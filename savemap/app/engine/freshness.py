from datetime import UTC, datetime

from app.core.config import settings

# 가격/검증 데이터가 얼마나 최신인지 다단계로 분류한다 — vNext 지시서(2026-08-31)
# "6. 가격 최신성 시스템". savings_report.py(신뢰도 점수)와 ranker.py(검색 랭킹)
# 양쪽이 같은 기준을 써야 "카드엔 오래됐다고 뜨는데 순위는 그대로"인 모순이 안
# 생기므로 여기 한 곳에만 둔다.
#
# "unknown"(확인 시각 정보 자체가 없음)과 "expired"(확인은 했는데 오래됨)는 다른
# 사실이다 — 모른다는 것과 오래됐다는 것을 같은 취급으로 뭉개지 않는다(지어내지
# 않기: last_verified_at이 없는 걸 "최근에 확인 안 됨"으로 단정하지 않는다).

FRESHNESS_LABELS: dict[str, str] = {
    "unknown": "확인 시각 정보 없음",
    "fresh": "매우 최신",
    "normal": "최신",
    "stale": "오래됨",
    "expired": "정보가 오래돼 확인이 필요해요",
}


def freshness_tier(
    last_verified_at: datetime | None, *, now: datetime | None = None
) -> tuple[str, int | None]:
    """(tier, days_since_verified)를 반환한다. last_verified_at이 없으면
    ("unknown", None)."""
    if last_verified_at is None:
        return "unknown", None
    now = now or datetime.now(UTC)
    days = (now - last_verified_at).days
    if days <= settings.price_freshness_fresh_days:
        return "fresh", days
    if days <= settings.price_freshness_normal_days:
        return "normal", days
    if days <= settings.price_freshness_stale_days:
        return "stale", days
    return "expired", days
