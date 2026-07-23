from fastapi import APIRouter
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import SessionDep, UserDep
from app.api.schemas.report import ReportCreate, ReportResponse
from app.sources.user_report.service import create_report

router = APIRouter(tags=["reports"])


@router.post("/reports", response_model=ReportResponse, status_code=201)
async def submit_report(
    payload: ReportCreate,
    user_id: str = UserDep,
    session: AsyncSession = SessionDep,
) -> ReportResponse:
    report = await create_report(session, user_id, payload.image_url)
    return ReportResponse(
        id=report.id,
        user_id=report.user_id,
        image_url=report.image_url,
        ai_category=report.ai_category,
        status=report.status,
    )
