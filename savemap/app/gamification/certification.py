from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.errors import CertificationNotSupportedError, OfferPublicNotFoundError
from app.domain.enums import CERTIFICATION_CONFIDENCE, CertificationMethod
from app.domain.offer import Offer
from app.domain.savings import SavingsCertification
from app.gamification.service import SavingsSummary, get_savings_summary
from app.integrations.gemini import GeminiVisionClient


async def certify_savings(
    session: AsyncSession,
    user_id: str,
    offer_id: int,
    method: CertificationMethod,
    actual_price: float | None = None,
    receipt_image_url: str | None = None,
    gemini: GeminiVisionClient | None = None,
) -> tuple[SavingsCertification, SavingsSummary]:
    stmt = select(Offer).where(Offer.id == offer_id).options(selectinload(Offer.place))
    offer = (await session.execute(stmt)).scalar_one_or_none()
    if offer is None:
        raise OfferPublicNotFoundError()
    if offer.base_price is None:
        raise CertificationNotSupportedError()

    base_price = float(offer.base_price)
    confidence = CERTIFICATION_CONFIDENCE[method]

    if method == CertificationMethod.RECEIPT and receipt_image_url:
        ocr = await (gemini or GeminiVisionClient()).extract_from_image(receipt_image_url)
        if ocr.price is not None:
            actual_price = ocr.price
        # OCR이 가격을 못 읽으면 사용자가 입력한 actual_price(있는 경우)로 폴백한다.

    if actual_price is None:
        # 간편 인증: 사용자가 가격을 다시 입력하지 않아도, 매장이 등록한 할인액을
        # 그대로 적용해 "정상가 - 할인액 = 실제 지불가"로 취급한다.
        actual_price = base_price - float(offer.store_discount or 0)

    amount = max(base_price - actual_price, 0.0)

    cert = SavingsCertification(
        user_id=user_id,
        offer_id=offer.id,
        place_name=offer.place.name if offer.place else "알 수 없는 매장",
        base_price=base_price,
        actual_price=actual_price,
        amount=amount,
        method=method,
        confidence=confidence,
    )
    session.add(cert)
    await session.commit()
    await session.refresh(cert)

    summary = await get_savings_summary(session, user_id)
    return cert, summary
