import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

from sqlalchemy.exc import IntegrityError

from app.domain.user_digest import UserDigest
from app.engine.savings_digest import _facts_and_template, _week_start, get_or_create_digest
from app.gamification.service import ExplorerSummary, RecommendSummary, SavingsSummary
from app.gamification.streak import StreakSummary


def _summary(weekly_saved=0.0, total_saved=0.0, certification_count=0) -> SavingsSummary:
    return SavingsSummary(
        total_saved=total_saved, level=1, title="절약 초보", current_threshold=0,
        next_threshold=None, remaining_to_next=None, progress_pct=0.0,
        certification_count=certification_count, weekly_saved=weekly_saved,
    )


def _explorer(count=0) -> ExplorerSummary:
    return ExplorerSummary(discovered_place_count=count, title="", next_threshold=None, remaining_to_next=None)


def _recommend(count=0) -> RecommendSummary:
    return RecommendSummary(recommend_count=count, title="", next_threshold=None, remaining_to_next=None)


def _streak(days=0) -> StreakSummary:
    return StreakSummary(current_streak=days, did_activity_today=False, at_risk=False)


class _Result:
    def __init__(self, row):
        self._row = row

    def scalar_one_or_none(self):
        return self._row

    def scalar_one(self):
        return self._row


class _FakeSession:
    """execute()는 항상 "이번 주 캐시 조회"(또는 레이스 재조회) 결과를 순서대로
    돌려준다. commit()은 fail_commit이면 첫 호출에서만 IntegrityError를 던진다
    (price_discovery의 _CommitRacingSession과 같은 패턴)."""

    def __init__(self, existing=None, fail_commit=False, winner=None):
        self._existing = existing
        self._winner = winner
        self._fail_commit = fail_commit
        self.added = []
        self.commits = 0
        self.rollbacks = 0

    async def execute(self, _stmt):
        if self.commits >= 1 and self._fail_commit:
            return _Result(self._winner)
        return _Result(self._existing)

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.commits += 1
        if self._fail_commit and self.commits == 1:
            raise IntegrityError("INSERT ...", {}, Exception("duplicate key"))

    async def rollback(self):
        self.rollbacks += 1


def _patch_gamification(summary, explorer, recommend, streak):
    return (
        patch("app.engine.savings_digest.get_savings_summary", new=AsyncMock(return_value=summary)),
        patch("app.engine.savings_digest.get_explorer_summary", new=AsyncMock(return_value=explorer)),
        patch("app.engine.savings_digest.get_recommend_summary", new=AsyncMock(return_value=recommend)),
        patch("app.engine.savings_digest.get_streak_summary", new=AsyncMock(return_value=streak)),
    )


class _FakeClient:
    def __init__(self, text="이번 주도 알뜰하게 잘 보내셨어요!", raise_exc=None):
        self.generate_digest = AsyncMock(side_effect=self._call)
        self._text = text
        self._raise_exc = raise_exc

    async def _call(self, facts):
        if self._raise_exc:
            raise self._raise_exc
        return self._text


# --- _week_start: get_savings_summary와 정확히 같은 기준(UTC 월요일 00:00) ---


def test_week_start_is_monday_midnight_utc():
    wed = datetime(2026, 9, 2, 15, 30, tzinfo=UTC)  # 2026-09-02는 수요일
    assert _week_start(wed) == datetime(2026, 8, 31, 0, 0, 0, tzinfo=UTC)


def test_week_start_on_monday_is_same_day():
    mon = datetime(2026, 8, 31, 9, 0, tzinfo=UTC)
    assert _week_start(mon) == datetime(2026, 8, 31, 0, 0, 0, tzinfo=UTC)


# --- _facts_and_template ---


def test_facts_and_template_empty_activity_uses_empty_fallback():
    facts, allowed, template = _facts_and_template(
        weekly_saved=0, total_saved=0, discovered_place_count=0, visit_count=0, recommend_count=0, streak_days=0
    )
    assert facts == {}
    assert allowed == set()
    assert "발견하기" in template


