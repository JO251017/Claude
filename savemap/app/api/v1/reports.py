from fastapi import APIRouter
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import SessionDep, UserDep
from app.api.schemas.report import ReportCreate, ReportResponse
from app.sources.user_report.pipeline import ReportPipeline

router = APIRouter(tags=["reports"])


@router.post("/reports", response_model=ReportResponse, status_code=201)
async def submit_report(
    payload: ReportCreate,
    user_id: str = UserDep,
    session: AsyncSession = SessionDep,
) -> ReportResponse:
    report = await ReportPipeline().ingest(
        session, user_id, payload.image_url, payload.lat, payload.lng
    )
    ocr = report.ocr_json or {}
    return ReportResponse(
        id=report.id,
        user_id=report.user_id,
        image_url=report.image_url,
        ai_category=report.ai_category,
        status=report.status,
        ocr_price=ocr.get("price"),
        ocr_title=ocr.get("title"),
        has_location=report.geom is not None,
    )
