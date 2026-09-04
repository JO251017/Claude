from math import asin, cos, radians, sin, sqrt

from app.domain.enums import SOURCE_PRIORITY
from app.ingestion.normalize import NormalizedOffer

DUP_DISTANCE_M = 50.0


def _haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6371000.0
    dlat = radians(lat2 - lat1)
    dlng = radians(lng2 - lng1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlng / 2) ** 2
    return 2 * r * asin(sqrt(a))


def _same_offer(a: NormalizedOffer, b: NormalizedOffer) -> bool:
    if a.category != b.category:
        return False
    if None in (a.lat, a.lng, b.lat, b.lng):
        return a.place_name == b.place_name and a.title == b.title
    return _haversine_m(a.lat, a.lng, b.lat, b.lng) <= DUP_DISTANCE_M and a.title == b.title


def dedupe(offers: list[NormalizedOffer]) -> list[NormalizedOffer]:
    kept: list[NormalizedOffer] = []
    for offer in offers:
        match_idx = next((i for i, k in enumerate(kept) if _same_offer(k, offer)), None)
        if match_idx is None:
            kept.append(offer)
            continue
        if SOURCE_PRIORITY[offer.source] < SOURCE_PRIORITY[kept[match_idx].source]:
            kept[match_idx] = offer
    return kept