def test_facts_and_template_includes_weekly_and_streak():
    facts, allowed, template = _facts_and_template(
        weekly_saved=8000, total_saved=50000, discovered_place_count=3, visit_count=2, recommend_count=1, streak_days=5
    )
    assert facts["이번 주 절약액"] == "8000원"
    assert allowed == {"8000", "50000", "3", "2", "1", "5"}
    assert "8000원" in template
    assert "5일째" in template


# --- get_or_create_digest ---


def test_returns_cached_digest_without_calling_ai():
    existing = UserDigest(user_id="u1", week_start=_week_start(datetime.now(UTC)), summary_text="캐시된 문장", source="ai")
    session = _FakeSession(existing=existing)
    client = _FakeClient()
    patches = _patch_gamification(_summary(), _explorer(), _recommend(), _streak())
    with patches[0], patches[1], patches[2], patches[3]:
        text, source = asyncio.run(get_or_create_digest(session, "u1", client=client))
    assert text == "캐시된 문장"
    assert source == "ai"
    client.generate_digest.assert_not_called()
    assert session.commits == 0


def test_generates_ai_digest_when_no_cache_and_facts_exist():
    session = _FakeSession(existing=None)
    client = _FakeClient(text="이번 주도 알뜰하게 잘 보내셨어요!")
    patches = _patch_gamification(
        _summary(weekly_saved=8000, total_saved=50000), _explorer(3), _recommend(1), _streak(5)
    )
    with patches[0], patches[1], patches[2], patches[3]:
        text, source = asyncio.run(get_or_create_digest(session, "u1", client=client))
    assert text == "이번 주도 알뜰하게 잘 보내셨어요!"
    assert source == "ai"
    assert session.commits == 1
    assert session.added[0].source == "ai"


def test_falls_back_to_template_when_ai_hallucinates_number():
    session = _FakeSession(existing=None)
    client = _FakeClient(text="이번 주 99000원 절약했어요!")  # facts에 없는 숫자
    patches = _patch_gamification(_summary(weekly_saved=8000), _explorer(), _recommend(), _streak())
    with patches[0], patches[1], patches[2], patches[3]:
        text, source = asyncio.run(get_or_create_digest(session, "u1", client=client))
    assert source == "template"
    assert "8000원" in text


def test_falls_back_to_template_when_ai_call_fails():
    session = _FakeSession(existing=None)
    client = _FakeClient(raise_exc=RuntimeError("boom"))
    patches = _patch_gamification(_summary(weekly_saved=8000), _explorer(), _recommend(), _streak())
    with patches[0], patches[1], patches[2], patches[3]:
        text, source = asyncio.run(get_or_create_digest(session, "u1", client=client))
    assert source == "template"
    assert "8000원" in text


def test_no_facts_skips_ai_call_entirely():
    session = _FakeSession(existing=None)
    client = _FakeClient()
    patches = _patch_gamification(_summary(), _explorer(), _recommend(), _streak())
    with patches[0], patches[1], patches[2], patches[3]:
        text, source = asyncio.run(get_or_create_digest(session, "u1", client=client))
    assert source == "template"
    client.generate_digest.assert_not_called()


def test_concurrent_request_race_returns_winners_digest():
    # 실사용을 가정: MY탭을 빠르게 두 번 열어 같은 주 캐시를 동시에 만들려다
    # 유니크 인덱스(ux_user_digest_user_week)에 걸리는 경우 — price_discovery의
    # enqueue_candidates 레이스 처리와 같은 원칙(500으로 죽이지 않고 이긴 쪽의
    # 결과를 그대로 읽어 돌려준다).
    winner = UserDigest(user_id="u1", week_start=_week_start(datetime.now(UTC)), summary_text="먼저 이긴 문장", source="template")
    session = _FakeSession(existing=None, fail_commit=True, winner=winner)
    client = _FakeClient()
    patches = _patch_gamification(_summary(weekly_saved=8000), _explorer(), _recommend(), _streak())
    with patches[0], patches[1], patches[2], patches[3]:
        text, source = asyncio.run(get_or_create_digest(session, "u1", client=client))
    assert text == "먼저 이긴 문장"
    assert session.rollbacks == 1
