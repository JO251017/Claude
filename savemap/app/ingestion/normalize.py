from dataclasses import dataclass, field
from datetime import datetime

from app.domain.enums import Category, Layer, SourceType


@dataclass
class NormalizedOffer:
    source: SourceType
    layer: Layer
    category: Category
    place_name: str
    title: str
    lat: float | None = None
    lng: float | None = None
    address: str | None = None
    base_price: float | None = None
    store_discount: float | None = None
    valid_from: datetime | None = None
    expires_at: datetime | None = None
    ttl_sec: int | None = None
    external_ref: str | None = None
    extra: dict = field(default_factory=dict)


_CATEGORY_ALIASES: list[tuple[str, Category]] = [
    ("주차", Category.FREE_PARKING),
    ("지역화폐", Category.LOCAL_BENEFIT),
    ("지역혜택", Category.LOCAL_BENEFIT),
    ("마감", Category.CLOSING_SOON),
    ("무료", Category.FREE),
    ("할인", Category.DISCOUNT),
]


def map_category(raw: str) -> Category:
    key = raw.replace(" ", "")
    for alias, category in _CATEGORY_ALIASES:
        if alias in key:
            return category
    return Category.DISCOUNT


def normalize(raw: dict, source: SourceType, layer: Layer) -> NormalizedOffer:
    return NormalizedOffer(
        source=source,
        layer=layer,
        category=map_category(str(raw.get("category", ""))),
        place_name=str(raw.get("place_name", "")).strip(),
        title=str(raw.get("title", "")).strip(),
        lat=raw.get("lat"),
        lng=raw.get("lng"),
        address=raw.get("address"),
        base_price=raw.get("base_price"),
        store_discount=raw.get("store_discount"),
        valid_from=raw.get("valid_from"),
        expires_at=raw.get("expires_at"),
        ttl_sec=raw.get("ttl_sec"),
        external_ref=raw.get("external_ref"),
    )
