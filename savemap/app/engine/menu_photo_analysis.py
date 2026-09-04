import uuid

from fastapi import UploadFile

from app.api.schemas.merchant import MenuItemAnalyzeResponse, MenuItemGuessItem
from app.core.errors import InvalidImageError
from app.integrations.gemini import GeminiVisionClient
from app.integrations.supabase_storage import SupabaseStorageClient

MAX_UPLOAD_BYTES = 10 * 1024 * 1024


async def analyze_menu_photo_upload(image: UploadFile) -> MenuItemAnalyzeResponse:
    """메뉴판 사진 한 장에서 AI가 메뉴명·가격을 통째로 읽어온다. 사업자 콘솔
    (app/api/v1/merchant.py, 소유권 확인된 사업자만)과 발견된 매장 제보
    (app/api/v1/places.py, 로그인만 하면 누구나 — 2026-08-13 사용자 지시로 열림)
    양쪽에서 완전히 같은 로직을 쓰던 걸 여기 하나로 모았다. 인증 수준(사업자 인증
    vs 로그인만)은 각 라우터가 알아서 게이트하고, 이 함수는 순수 "사진 → 메뉴 추측
    목록" 변환만 담당한다. DB에는 저장하지 않는다(사용자 확인 전 단계)."""
    content_type = image.content_type or ""
    if not content_type.startswith("image/"):
        raise InvalidImageError(f"이미지 파일이 아닙니다 (받은 형식: {content_type or '알 수 없음'})")

    content = await image.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise InvalidImageError("사진 용량이 너무 큽니다 (최대 10MB)")

    ext = (content_type.split("/")[-1] or "jpg").split(";")[0]
    path = f"{uuid.uuid4().hex}.{ext}"
    image_url = await SupabaseStorageClient().upload(path, content, content_type)

    guesses = await GeminiVisionClient().extract_menu_items(image_url)

    return MenuItemAnalyzeResponse(
        image_url=image_url,
        items=[MenuItemGuessItem(name=g.name, price=g.price) for g in guesses],
    )
