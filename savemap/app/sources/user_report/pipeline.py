from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import MissingReportImageError
from app.core.spatial import ewkt_point
from app.domain.enums import Category, ReportStatus, XpReason
from app.domain.report import UserReport
from app.gamification.service import award_xp
from app.integrations.gemini import GeminiVisionClient, OcrResult
from app.integrations.kakao import KakaoClient


class ReportPipeline:
    def __init__(self, gemini: GeminiVisionClient | None = None, kakao: KakaoClient | None = None):
        self.gemini = gemini or GeminiVisionClient()
        self.kakao = kakao or KakaoClient()

    async def _resolve_geom(
        self, lat: float | None, lng: float | None, location_text: str | None
    ) -> str | None:
        if lat is not None and lng is not None:
            return ewkt_point(lat, lng)
        if not location_text:
            return None
        try:
            geo = await self.kakao.geocode(location_text)
        except Exception:
            # 위치는 부가 정보라 지오코딩 실패로 제보 저장 자체를 막지 않는다.
            return None
        return ewkt_point(geo.lat, geo.lng) if geo else None

    async def ingest(
        self,
        session: AsyncSession,
        user_id: str,
        image_url: str,
        lat: float | None = None,
        lng: float | None = None,
        title_override: str | None = None,
        price_override: float | None = None,
        category_override: Category | None = None,
    ) -> UserReport:
        if not image_url:
            raise MissingReportImageError()

        has_override = (
            title_override is not None or price_override is not None or category_override is not None
        )
        if has_override:
            # POST /v1/reports/analyze 로 이미 분석 → 사용자가 확인/수정한 값이므로 재분석하지 않는다.
            ocr = OcrResult(
                raw_text="",
                price=price_override,
                title=title_override,
                category=category_override,
            )
        else:
            ocr = await self.gemini.extract_from_image(image_url)

        geom = await self._resolve_geom(lat, lng, ocr.location_text)

        report = UserReport(
            user_id=user_id,
            image_url=image_url,
            ocr_json={
                "raw_text": ocr.raw_text,
                "price": ocr.price,
                "title": ocr.title,
                "location_text": ocr.location_text,
            },
            ai_category=ocr.category,
            status=ReportStatus.PENDING,
            geom=geom,
        )
        session.add(report)
        await session.commit()
        await session.refresh(report)

        await award_xp(session, user_id, XpReason.VALID_REPORT)
        return report
