import asyncio
from unittest.mock import AsyncMock, patch

from app.domain.place import Place
from app.domain.price_discovery import DiscoveryJobStatus, PriceDiscoveryJob
from app.engine.price_discovery import orchestrator
from app.engine.price_discovery.price_validator import PriceVerdict
from app.integrations.gemini import (
    GroundingResult,
    PriceDiscoveryExtraction,
    PriceDiscoveryStoreMatch,
)


class _FakeSession:
    def __init__(self, place: Place | None = None, execute_rows: list | None = None):
        self._place = place
        self._execute_rows = execute_rows or []
        self.commits = 0
        self.rollbacks = 0

    async def get(self, model, id_):
        return self._place

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1

    async def execute(self, _stmt):
        class _Result:
            def __init__(self, rows):
                self._rows = rows

            def scalars(self):
                class _Scalars:
                    def __init__(self, rows):
                        self._rows = rows

                    def all(self):
                        return self._rows

                return _Scalars(self._rows)

        return _Result(self._execute_rows)


def _job(**kw) -> PriceDiscoveryJob:
    base = dict(id=1, place_id=1, status=DiscoveryJobStatus.PENDING, priority=0, attempt_count=0)
    base.update(kw)
    return PriceDiscoveryJob(**base)


def _place() -> Place:
    return Place(id=1, name="냉삼가게", address="충남 아산시", geom="fake-geom")


def _price_item(name="김치찌개", price=8000.0, source_type="official"):
    from app.integrations.gemini import PriceDiscoveryPriceItem

    return PriceDiscoveryPriceItem(
        menu_name=name, price=price, source_type=source_type,
        source_url="https://example.com", source_title=None, observed_at=None, evidence=None,
    )


# --- source_discovery/extraction 실패 → 재시도 → manual_review ---


def test_no_source_found_retries_then_gives_up():
    job = _job(attempt_count=0)
    session = _FakeSession(place=_place())
    with patch("app.engine.price_discovery.orchestrator.discover_sources", new=AsyncMock(return_value=None)):
        asyncio.run(orchestrator._process_job(session, job, client=None))
    # 1차 실패, max_retry=1 미만이라 재시도(PENDING)로 돌아감
    assert job.status == DiscoveryJobStatus.PENDING
    assert job.attempt_count == 1

    with patch("app.engine.price_discovery.orchestrator.discover_sources", new=AsyncMock(return_value=None)):
        asyncio.run(orchestrator._process_job(session, job, client=None))
    # 2차 실패, max_retry(1)를 넘었으니 포기 → manual_review
    assert job.status == DiscoveryJobStatus.MANUAL_REVIEW
    assert job.attempt_count == 2
    assert job.error_code == "NO_SOURCE_FOUND"


def test_place_not_found_gives_up_immediately():
    job = _job()
    session = _FakeSession(place=None)
    asyncio.run(orchestrator._process_job(session, job, client=None))
    assert job.status == DiscoveryJobStatus.MANUAL_REVIEW
    assert job.error_code == "PLACE_NOT_FOUND"


# --- store_matcher REJECT/REVIEW ---


def test_store_match_rejected_marks_job_failed_and_publishes_nothing():
    job = _job()
    session = _FakeSession(place=_place())
    grounding = GroundingResult(text="다른 지점 얘기", citations=[])
    extraction = PriceDiscoveryExtraction(
        store_match=PriceDiscoveryStoreMatch(matched=False, confidence=0.99, reason="다른 지점"),
        prices=[_price_item()],
    )
    with (
        patch("app.engine.price_discovery.orchestrator.discover_sources", new=AsyncMock(return_value=grounding)),
        patch("app.engine.price_discovery.orchestrator.extract_prices", new=AsyncMock(return_value=extraction)),
        patch("app.engine.price_discovery.orchestrator.publish_prices", new=AsyncMock()) as mock_publish,
    ):
        published = asyncio.run(orchestrator._process_job(session, job, client=None))
    assert job.status == DiscoveryJobStatus.FAILED
    assert job.error_code == "STORE_NOT_MATCHED"
    assert published == 0
    mock_publish.assert_not_called()


