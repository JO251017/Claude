"""AI 활용 확대 안건 C(2026-08-31) — 개인화 절약 다이제스트.

MY탭에 "이번 주 절약 활동을 이렇게 하셨어요" 식으로, 사용자의 실제 활동을
AI가 다정한 한두 문장으로 요약한다. 숫자는 전부 app/gamification/service.py·
streak.py가 이미 계산해 MY탭 화면(SavingsSummaryResponse)에 그대로 뜨는 바로
그 값만 쓴다 — 새 집계 쿼리를 따로 만들지 않고, AI는 그 사실들을 phrase만
한다(app.engine.ai_text_guard로 숫자 환각을 걸러낸다). offer_blurb_backfill과
완전히 같은 원칙.

검색 응답의 one_line(savings_report.py)과 같은 이유로 매 요청마다 AI를 안
부른다 — 사용자당 주 1번만 생성해 user_digest에 캐시하고, 그 다음부터는
캐시를 그대로 돌려준다(온디맨드: MY탭 진입 시 이번 주 캐시가 없으면 그
자리에서 한 번 생성)."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.user_digest import UserDigest
from app.engine.ai_text_guard import has_unapproved_numbers
from app.gamification.service import get_explorer_summary, get_recommend_summary, get_savings_summary
from app.gamification.streak import get_streak_summary
from app.integrations.gemini import GeminiVisionClient

# summary_text 컬럼 한도(300자)보다 짧게 — 프롬프트가 60자 이내를 요구하지만
# 모델이 어기는 경우까지 대비한 안전판(offer_blurb_backfill과 같은 관례).
_MAX_DIGEST_LEN = 200

_EMPTY_FALLBACK = "아직 활동 기록이 없어요. 발견하기 버튼으로 첫 절약을 찾아보세요!"


def _week_start(now: datetime) -> datetime:
    """app.gamification.service.get_savings_summary가 weekly_saved를 계산할 때
    쓰는 것과 정확히 같은 기준(UTC, 월요일 00:00) — 다이제스트가 인용하는
    "이번 주 절약액"이 MY탭에 뜨는 숫자와 어긋나지 않게 한다."""
    return (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)


def _facts_and_template(
    *,
    weekly_saved: float,
    total_saved: float,
    discovered_place_count: int,
    visit_count: int,
    recommend_count: int,
    streak_days: int,
) -> tuple[dict[str, str], set[str], str]:
    """(AI에게 줄 사실 목록, 허용된 숫자, 그 사실만으로 만든 결정론적 폴백 문장).
    AI 호출이 실패하거나 숫자를 지어내면 이 폴백을 그대로 쓴다 — route_planner.
    _fallback_summary와 같은 위치의 함수."""
    facts: dict[str, str] = {}
    allowed: set[str] = set()
    template_parts: list[str] = []

    if weekly_saved > 0:
        n = str(round(weekly_saved))
        facts["이번 주 절약액"] = f"{n}원"
        allowed.add(n)
        template_parts.append(f"이번 주 {n}원 절약했어요")
    if total_saved > 0:
        n = str(round(total_saved))
        facts["지금까지 총 절약액"] = f"{n}원"
        allowed.add(n)
    if discovered_place_count > 0:
        n = str(discovered_place_count)
        facts["지금까지 발견한 매장 수"] = f"{n}곳"
        allowed.add(n)
    if visit_count > 0:
        n = str(visit_count)
        facts["지금까지 방문 인증 횟수"] = f"{n}회"
        allowed.add(n)
    if recommend_count > 0:
        n = str(recommend_count)
        facts["지금까지 추천 횟수"] = f"{n}회"
        allowed.add(n)
    if streak_days > 0:
        n = str(streak_days)
        facts["연속 활동 일수"] = f"{n}일"
        allowed.add(n)
        template_parts.append(f"{n}일째 연속으로 활동 중이에요")

    if not template_parts:
        # 절약액/스트릭 둘 다 없어도 발견/방문/추천 실적이 있으면 그걸로 대신한다.
        if discovered_place_count > 0:
            template_parts.append(f"지금까지 {discovered_place_count}곳을 발견했어요")
        elif visit_count > 0:
            template_parts.append(f"지금까지 {visit_count}번 방문 인증했어요")
        elif recommend_count > 0:
            template_parts.append(f"지금까지 {recommend_count}번 추천했어요")

    template = ". ".join(template_parts) + "!" if template_parts else _EMPTY_FALLBACK
    return facts, allowed, template


async def get_or_create_digest(
    session: AsyncSession, user_id: str, *, client: GeminiVisionClient | None = None, now: datetime | None = None
) -> tuple[str, str]:
    """이번 주 다이제스트를 (문장, source) 형태로 돌려준다. source는 "ai"|"template".
    캐시가 있으면 AI를 아예 안 부르고 그대로 반환한다."""
    now = now or datetime.now(UTC)
    week_start = _week_start(now)

    existing = (
        await session.execute(
            select(UserDigest).where(UserDigest.user_id == user_id, UserDigest.week_start == week_start)
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing.summary_text, existing.source

    summary = await get_savings_summary(session, user_id)
    explorer = await get_explorer_summary(session, user_id)
    recommend = await get_recommend_summary(session, user_id)
    streak = await get_streak_summary(session, user_id)

    facts, allowed, template = _facts_and_template(
        weekly_saved=summary.weekly_saved,
        total_saved=summary.total_saved,
        discovered_place_count=explorer.discovered_place_count,
        visit_count=summary.certification_count,
        recommend_count=recommend.recommend_count,
        streak_days=streak.current_streak,
    )

    text, source = template, "template"
    if facts:
        client = client or GeminiVisionClient()
        try:
            ai_text = await client.generate_digest(facts)
        except Exception:  # noqa: BLE001 - AI 실패가 다이제스트 자체를 막으면 안 됨
            ai_text = None
        if ai_text and not has_unapproved_numbers(ai_text, allowed):
            text, source = ai_text[:_MAX_DIGEST_LEN], "ai"

    session.add(UserDigest(user_id=user_id, week_start=week_start, summary_text=text, source=source))
    try:
        await session.commit()
    except IntegrityError:
        # 동시 요청 레이스(MY탭을 두 번 빠르게 열었을 때 등) — 이미 다른 요청이
        # 이번 주 캐시를 만들었으면 그걸 그대로 읽는다(price_discovery의
        # enqueue_candidates와 같은 패턴).
        await session.rollback()
        winner = (
            await session.execute(
                select(UserDigest).where(
                    UserDigest.user_id == user_id, UserDigest.week_start == week_start
                )
            )
        ).scalar_one()
        return winner.summary_text, winner.source

    return text, source
