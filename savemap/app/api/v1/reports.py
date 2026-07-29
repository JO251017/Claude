import uuid

from fastapi import APIRouter, File, Form, UploadFile

from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import SessionDep, UserDep
from app.api.schemas.report import (
    RecentReportItem,
    ReportAnalyzeResponse,
    ReportCreate,
    ReportResponse,
)
from app.core.errors import InvalidImageError
from app.integrations.gemini import GeminiVisionClient
from app.integrations.supabase_storage import SupabaseStorageClient
from app.sources.user_report import service as report_service
from app.sources.user_report.pipeline import ReportPipeline

router = APIRouter(tags=["reports"])

MAX_UPLOAD_BYTES = 10 * 1024 * 1024


@router.post("/reports/analyze", response_model=ReportAnalyzeResponse)
async def analyze_report_photo(
    image: UploadFile = File(...),
    lat: float | None = Form(default=None),
    lng: float | None = Form(default=None),
) -> ReportAnalyzeResponse:
    """사진을 업로드하고 AI가 정보를 추출한다. DB에는 저장하지 않는다(사용자 확인 전 단계)."""
    content_type = image.content_type or ""
    if not content_type.startswith("image/"):
        raise InvalidImageError(f"이미지 파일이 아닙니다 (받은 형식: {content_type or '알 수 없음'})")

    content = await image.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise InvalidImageError("사진 용량이 너무 큽니다 (최대 10MB)")

    ext = (content_type.split("/")[-1] or "jpg").split(";")[0]
    path = f"{uuid.uuid4().hex}.{ext}"
    image_url = await SupabaseStorageClient().upload(path, content, content_type)

    ocr = await GeminiVisionClient().extract_from_image(image_url)

    return ReportAnalyzeResponse(
        image_url=image_url,
        ai_category=ocr.category,
        ocr_price=ocr.price,
        ocr_title=ocr.title,
        lat=lat,
        lng=lng,
    )


@router.get("/reports/recent", response_model=list[RecentReportItem])
async def recent_reports(session: AsyncSession = SessionDep) -> list[RecentReportItem]:
    reports = await report_service.list_pending(session, limit=20)
    return [
        RecentReportItem(
            id=r.id,
            ai_category=r.ai_category,
            status=r.status,
            ocr_title=(r.ocr_json or {}).get("title"),
            ocr_price=(r.ocr_json or {}).get("price"),
        )
        for r in reports
    ]


@router.post("/reports", response_model=ReportResponse, status_code=201)
async def submit_report(
    payload: ReportCreate,
    user_id: str = UserDep,
    session: AsyncSession = SessionDep,
) -> ReportResponse:
    report = await ReportPipeline().ingest(
        session,
        user_id,
        payload.image_url,
        payload.lat,
        payload.lng,
        title_override=payload.title,
        price_override=payload.price,
        category_override=payload.category,
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
