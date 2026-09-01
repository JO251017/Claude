from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import XP_REWARD, XpReason
from app.domain.savings import SavingsCertification
from app.domain.store_visit import PlaceRecommendation, StoreInterest
from app.domain.xp import XpLedger

# 사용자 노출 브랜드명(2026-08-31, "쓸모" 브랜드 전환) — 최고 등급 칭호 3개에
# 브랜드명이 박혀 있어서, 매번 문자열을 직접 쓰지 않고 여기 한 곳만 바꾸면
# 전부 반영되게 상수로 뺐다. DB 테이블명/API/모듈명 등 내부 식별자(savemap*)는
# 이 전환 대상이 아니다 — 사용자가 실제로 보는 문구만 바꾼다.
BRAND_NAME = "쓸모"

# 예전엔 여기에 XP 총량 기반 레벨링(compute_level/XP_PER_LEVEL/LEVEL_TITLES)이
# 있었다 — "구조 재설계 제안서"(2026-08-13) §1 진단에서, 프론트가 실제로는
# compute_savings_level()(실제 인증된 누적 절약금액 기반)만 쓰고 이쪽은 어디서도
# 호출되지 않는 죽은 코드라는 게 확인돼 제거했다(GET /me/xp 엔드포인트도 함께
# 제거). xp_ledger/award_xp 자체는 그대로 남는다 — "캐릭터 레벨"이 아니라 향후
# 배지 등 활동 지표 전용으로 역할이 좁혀졌을 뿐이다.


async def award_xp(
    session: AsyncSession, user_id: str, reason: XpReason, place_id: int | None = None
) -> int:
    delta = XP_REWARD[reason]
    session.add(XpLedger(user_id=user_id, delta=delta, reason=reason, place_id=place_id))
    await session.commit()
    return delta


async def get_dining_counts(session: AsyncSession, place_ids: list[int]) -> dict[int, int]:
    """검색 결과에 "N번 식사 인증됨"을 보여주기 위한 매장별 누적 영수증/절약 인증 수."""
    if not place_ids:
        return {}
    rows = (
        await session.execute(
            select(SavingsCertification.place_id, func.count())
            .where(SavingsCertification.place_id.in_(place_ids))
            .group_by(SavingsCertification.place_id)
        )
    ).all()
    return {place_id: count for place_id, count in rows}


# --- 절약 레벨 (리디자인 기획서 §5~15): 캐릭터 성장은 XP가 아닌
# "실제 인증된 누적 절약금액"으로만 결정한다. XP/xp_ledger는 배지 등 내부 활동
# 지표로만 남기고, 사용자에게 노출되는 레벨/캐릭터 성장은 이 값을 사용한다.
# (가정) 레벨 구간별 누적 절약금액 임계값. 기획서에 정확한 숫자가 명시되지 않아
# 예시(§15 "Lv.6→Lv.7까지 ₩1,000,000")를 참고해 임의로 설정했다.
SAVINGS_LEVEL_THRESHOLDS: list[tuple[int, str, float]] = [
    (1, "절약 초보", 0),
    (2, "짠지망생", 10_000),
    (3, "알뜰 탐험가", 30_000),
    (4, "절약 탐험가", 70_000),
    (5, "동네 절약꾼", 150_000),
    (6, "절약 고수", 350_000),
    (7, "절약왕", 1_000_000),
]
SAVINGS_LEVEL_STEP_BEYOND_MAX = 500_000  # 최고 구간 이후엔 이 금액씩 레벨업한다고 가정


@dataclass
class SavingsSummary:
    total_saved: float
    level: int
    title: str
    current_threshold: float
    next_threshold: float | None
    remaining_to_next: float | None
    progress_pct: float
    certification_count: int
    monthly_saved: float = 0.0
    # MY 탭 절약 요약 재구조화(2-1, 2026-08-13): "오늘 누적 절약"을 메인으로,
    # 주간/한달(기존 monthly_saved)/연간을 나란히 보여주기 위한 기간별 합계.
    today_saved: float = 0.0
    weekly_saved: float = 0.0
    yearly_saved: float = 0.0


