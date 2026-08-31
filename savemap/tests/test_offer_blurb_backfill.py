import asyncio
from unittest.mock import AsyncMock

from app.domain.enums import Category, Layer, SourceType
from app.domain.offer import Offer
from app.domain.place import Place
from app.engine.offer_blurb_backfill import _facts_for_offer, backfill_offer_blurbs


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeSession:
    def __init__(self, rows):
        self._rows = rows
        self.commits = 0
        self.rollbacks = 0

    async def execute(self, _stmt):
        return _Result(self._rows)

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1


def _offer(id_=1, base_price=10000.0, store_discount=2000.0, benchmark_source="region", sample=8, ai_one_line=None):
    return Offer(
        id=id_,
        place_id=1,
        source=SourceType.S1_PUBLIC,
        layer=Layer.REGULAR,
        category=Category.DISCOUNT,
        title="김치찌개 8,000원",
        base_price=base_price,
        store_discount=store_discount,
        benchmark_source=benchmark_source,
        benchmark_sample_count=sample,
        ai_one_line=ai_one_line,
    )


def _place():
    return Place(id=1, name="가게", category_name="일반음식점 > 한식", geom="fake-geom")


class _FakeClient:
    def __init__(self, text="주변보다 저렴해요.", raise_exc=None):
        self._text = text
        self._raise_exc = raise_exc
        self.generate_offer_blurb = AsyncMock(side_effect=self._call)

    async def _call(self, facts):
        if self._raise_exc:
            raise self._raise_exc
        return self._text


# --- _facts_for_offer: 사실 목록과 허용 숫자가 정확히 일치해야 한다 ---


def test_facts_include_category_and_benchmark():
    facts, allowed = _facts_for_offer(_offer(), _place())
    assert facts["업종"] == "일반음식점 > 한식"
    assert facts["가격 비교 기준"] == "주변 매장 실측가"
    assert facts["비교한 주변 매장 수"] == "8곳"
    assert allowed == {"8"}


def test_facts_omit_sample_count_when_not_region():
    facts, allowed = _facts_for_offer(_offer(benchmark_source="ai", sample=None), _place())
    assert "비교한 주변 매장 수" not in facts
    assert allowed == set()


def test_facts_omit_benchmark_when_none():
    facts, allowed = _facts_for_offer(_offer(benchmark_source=None), _place())
    assert "가격 비교 기준" not in facts
    assert "비교 결과" not in facts


# --- backfill_offer_blurbs: 배치/페이지네이션/검증 ---


def test_generates_and_saves_blurb():
    session = _FakeSession([(_offer(), _place())])
    client = _FakeClient(text="주변보다 저렴한 곳이에요.")
    result = asyncio.run(backfill_offer_blurbs(session, limit=10, client=client))

    assert result["generated"] == 1
    assert result["scanned"] == 1
    assert result["done"] is True
    assert session.commits == 1
    assert session.rollbacks == 0


def test_dry_run_does_not_commit():
    offer = _offer()
    session = _FakeSession([(offer, _place())])
    client = _FakeClient(text="주변보다 저렴한 곳이에요.")
    result = asyncio.run(backfill_offer_blurbs(session, limit=10, dry_run=True, client=client))

    assert result["generated"] == 1
    assert session.rollbacks == 1
    assert session.commits == 0
    assert offer.ai_one_line is None  # dry_run이라 실제로는 안 붙음


def test_hallucinated_number_is_rejected_and_not_saved():
    # facts엔 "8곳"만 허용됐는데 AI가 "23%"라는 새 숫자를 지어낸 경우.
    offer = _offer()
    session = _FakeSession([(offer, _place())])
    client = _FakeClient(text="23% 더 저렴해요.")
    result = asyncio.run(backfill_offer_blurbs(session, limit=10, client=client))

    assert result["generated"] == 0
    assert result["rejected_hallucination"] == 1
    assert offer.ai_one_line is None


def test_generation_failure_is_counted_and_does_not_block_others():
    offer1, offer2 = _offer(id_=1), _offer(id_=2)
    session = _FakeSession([(offer1, _place()), (offer2, _place())])
    call_count = {"n": 0}

    async def flaky(facts):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise RuntimeError("boom")
        return "주변보다 저렴한 곳이에요."

    client = _FakeClient()
    client.generate_offer_blurb = AsyncMock(side_effect=flaky)
    result = asyncio.run(backfill_offer_blurbs(session, limit=10, client=client))

    assert result["failed"] == 1
    assert result["generated"] == 1
    assert offer1.ai_one_line is None
    assert offer2.ai_one_line == "주변보다 저렴한 곳이에요."


def test_none_response_counts_as_failed():
    session = _FakeSession([(_offer(), _place())])
    client = _FakeClient(text=None)
    result = asyncio.run(backfill_offer_blurbs(session, limit=10, client=client))
    assert result["failed"] == 1
    assert result["generated"] == 0


def test_next_offset_and_done_when_batch_smaller_than_limit():
    session = _FakeSession([(_offer(id_=5), _place())])
    client = _FakeClient()
    result = asyncio.run(backfill_offer_blurbs(session, limit=10, client=client))
    assert result["next_offset"] == 6
    assert result["done"] is True


def test_not_done_when_batch_equals_limit():
    session = _FakeSession([(_offer(id_=1), _place()), (_offer(id_=2), _place())])
    client = _FakeClient()
    result = asyncio.run(backfill_offer_blurbs(session, limit=2, client=client))
    assert result["done"] is False
    assert result["next_offset"] == 3


def test_empty_batch_is_done():
    session = _FakeSession([])
    client = _FakeClient()
    result = asyncio.run(backfill_offer_blurbs(session, limit=10, client=client))
    assert result == {
        "offset": 0, "dry_run": False,
        "scanned": 0, "generated": 0, "rejected_hallucination": 0, "failed": 0,
        "next_offset": 0, "done": True,
    }
