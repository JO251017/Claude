import asyncio
from unittest.mock import AsyncMock, patch

from sqlalchemy.exc import IntegrityError

from app.domain.place import Place
from app.domain.price_discovery import DiscoveryJobStatus, PriceDiscoveryJob
from app.engine.price_discovery import orchestrator
from app.engine.price_discovery.candidate_selector import DiscoveryCandidate
from app.engine.price_discovery.price_validator import PriceVerdict
from app.integrations.gemini import (
    GroundingResult,
    GroundingUnavailableError,
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


def test_search_request_failure_gets_distinct_error_code_from_no_source_found():
    # 실사용 중 발견(2026-08-31): "정말 자료가 없음"(NO_SOURCE_FOUND)과 "검색 요청
    # 자체가 실패함"이 예전엔 똑같이 NO_SOURCE_FOUND 하나로 보여서 관리자 페이지에서
    # 구분이 안 됐다 — 이제 후자는 별도 error_code(SEARCH_ERR:<사유>)로 남는다.
    job = _job(attempt_count=0)
    session = _FakeSession(place=_place())
    with patch(
        "app.engine.price_discovery.orchestrator.discover_sources",
        new=AsyncMock(side_effect=GroundingUnavailableError("HTTP_429")),
    ):
        asyncio.run(orchestrator._process_job(session, job, client=None))
    assert job.status == DiscoveryJobStatus.PENDING
    assert job.error_code == "SEARCH_ERR:HTTP_429"
    assert job.error_code != "NO_SOURCE_FOUND"


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


# --- enqueue_candidates: 동시 요청 경쟁으로 같은 매장이 두 번 큐에 들어가려 하면
# (프로덕션에서 실제로 겪은 문제 — "한 번 실행"을 응답 오기 전에 여러 번 누름)
# ux_price_discovery_job_active_place 유니크 인덱스에 걸려 IntegrityError가 나는데,
# 이걸 500으로 전체 요청을 죽이지 않고 그 매장만 건너뛰어야 한다. ---


class _CommitRacingSession:
    """add()로 쌓인 걸 commit()할 때, 미리 지정한 인덱스(0-based, 몇 번째
    commit()인지)에서만 IntegrityError를 던진다 — 실제 유니크 인덱스 충돌을
    흉내낸다."""

    def __init__(self, fail_at_commit_index: set[int]):
        self._fail_at = fail_at_commit_index
        self._commit_call_count = 0
        self.added = []
        self.rollbacks = 0

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        idx = self._commit_call_count
        self._commit_call_count += 1
        if idx in self._fail_at:
            raise IntegrityError(
                "INSERT ...", {}, Exception("duplicate key value violates unique constraint")
            )

    async def rollback(self):
        self.rollbacks += 1


def _candidate(place_id: int, score: int = 10):
    return DiscoveryCandidate(place=Place(id=place_id, name=f"p{place_id}"), score=score, is_franchise=False)


def test_enqueue_candidates_skips_place_that_lost_the_race():
    candidates = [_candidate(1), _candidate(2), _candidate(3)]
    session = _CommitRacingSession(fail_at_commit_index={1})  # 두 번째(place_id=2)만 실패
    with patch(
        "app.engine.price_discovery.orchestrator.get_discovery_candidates",
        new=AsyncMock(return_value=candidates),
    ):
        created = asyncio.run(orchestrator.enqueue_candidates(session, limit=10))
    assert created == 2  # place 1, 3은 성공, place 2만 건너뜀
    assert session.rollbacks == 1


def test_enqueue_candidates_all_succeed_when_no_conflict():
    candidates = [_candidate(1), _candidate(2)]
    session = _CommitRacingSession(fail_at_commit_index=set())
    with patch(
        "app.engine.price_discovery.orchestrator.get_discovery_candidates",
        new=AsyncMock(return_value=candidates),
    ):
        created = asyncio.run(orchestrator.enqueue_candidates(session, limit=10))
    assert created == 2
    assert session.rollbacks == 0


def test_enqueue_candidates_returns_zero_for_empty_candidates():
    session = _CommitRacingSession(fail_at_commit_index=set())
    with patch(
        "app.engine.price_discovery.orchestrator.get_discovery_candidates",
        new=AsyncMock(return_value=[]),
    ):
        created = asyncio.run(orchestrator.enqueue_candidates(session, limit=10))
    assert created == 0
