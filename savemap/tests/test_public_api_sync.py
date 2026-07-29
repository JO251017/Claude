import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from app.domain.enums import Category, Layer, SourceType
from app.ingestion.normalize import NormalizedOffer
from app.sources.public_api.service import sync_all_public_sources


def _valid_offer() -> NormalizedOffer:
    return NormalizedOffer(
        source=SourceType.S1_PUBLIC,
        layer=Layer.CORE_BASE,
        category=Category.FREE_PARKING,
        place_name="시청 공영주차장",
        title="상시 무료 개방",
        lat=36.99,
        lng=127.11,
    )


def _invalid_offer() -> NormalizedOffer:
    # 좌표가 국내 범위를 벗어나 validate()에서 걸러져야 한다.
    return NormalizedOffer(
        source=SourceType.S1_PUBLIC,
        layer=Layer.CORE_BASE,
        category=Category.FREE_PARKING,
        place_name="잘못된 좌표",
        title="테스트",
        lat=0.0,
        lng=0.0,
    )


def test_sync_skips_not_implemented_adapters_and_upserts_valid_offers():
    working_adapter_cls = MagicMock()
    working_adapter_cls.__name__ = "FakeParkingAdapter"
    working_adapter = MagicMock()
    working_adapter.collect = AsyncMock(return_value=[_valid_offer(), _invalid_offer()])
    working_adapter_cls.return_value = working_adapter

    stub_adapter_cls = MagicMock()
    stub_adapter_cls.__name__ = "FakeStubAdapter"
    stub_adapter = MagicMock()
    stub_adapter.collect = AsyncMock(side_effect=NotImplementedError("스펙 미확인"))
    stub_adapter_cls.return_value = stub_adapter

    session = MagicMock()

    with (
        patch("app.sources.public_api.service.ADAPTERS", [working_adapter_cls, stub_adapter_cls]),
        patch("app.sources.public_api.service.upsert_offers", new=AsyncMock(return_value=1)) as mock_upsert,
    ):
        result = asyncio.run(sync_all_public_sources(session))

    assert result["collected"] == 2
    assert result["invalid"] == 1
    assert result["inserted"] == 1
    assert result["skipped_adapters"] == [{"adapter": "FakeStubAdapter", "reason": "스펙 미확인"}]

    upserted_offers = mock_upsert.call_args.args[1]
    assert len(upserted_offers) == 1
    assert upserted_offers[0].place_name == "시청 공영주차장"
