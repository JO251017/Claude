from fastapi import APIRouter
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import RequireUserDep, SessionDep
from app.api.schemas.verification import (
    OfferVerificationCreate,
    OfferVerificationResponse,
    VerificationCreate,
    VerificationResponse,
)
from app.sources.user_verification.service import submit_offer_verification, submit_verification

router = APIRouter(tags=["verifications"])

# 보안 점검(vNext, 2026-08-31)에서 발견: 이 두 엔드포인트만 UserDep(비로그인이면
# user_id="anonymous"로 통과)을 썼다 — 이 저장소의 다른 모든 상태변경 엔드포인트
# (recommendations/status-updates/menu-reports/certify/exchange/merchant)는 전부
# RequireUserDep(비로그인이면 401)이다. verify는 매 호출마다 새 검증 행을 쌓고
# trust_score를 그 자리에서 재계산해 검색 랭킹(rank_trust_weight=0.25)에 직접
# 반영되는데, 로그인 없이 호출 가능하면 익명으로 무제한 반복 호출해 아무 오퍼의
# 신뢰도든 조작할 수 있었다 — 다른 엔드포인트와 같은 수준으로 맞춘다.


@router.post("/verifications", response_model=VerificationResponse, status_code=201)
async def create_verification(
    payload: VerificationCreate,
    user_id: str = RequireUserDep,
    session: AsyncSession = SessionDep,
) -> VerificationResponse:
    score = await submit_verification(
        session, payload.report_id, user_id, payload.verdict, payload.weight
    )
    return VerificationResponse(report_id=payload.report_id, trust_score=score)


@router.post("/offers/{offer_id}/verify", response_model=OfferVerificationResponse, status_code=201)
async def create_offer_verification(
    offer_id: int,
    payload: OfferVerificationCreate,
    user_id: str = RequireUserDep,
    session: AsyncSession = SessionDep,
) -> OfferVerificationResponse:
    score, count, last_at = await submit_offer_verification(
        session, offer_id, user_id, payload.verdict
    )
    return OfferVerificationResponse(
        offer_id=offer_id, trust_score=score, verification_count=count, last_verified_at=last_at
    )
