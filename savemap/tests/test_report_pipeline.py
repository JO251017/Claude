import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from app.domain.enums import Category, ReportStatus, SourceType
from app.domain.offer import Offer
from app.domain.place import Place
from app.sources.user_report.pipeline import ReportPipeline


def _make_session():
    session = MagicMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    session.flush = AsyncMock()
    return session


def test_override_skips_gemini_reextraction():
    gemini = MagicMock()
    gemini.extract_from_image = AsyncMock()
    pipeline = ReportPipeline(gemini=gemini, kakao=MagicMock())
    session = _make_session()

    with patch("app.sources.user_report.pipeline.award_xp", new=AsyncMock()):
        report = asyncio.run(
            pipeline.ingest(
                session,
                "user-1",
                "https://example.com/a.jpg",
                lat=36.99,
                lng=127.11,
                title_override="삼겹살 반값",
                price_override=8000,
                category_override=Category.DISCOUNT,
            )
        )

    gemini.extract_from_image.assert_not_called()
    assert report.ocr_json["title"] == "삼겹살 반값"
    assert report.ocr_json["price"] == 8000
    assert report.ai_category == Category.DISCOUNT


def test_no_override_still_calls_gemini():
    gemini = MagicMock()
    ocr_result = MagicMock(
        raw_text="raw", price=5000, title="AI 제목", category=Category.FREE, location_text=None
    )
    gemini.extract_from_image = AsyncMock(return_value=ocr_result)
    pipeline = ReportPipeline(gemini=gemini, kakao=MagicMock())
    session = _make_session()

    with patch("app.sources.user_report.pipeline.award_xp", new=AsyncMock()):
        report = asyncio.run(
            pipeline.ingest(session, "user-1", "https://example.com/a.jpg", lat=36.99, lng=127.11)
        )

    gemini.extract_from_image.assert_called_once_with("https://example.com/a.jpg")
    assert report.ocr_json["title"] == "AI 제목"


def _added_instances(session, cls):
    return [c.args[0] for c in session.add.call_args_list if isinstance(c.args[0], cls)]


# --- 제보 → 실제 Place/Offer 게시(2026-08-18, "즉시 게시 + 기존 신뢰도 시스템에
# 편입") --- 예전엔 UserReport를 PENDING으로 저장만 하고 끝이라 지도에 영원히
# 안 떴다. 위치(geom)와 매장명이 둘 다 있어야 실제로 게시된다.


def test_ingest_with_location_and_place_name_publishes_offer():
    pipeline = ReportPipeline(gemini=MagicMock(), kakao=MagicMock())
    session = _make_session()

    with patch("app.sources.user_report.pipeline.award_xp", new=AsyncMock()):
        report = asyncio.run(
            pipeline.ingest(
                session,
                "user-1",
                "https://example.com/a.jpg",
                lat=36.99,
                lng=127.11,
                title_override="삼겹살 20% 할인",
                price_override=8000,
                category_override=Category.DISCOUNT,
                place_name="늘푸른정육점",
                regular_price=10000,
            )
        )

    places = _added_instances(session, Place)
    offers = _added_instances(session, Offer)
    assert len(places) == 1 and places[0].name == "늘푸른정육점"
    assert len(offers) == 1
    offer = offers[0]
    assert offer.source == SourceType.S4_REPORT
    assert offer.category == Category.DISCOUNT
    # 정가(10000) - 할인가(8000) = 실제 절약 2000원. 지어낸 값이 아니라 사용자가
    # 준 두 숫자의 차이 그대로다.
    assert offer.base_price == 10000
    assert offer.store_discount == 2000
    assert report.status == ReportStatus.VERIFIED


def test_ingest_without_regular_price_does_not_fabricate_discount():
    pipeline = ReportPipeline(gemini=MagicMock(), kakao=MagicMock())
    session = _make_session()

    with patch("app.sources.user_report.pipeline.award_xp", new=AsyncMock()):
        asyncio.run(
            pipeline.ingest(
                session,
                "user-1",
                "https://example.com/a.jpg",
                lat=36.99,
                lng=127.11,
                title_override="아메리카노",
                price_override=4500,
                category_override=Category.DISCOUNT,
                place_name="행복카페",
                # regular_price 없음 — 정가를 모르니 할인액을 지어내면 안 된다.
            )
        )

    offer = _added_instances(session, Offer)[0]
    assert offer.base_price == 4500
    assert offer.store_discount == 0.0


def test_ingest_without_place_name_stays_pending():
    # 위치는 있어도 매장명이 없으면 Place를 못 만든다(Place.name은 NOT NULL) —
    # 제보 자체는 저장되지만 지도에는 아직 안 뜬다.
    pipeline = ReportPipeline(gemini=MagicMock(), kakao=MagicMock())
    session = _make_session()

    with patch("app.sources.user_report.pipeline.award_xp", new=AsyncMock()):
        report = asyncio.run(
            pipeline.ingest(
                session,
                "user-1",
                "https://example.com/a.jpg",
                lat=36.99,
                lng=127.11,
                title_override="아메리카노",
                price_override=4500,
                category_override=Category.DISCOUNT,
            )
        )

    assert _added_instances(session, Place) == []
    assert _added_instances(session, Offer) == []
    assert report.status == ReportStatus.PENDING
    assert report.place_id is None
    assert report.offer_id is None


def test_ingest_without_location_stays_pending_even_with_place_name():
    pipeline = ReportPipeline(gemini=MagicMock(), kakao=MagicMock())
    session = _make_session()

    with patch("app.sources.user_report.pipeline.award_xp", new=AsyncMock()):
        report = asyncio.run(
            pipeline.ingest(
                session,
                "user-1",
                "https://example.com/a.jpg",
                title_override="아메리카노",
                price_override=4500,
                category_override=Category.DISCOUNT,
                place_name="행복카페",
            )
        )

    assert _added_instances(session, Place) == []
    assert report.status == ReportStatus.PENDING
