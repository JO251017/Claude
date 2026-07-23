from fastapi import APIRouter

router = APIRouter(tags=["merchant"], prefix="/merchant")


@router.post("/offers", status_code=501)
async def create_merchant_offer() -> dict:
    return {
        "detail": "사업자 콘솔 CRUD는 인증·권한 모델 확정 후 구현 예정",
        "status": "not_implemented",
    }
