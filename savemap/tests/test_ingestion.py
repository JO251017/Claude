import pytest

from app.domain.enums import Category, Layer, SourceType
from app.ingestion.dedupe import dedupe
from app.ingestion.normalize import NormalizedOffer, map_category
from app.ingestion.validate import ValidationError, validate


def test_map_category_aliases():
    assert map_category("무료 주차") == Category.FREE_PARKING
    assert map_category("지역화폐") == Category.LOCAL_BENEFIT
    assert map_category("알수없음") == Category.DISCOUNT


def _offer(source: SourceType, lat=36.99, lng=127.11, title="세일") -> NormalizedOffer:
    return NormalizedOffer(
        source=source,
        layer=Layer.CORE_BASE,
        category=Category.FREE_PARKING,
        place_name="시청주차장",
        title=title,
        lat=lat,
        lng=lng,
    )


def test_validate_rejects_bad_coords():
    bad = _offer(SourceType.S1_PUBLIC, lat=0.0, lng=0.0)
    with pytest.raises(ValidationError):
        validate(bad)


def test_validate_requires_expiry_for_flash():
    o = _offer(SourceType.S3_MERCHANT)
    o.layer = Layer.FLASH
    with pytest.raises(ValidationError):
        validate(o)


def test_dedupe_keeps_higher_priority_source():
    public = _offer(SourceType.S1_PUBLIC)
    report = _offer(SourceType.S4_REPORT)
    kept = dedupe([report, public])
    assert len(kept) == 1
    assert kept[0].source == SourceType.S1_PUBLIC
