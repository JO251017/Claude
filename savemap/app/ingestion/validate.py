from app.domain.enums import Layer
from app.ingestion.normalize import NormalizedOffer


class ValidationError(Exception):
    pass


def _valid_coords(lat: float | None, lng: float | None) -> bool:
    if lat is None or lng is None:
        return False
    return 33.0 <= lat <= 39.0 and 124.0 <= lng <= 132.0


def validate(offer: NormalizedOffer) -> NormalizedOffer:
    if not offer.place_name:
        raise ValidationError("place_name 누락")
    if not offer.title:
        raise ValidationError("title 누락")
    if not _valid_coords(offer.lat, offer.lng):
        raise ValidationError("좌표가 유효한 국내 범위를 벗어남")
    if offer.layer in (Layer.REGULAR, Layer.FLASH) and offer.expires_at is None:
        raise ValidationError(f"{offer.layer.value} 레이어는 expires_at 필수")
    if offer.layer == Layer.FLASH and offer.ttl_sec is None:
        raise ValidationError("flash 레이어는 ttl_sec 필수")
    return offer
