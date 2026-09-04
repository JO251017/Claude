from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import MissingReportImageError
from app.core.spatial import ewkt_point, to_h3
from app.domain.enums import Category, Layer, ReportStatus, SourceType, XpReason
from app.domain.offer import Offer
from app.domain.place import Place
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
    ) -> tuple[str, float, float] | tuple[None, None, None]:
        if lat is not None and lng is not None:
            return ewkt_point(lat, lng), lat, lng
        if not location_text:
            return None, None, None
        try:
            geo = await self.kakao.geocode(location_text)
        except Exception:
            # 위치는 부가 정보라 지오코딩 실패로 제보 저장 자체를 막지 않는다.
            return None, None, None
        return (ewkt_point(geo.lat, geo.lng), geo.lat, geo.lng) if geo else (None, None, None)

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
        place_name: str | None = None,
        regular_price: float | None = None,
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

        geom, resolved_lat, resolved_lng = await self._resolve_geom(lat, lng, ocr.location_text)

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

        # 제보 → 실제 게시(2026-08-18, "즉시 게시 + 기존 신뢰도 시스템에 편입") —
        # 예전엔 여기서 끝이라 제보가 지도에 영원히 안 떴다. 위치가 확보됐고
        # 매장명이 있으면 바로 Place+Offer를 만들어 검색에 노출한다. 신뢰도는
        # source=S4_REPORT(가장 낮은 우선순위, dedupe.py SOURCE_PRIORITY)로 시작해서
        # 이미 있는 "아직 있어요/없어졌어요" 검증·발견/방문 카운트가 자연스럽게
        # 신뢰도를 올리거나 내린다 — 관리자 승인 큐를 새로 만들지 않는다.
        if geom is not None and place_name:
            place = Place(
                name=place_name,
                address=None,
                owner_user_id=None,
                geom=geom,
                h3_r9=to_h3(resolved_lat, resolved_lng),
            )
            session.add(place)
            await session.flush()  # place.id를 얻기 위해 커밋 전에 flush

            # 정가(regular_price)가 있어야 진짜 할인액을 계산할 수 있다 — 없으면
            # 가격을 지어내지 않고 base_price/store_discount 둘 다 비워서 게시한다
            # (제목/카테고리만 있는 정보로도 발견 가치는 있다, 예: "여기 무료주차 돼요").
            base_price = None
            store_discount = None
            if regular_price is not None and ocr.price is not None and regular_price > ocr.price:
                base_price = regular_price
                store_discount = regular_price - ocr.price
            elif regular_price is None and ocr.price is not None and ocr.price > 0:
                # 정가 없이 가격 하나만 있으면 절약액 없이 가격 정보만 노출한다.
                base_price = ocr.price
                store_discount = 0.0

            offer = Offer(
                place_id=place.id,
                source=SourceType.S4_REPORT,
                layer=Layer.REGULAR,
                category=category_override or ocr.category or Category.DISCOUNT,
                title=ocr.title or place_name,
                base_price=base_price,
                store_discount=store_discount,
            )
            session.add(offer)
            await session.flush()

            report.place_id = place.id
            report.offer_id = offer.id
            report.status = ReportStatus.VERIFIED

        await session.commit()
        await session.refresh(report)

        await award_xp(session, user_id, XpReason.VALID_REPORT)
        return report
