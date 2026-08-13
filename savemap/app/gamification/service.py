from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import XP_REWARD, XpReason
from app.domain.savings import SavingsCertification
from app.domain.xp import XpLedger

# 예전엔 여기에 XP 총량 기반 레벨링(compute_level/XP_PER_LEVEL/LEVEL_TITLES)이
# 있었다 — "구조 재설계 제안서"(2026-08-13) §1 진단에서, 프론트가 실제로는
# compute_savings_level()(실제 인증된 누적 절약금액 기반)만 쓰고 이쪽은 어디서도
# 호출되지 않는 죽은 코드라는 게 확인돼 제거했다(GET /me/xp 엔드포인트도 함께
# 제거). xp_ledger/award_xp 자체는 그대로 남는다 — "캐릭터 레벨"이 아니라 향후
# 배지 등 활동 지표 전용으로 역할이 좁혀졌을 뿐이다.


async def award_xp(session: AsyncSession, user_id: str, reason: XpReason) -> int:
    delta = XP_REWARD[reason]
    session.add(XpLedger(user_id=user_id, delta=delta, reason=reason))
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

    month_start = datetime.now(timezone.utc).replace(
        day=1, hour=0, minute=0, second=0, microsecond=0
    )
    monthly_total = (
        await session.execute(
            select(func.coalesce(func.sum(SavingsCertification.amount), 0)).where(
                SavingsCertification.user_id == user_id,
                SavingsCertification.created_at >= month_start,
            )
        )
    ).scalar_one()

    return compute_savings_level(float(total), int(count), float(monthly_total))


class LeaderboardService:
    async def weekly_top(self, region: str, limit: int = 10) -> list[dict]:
        raise NotImplementedError("길드·랭킹보드는 후속 단계에서 구현")