def test_no_prices_found_marks_job_failed():
    job = _job()
    session = _FakeSession(place=_place())
    grounding = GroundingResult(text="가격 정보 없음", citations=[])
    extraction = PriceDiscoveryExtraction(
        store_match=PriceDiscoveryStoreMatch(matched=True, confidence=0.99, reason="일치"),
        prices=[],
    )
    with (
        patch("app.engine.price_discovery.orchestrator.discover_sources", new=AsyncMock(return_value=grounding)),
        patch("app.engine.price_discovery.orchestrator.extract_prices", new=AsyncMock(return_value=extraction)),
    ):
        asyncio.run(orchestrator._process_job(session, job, client=None))
    assert job.status == DiscoveryJobStatus.FAILED
    assert job.error_code == "NO_PRICES_FOUND"


def test_review_decision_goes_to_manual_review_without_publishing():
    job = _job()
    session = _FakeSession(place=_place())
    grounding = GroundingResult(text="애매함", citations=[])
    extraction = PriceDiscoveryExtraction(
        store_match=PriceDiscoveryStoreMatch(matched=True, confidence=0.85, reason="애매함"),
        prices=[_price_item()],
    )
    with (
        patch("app.engine.price_discovery.orchestrator.discover_sources", new=AsyncMock(return_value=grounding)),
        patch("app.engine.price_discovery.orchestrator.extract_prices", new=AsyncMock(return_value=extraction)),
        patch("app.engine.price_discovery.orchestrator.publish_prices", new=AsyncMock()) as mock_publish,
    ):
        published = asyncio.run(orchestrator._process_job(session, job, client=None))
    assert job.status == DiscoveryJobStatus.MANUAL_REVIEW
    assert published == 0
    mock_publish.assert_not_called()


# --- 정상 흐름: AUTO 매칭 + 유효 가격 → COMPLETED ---


def test_auto_match_with_valid_prices_completes_and_publishes():
    job = _job()
    session = _FakeSession(place=_place())
    grounding = GroundingResult(text="확인됨", citations=[])
    extraction = PriceDiscoveryExtraction(
        store_match=PriceDiscoveryStoreMatch(matched=True, confidence=0.98, reason="일치"),
        prices=[_price_item(price=8000.0)],
    )
    fake_published = [object()]
    with (
        patch("app.engine.price_discovery.orchestrator.discover_sources", new=AsyncMock(return_value=grounding)),
        patch("app.engine.price_discovery.orchestrator.extract_prices", new=AsyncMock(return_value=extraction)),
        patch(
            "app.engine.price_discovery.orchestrator.publish_prices",
            new=AsyncMock(return_value=fake_published),
        ) as mock_publish,
    ):
        published = asyncio.run(orchestrator._process_job(session, job, client=None))
    assert job.status == DiscoveryJobStatus.COMPLETED
    assert published == 1
    # publish_prices에 넘어간 항목이 VALID verdict인지 확인
    call_args = mock_publish.call_args
    validated_arg = call_args.args[2]
    assert all(v.verdict == PriceVerdict.VALID for v in validated_arg)


