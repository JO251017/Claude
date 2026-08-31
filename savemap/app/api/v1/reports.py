import uuid

from fastapi import APIRouter, File, Form, UploadFile

from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import RequireUserDep, SessionDep
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
    user_id: str = RequireUserDep,
) -> ReportAnalyzeResponse:
    """사진을 업로드하고 AI가 정보를 추출한다. DB에는 저장하지 않는다(사용자 확인 전 단계).

    user_id는 결과에 쓰이지 않고 로그인 게이트로만 쓴다(app/api/v1/merchant.py의
    analyze_menu_photo, app/api/v1/places.py의 analyze_menu_report_photo와 동일한
    패턴) — 보안 점검(2026-08-31)에서 발견: 이 엔드포인트만 로그인 없이도 호출
    가능해서, 비용이 드는 Gemini Vision/Supabase Storage 업로드를 익명으로
    무제한 호출할 수 있었다."""
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
        location_text=ocr.location_text,
    )


@router.get("/reports/recent", response_model=list[RecentReportItem])
async def recent_reports(session: AsyncSession = SessionDep) -> list[RecentReportItem]:
    reports = await report_service.list_recent(session, limit=20)
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
    user_id: str = RequireUserDep,
    session: AsyncSession = SessionDep,
) -> ReportResponse:
    # 보안 점검(2026-08-31)에서 발견: 예전엔 UserDep(비로그인이면 "anonymous"로
    # 통과)이라 로그인 없이도 공개 지도에 Place/Offer가 새로 만들어질 수 있었다 —
    # 이 저장소의 다른 모든 쓰기 엔드포인트와 같은 수준(RequireUserDep)으로 맞춘다.
    report = await ReportPipeline().ingest(
        session,
        user_id,
        payload.image_url,
        payload.lat,
        payload.lng,
        title_override=payload.title,
        price_override=payload.price,
        category_override=payload.category,
        place_name=payload.place_name,
        regular_price=payload.regular_price,
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
        place_id=report.place_id,
        offer_id=report.offer_id,
    )
