import asyncio
from unittest.mock import AsyncMock

from app.domain.franchise import FranchiseBrand
from app.engine.franchise_keyword_discovery import discover_franchise_keywords


class _ScalarsResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return _ScalarsResult(self._rows)


class _FakeSession:
    """discover_franchise_keywords는 브랜드 목록을 한 번만 조회한다
    (_load_candidate_brands) — menu_synonym_discovery와 달리 기존 후보
    조회가 없다: suggested_match_keywords IS NULL 조건 자체가 이미 필터다."""

    def __init__(self, brands):
        self._result = _Result(brands)
        self.commits = 0
        self.rollbacks = 0

    async def execute(self, _stmt):
        return self._result

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1


def _brand(id_, name, match_keywords=None):
    return FranchiseBrand(id=id_, name=name, match_keywords=match_keywords)


class _FakeClient:
    def __init__(self, result=None, raise_exc=None):
        self._result = result or {}
        self._raise_exc = raise_exc
        self.suggest_franchise_keywords_batch = AsyncMock(side_effect=self._call)

    async def _call(self, brands):
        if self._raise_exc:
            raise self._raise_exc
        return dict(self._result)


def test_saves_suggested_keywords_onto_matching_brand():
    brand = _brand(1, "스타벅스")
    session = _FakeSession([brand])
    client = _FakeClient(result={0: ["starbucks", "스타 벅스"]})
    result = asyncio.run(discover_franchise_keywords(session, limit=100, client=client))

    assert result["scanned"] == 1
    assert result["suggested"] == 1
    assert result["done"] is True
    assert session.commits == 1
    assert brand.suggested_match_keywords == "starbucks|스타 벅스"
    # 실제 매칭 컬럼은 절대 건드리지 않는다.
    assert brand.match_keywords is None


def test_keywords_joined_with_pipe_as_returned_by_client():
    """3개 상한 적용은 클라이언트(suggest_franchise_keywords_batch) 책임이다
    (test_gemini_client.py에서 검증) — 엔진은 받은 리스트를 그대로 파이프로
    합쳐 저장하기만 한다."""
    brand = _brand(1, "스타벅스")
    session = _FakeSession([brand])
    client = _FakeClient(result={0: ["a", "b", "c"]})
    asyncio.run(discover_franchise_keywords(session, limit=100, client=client))

    assert brand.suggested_match_keywords == "a|b|c"


def test_dry_run_does_not_commit_or_save():
    brand = _brand(1, "스타벅스")
    session = _FakeSession([brand])
    client = _FakeClient(result={0: ["starbucks"]})
    result = asyncio.run(
        discover_franchise_keywords(session, limit=100, dry_run=True, client=client)
    )

    assert result["dry_run"] is True
    assert brand.suggested_match_keywords is None
    assert session.commits == 0
    assert session.rollbacks == 1


def test_batch_call_failure_does_not_crash_and_yields_zero():
    brand = _brand(1, "스타벅스")
    session = _FakeSession([brand])
    client = _FakeClient(raise_exc=RuntimeError("boom"))
    result = asyncio.run(discover_franchise_keywords(session, limit=100, client=client))

    assert result["suggested"] == 0
    assert session.commits == 1  # 아무것도 없어도 정상적으로 커밋(빈 트랜잭션)까지 진행


def test_empty_candidate_list_marks_done_immediately():
    session = _FakeSession([])
    client = _FakeClient()
    result = asyncio.run(discover_franchise_keywords(session, offset=0, limit=100, client=client))

    assert result["done"] is True
    assert result["scanned"] == 0
    client.suggest_franchise_keywords_batch.assert_not_awaited()


def test_pagination_offset_advances_by_page_size():
    brands = [_brand(1, "a"), _brand(2, "b"), _brand(3, "c")]
    session = _FakeSession(brands)
    client = _FakeClient(result={})
    result = asyncio.run(discover_franchise_keywords(session, offset=0, limit=2, client=client))

    assert result["scanned"] == 2
    assert result["next_offset"] == 2
    assert result["done"] is False


def test_brand_missing_from_response_is_left_untouched():
    """AI가 특정 브랜드에 제안할 게 없다고 판단하면(응답에서 아예 빼면)
    그 브랜드의 suggested_match_keywords는 그대로 None으로 남아야 한다 —
    다음 배치에서 다시 후보로 잡힌다."""
    brand_a = _brand(1, "스타벅스")
    brand_b = _brand(2, "이디야")
    session = _FakeSession([brand_a, brand_b])
    client = _FakeClient(result={0: ["starbucks"]})
    result = asyncio.run(discover_franchise_keywords(session, limit=100, client=client))

    assert result["suggested"] == 1
    assert brand_a.suggested_match_keywords == "starbucks"
    assert brand_b.suggested_match_keywords is None
