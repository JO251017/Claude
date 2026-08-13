from datetime import datetime, timezone

from app.domain.enums import Category, Layer, RouteActivity
from app.domain.offer import Offer
from app.domain.place import Place
from app.engine.activity_classifier import classify_activity

MVP_LAYERS = (Layer.CORE_BASE, Layer.REGULAR)


def rule_filter(
    rows: list[tuple[Offer, Place, float]],
    category: Category | None = None,
    now: datetime | None = None,
    mvp_only: bool = True,
    activities: list[RouteActivity] | None = None,
) -> list[tuple[Offer, Place, float]]:
    """activities: 비어있지 않으면 place.category_name에서 분류한 활동이 그 목록에
    속하는 행만 남긴다(AI 절약 플랜의 "무엇을 할까요?" 선택, 2026-08-13). 미분류
    (None) 매장은 목록에 넣지 않는다 — 활동을 지정했는데 뭔지 모르는 곳을 섞어
    보여주면 사용자가 고른 조건과 안 맞는 결과가 나온다. /search는 이 파라미터를
    넘기지 않아 기존 동작 그대로다."""
    now = now or datetime.now(timezone.utc)
    result: list[tuple[Offer, Place, float]] = []
    for offer, place, distance in rows:
        if mvp_only and offer.layer not in MVP_LAYERS:
            continue
        if category is not None and offer.category != category:
            continue
        if activities and classify_activity(place.category_name) not in activities:
            continue
        if offer.expires_at is not None and offer.expires_at < now:
            continue
        if offer.valid_from is not None and offer.valid_from > now:
            continue
        result.append((offer, place, distance))
    return result
