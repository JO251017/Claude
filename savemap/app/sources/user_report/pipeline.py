from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import MissingReportImageError
from app.core.spatial import ewkt_point, to_h3
from app.domain.enums import ReportStatus
from app.domain.report import UserReport
from app.integrations.gemini import GeminiVisionClient
from app.integrations.kakao import KakaoClient


class ReportPipeline:
    def __init__(self, gemini: GeminiVisionClient | None = None, kakao: KakaoClient | None = None):
        self.gemini = gemini or GeminiVisionClient()
        self.kakao = kakao or KakaoClient()

    async def ingest(
        self, session: AsyncSession, user_id: str, image_url: str
    ) -> UserReport:
        if not image_url:
            raise MissingReportImageError()

        ocr = await self.gemini.extract_from_image(image_url)
        geo = await self.kakao.geocode(ocr.title or "")

        report = UserReport(
            user_id=user_id,
            image_url=image_url,
            ocr_json={"raw_text": ocr.raw_text, "price": ocr.price, "title": ocr.title},
            ai_category=ocr.category,
            status=ReportStatus.PENDING,
            geom=ewkt_point(geo.lat, geo.lng) if geo else None,
        )
        session.add(report)
        await session.commit()
        return report
