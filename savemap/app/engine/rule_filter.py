from datetime import datetime, timezone

from app.domain.enums import Category, Layer
from app.domain.offer import Offer
from app.domain.place import Place

MVP_LAYERS = (Layer.CORE_BASE, Layer.REGULAR)


def rule_filter(
    rows: list[tuple[Offer, Place, float]],
    category: Category | None = None,
    now: datetime | None = None,
    mvp_only: bool = True,
) -> list[tuple[Offer, Place, float]]:
    now = now or datetime.now(timezone.utc)
    result: list[tuple[Offer, Place, float]] = []
    for offer, place, distance in rows:
        if mvp_only and offer.layer not in MVP_LAYERS:
            continue
        if category is not None and offer.category != category:
            continue
        if offer.expires_at is not None and offer.expires_at < now:
            continue
        if offer.valid_from is not None and offer.valid_from > now:
            continue
        result.append((offer, place, distance))
    return result