def test_auto_match_with_outlier_price_goes_to_manual_review_but_still_publishes_valid_ones():
    job = _job()
    session = _FakeSession(place=_place())
    grounding = GroundingResult(text="확인됨", citations=[])
    extraction = PriceDiscoveryExtraction(
        store_match=PriceDiscoveryStoreMatch(matched=True, confidence=0.98, reason="일치"),
        prices=[_price_item(name="정상메뉴", price=8000.0), _price_item(name="이상치메뉴", price=9_000_000.0)],
    )
    with (
        patch("app.engine.price_discovery.orchestrator.discover_sources", new=AsyncMock(return_value=grounding)),
        patch("app.engine.price_discovery.orchestrator.extract_prices", new=AsyncMock(return_value=extraction)),
        patch(
            "app.engine.price_discovery.orchestrator.publish_prices",
            new=AsyncMock(return_value=[object()]),
        ) as mock_publish,
    ):
        asyncio.run(orchestrator._process_job(session, job, client=None))
    assert job.status == DiscoveryJobStatus.MANUAL_REVIEW
    validated_arg = mock_publish.call_args.args[2]
    assert len(validated_arg) == 1  # 이상치는 publish_prices에 안 넘어감(VALID만)


# --- force(관리자 승인) — REVIEW/이상치는 넘기지만 REJECT는 절대 안 넘긴다 ---


def test_force_publishes_review_decision_items():
    job = _job(status=DiscoveryJobStatus.MANUAL_REVIEW)
    session = _FakeSession(place=_place())
    grounding = GroundingResult(text="애매함", citations=[])
    extraction = PriceDiscoveryExtraction(
        store_match=PriceDiscoveryStoreMatch(matched=True, confidence=0.85, reason="애매함"),
        prices=[_price_item()],
    )
    with (
        patch("app.engine.price_discovery.orchestrator.discover_sources", new=AsyncMock(return_value=grounding)),
        patch("app.engine.price_discovery.orchestrator.extract_prices", new=AsyncMock(return_value=extraction)),
        patch(
            "app.engine.price_discovery.orchestrator.publish_prices",
            new=AsyncMock(return_value=[object()]),
        ) as mock_publish,
    ):
        published = asyncio.run(orchestrator._process_job(session, job, client=None, force=True))
    assert job.status == DiscoveryJobStatus.COMPLETED
    assert published == 1
    mock_publish.assert_called_once()


def test_force_never_bypasses_explicit_store_rejection():
    job = _job(status=DiscoveryJobStatus.MANUAL_REVIEW)
    session = _FakeSession(place=_place())
    grounding = GroundingResult(text="다른 곳", citations=[])
    extraction = PriceDiscoveryExtraction(
        store_match=PriceDiscoveryStoreMatch(matched=False, confidence=0.99, reason="다른 매장"),
        prices=[_price_item()],
    )
    with (
        patch("app.engine.price_discovery.orchestrator.discover_sources", new=AsyncMock(return_value=grounding)),
        patch("app.engine.price_discovery.orchestrator.extract_prices", new=AsyncMock(return_value=extraction)),
        patch("app.engine.price_discovery.orchestrator.publish_prices", new=AsyncMock()) as mock_publish,
    ):
        asyncio.run(orchestrator._process_job(session, job, client=None, force=True))
    assert job.status == DiscoveryJobStatus.FAILED
    assert job.error_code == "STORE_NOT_MATCHED"
    mock_publish.assert_not_called()


# --- run_discovery_batch: 집계 + 예외 하나가 나머지를 안 막음 ---


def test_run_discovery_batch_aggregates_and_survives_one_failure():
    ok_job = _job(id=1, place_id=1)
    boom_job = _job(id=2, place_id=2)
    session = _FakeSession(place=_place(), execute_rows=[ok_job, boom_job])

    async def _fake_process(sess, job, client, force=False):
        if job.id == 2:
            raise RuntimeError("boom")
        job.status = DiscoveryJobStatus.COMPLETED
        return 3

    with patch("app.engine.price_discovery.orchestrator._process_job", new=_fake_process):
        result = asyncio.run(orchestrator.run_discovery_batch(session, limit=10))

    assert result["jobs_picked_up"] == 2
    assert result["jobs_completed"] == 1
    assert result["jobs_failed"] == 1
    assert result["prices_found"] == 3
    assert boom_job.status == DiscoveryJobStatus.FAILED
    assert boom_job.error_code == "UNEXPECTED_ERROR"
