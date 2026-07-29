import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from app.domain.enums import Category
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