def compute_savings_level(
    total_saved: float, certification_count: int = 0, monthly_saved: float = 0.0
) -> SavingsSummary:
    total_saved = max(total_saved, 0.0)
    level, title, threshold = SAVINGS_LEVEL_THRESHOLDS[0]
    next_threshold: float | None = None
    for i, (lv, name, amount) in enumerate(SAVINGS_LEVEL_THRESHOLDS):
        if total_saved >= amount:
            level, title, threshold = lv, name, amount
            next_threshold = (
                SAVINGS_LEVEL_THRESHOLDS[i + 1][2] if i + 1 < len(SAVINGS_LEVEL_THRESHOLDS) else None
            )
        else:
            break

    if next_threshold is None and total_saved >= SAVINGS_LEVEL_THRESHOLDS[-1][2]:
        max_lv, max_title, max_amount = SAVINGS_LEVEL_THRESHOLDS[-1]
        extra_levels = int((total_saved - max_amount) // SAVINGS_LEVEL_STEP_BEYOND_MAX)
        level = max_lv + extra_levels
        title = max_title
        threshold = max_amount + extra_levels * SAVINGS_LEVEL_STEP_BEYOND_MAX
        next_threshold = threshold + SAVINGS_LEVEL_STEP_BEYOND_MAX

    remaining = None if next_threshold is None else max(next_threshold - total_saved, 0.0)
    span = None if next_threshold is None else (next_threshold - threshold)
    pct = 0.0 if not span else min(100.0, round((total_saved - threshold) / span * 100, 1))

    return SavingsSummary(
        total_saved=total_saved,
        level=level,
        title=title,
        current_threshold=threshold,
        next_threshold=next_threshold,
        remaining_to_next=remaining,
        progress_pct=pct,
        certification_count=certification_count,
        monthly_saved=monthly_saved,
    )


async def get_savings_summary(session: AsyncSession, user_id: str) -> SavingsSummary:
    row = (
        await session.execute(
            select(
                func.coalesce(func.sum(SavingsCertification.amount), 0),
                func.count(SavingsCertification.id),
            ).where(SavingsCertification.user_id == user_id)
        )
    ).one()
    total, count = row

    # 오늘/이번 주/이번 달/올해 절약 합계 — MY 탭 재구조화(2-1)에서 "오늘 누적
    # 절약"을 메인 숫자로 쓰고, 그 아래 주간/한달/연간을 나란히 보여준다. 네
    # 기간 모두 같은 SavingsCertification 테이블에서 조건부 합계로 한 번에
    # 구해서 왕복 쿼리를 늘리지 않는다.
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = (now - timedelta(days=now.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    year_start = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)

    def _sum_since(start: datetime):
        return func.coalesce(
            func.sum(case((SavingsCertification.created_at >= start, SavingsCertification.amount), else_=0)),
            0,
        )

    period_row = (
        await session.execute(
            select(
                _sum_since(today_start),
                _sum_since(week_start),
                _sum_since(month_start),
                _sum_since(year_start),
            ).where(SavingsCertification.user_id == user_id)
        )
    ).one()
    today_total, weekly_total, monthly_total, yearly_total = period_row

    summary = compute_savings_level(float(total), int(count), float(monthly_total))
    summary.today_saved = float(today_total)
    summary.weekly_saved = float(weekly_total)
    summary.yearly_saved = float(yearly_total)
    return summary


class LeaderboardService:
    async def weekly_top(self, region: str, limit: int = 10) -> list[dict]:
        raise NotImplementedError("길드·랭킹보드는 후속 단계에서 구현")


# --- 탐험가 칭호 (방문 매장 수 기반, 2026-08-13): "현장 활동 유도" 목적으로 도입.
# 절약금액 기반 레벨(SavingsSummary)과는 독립된 축이다 — 얼마나 아꼈는지가 아니라
# 얼마나 많은 실제 매장을 발품 팔아 발견했는지를 본다. StoreInterest는 (user_id,
# place_id)가 유일하므로, 한 사용자의 StoreInterest 행 개수 = 그 사용자가 실제로
# 방문 인증(발견하기)한 서로 다른 매장 수 — 그대로 세면 된다.
#
# 기존 절약 배지(my-badges, frontend/app.js)와 동일하게 영속 테이블 없이 매번
# 실시간으로 판정한다 — "언제 이 칭호를 받았는지"는 보여주지 않지만, 그 대신
# 마이그레이션/새 테이블이 필요 없다.
EXPLORER_TITLE_THRESHOLDS: list[tuple[int, str]] = [
    (0, "동네 초보"),
    (5, "동네 탐방러"),
    (10, "골목 탐험가"),
    (30, "발품왕"),
    (50, "동네 마스터"),
    (100, f"{BRAND_NAME} 전설"),
]


def _walk_count_thresholds(
    count: int, thresholds: list[tuple[int, str]]
) -> tuple[str, int | None, int | None]:
    """(칭호명, 다음 임계값, 다음까지 남은 수) — 발견/방문/추천 칭호 3종(2-2)이 모두
    "누적 카운트 임계값 사다리"라는 같은 모양이라 공용 로직으로 뽑았다."""
    count = max(count, 0)
    title = thresholds[0][1]
    next_threshold: int | None = None
    for i, (amount, name) in enumerate(thresholds):
        if count >= amount:
            title = name
            next_threshold = thresholds[i + 1][0] if i + 1 < len(thresholds) else None
        else:
            break
    remaining = None if next_threshold is None else max(next_threshold - count, 0)
    return title, next_threshold, remaining


@dataclass
class ExplorerSummary:
    discovered_place_count: int
    title: str
    next_threshold: int | None
    remaining_to_next: int | None


def compute_explorer_title(discovered_place_count: int) -> ExplorerSummary:
    discovered_place_count = max(discovered_place_count, 0)
    title, next_threshold, remaining = _walk_count_thresholds(
        discovered_place_count, EXPLORER_TITLE_THRESHOLDS
    )
    return ExplorerSummary(
        discovered_place_count=discovered_place_count,
        title=title,
        next_threshold=next_threshold,
        remaining_to_next=remaining,
    )


async def get_discovered_place_count(session: AsyncSession, user_id: str) -> int:
    return (
        await session.execute(
            select(func.count()).select_from(StoreInterest).where(StoreInterest.user_id == user_id)
        )
    ).scalar_one()


async def get_explorer_summary(session: AsyncSession, user_id: str) -> ExplorerSummary:
    count = await get_discovered_place_count(session, user_id)
    return compute_explorer_title(int(count))


# --- 방문 횟수 칭호 (2-2, 2026-08-13) --- 사용자 확정: "영수증 인증을 방문횟수로
# 해, 기존 영수증 인증은 숨기고 방문횟수에서 참고하도록". 즉 새 카운트 쿼리를
# 만들지 않고 이미 get_savings_summary가 계산해 두는 certification_count(실제
# 영수증/직접입력 인증 건수)를 그대로 칭호 사다리에 태운다.
VISIT_TITLE_THRESHOLDS: list[tuple[int, str]] = [
    (0, "방문 새내기"),
    (5, "단골 새싹"),
    (10, "동네 단골"),
    (30, "찐단골"),
    (50, "방문왕"),
    (100, f"{BRAND_NAME} 터줏대감"),
]


@dataclass
class VisitSummary:
    visit_count: int
    title: str
    next_threshold: int | None
    remaining_to_next: int | None


def compute_visit_title(visit_count: int) -> VisitSummary:
    visit_count = max(visit_count, 0)
    title, next_threshold, remaining = _walk_count_thresholds(visit_count, VISIT_TITLE_THRESHOLDS)
    return VisitSummary(
        visit_count=visit_count,
        title=title,
        next_threshold=next_threshold,
        remaining_to_next=remaining,
    )


# --- 추천 횟수 칭호 (2-2, 2026-08-13) --- PlaceRecommendation은 지금까지 매장별
# 카운트(그 매장이 몇 번 추천됐는지)만 쓰였고, 사용자별 누적 추천 수를 세는
# 쿼리는 없었다 — 새로 추가한다.
RECOMMEND_TITLE_THRESHOLDS: list[tuple[int, str]] = [
    (0, "추천 새내기"),
    (5, "입소문 메이커"),
    (10, "찐추천러"),
    (30, "추천왕"),
    (50, f"{BRAND_NAME} 인플루언서"),
    (100, "추천의 신"),
]


@dataclass
class RecommendSummary:
    recommend_count: int
    title: str
    next_threshold: int | None
    remaining_to_next: int | None


def compute_recommend_title(recommend_count: int) -> RecommendSummary:
    recommend_count = max(recommend_count, 0)
    title, next_threshold, remaining = _walk_count_thresholds(
        recommend_count, RECOMMEND_TITLE_THRESHOLDS
    )
    return RecommendSummary(
        recommend_count=recommend_count,
        title=title,
        next_threshold=next_threshold,
        remaining_to_next=remaining,
    )


async def get_recommended_place_count(session: AsyncSession, user_id: str) -> int:
    return (
        await session.execute(
            select(func.count())
            .select_from(PlaceRecommendation)
            .where(PlaceRecommendation.user_id == user_id)
        )
    ).scalar_one()


async def get_recommend_summary(session: AsyncSession, user_id: str) -> RecommendSummary:
    count = await get_recommended_place_count(session, user_id)
    return compute_recommend_title(int(count))
