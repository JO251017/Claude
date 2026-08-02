from fastapi import APIRouter, File, Header, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import SessionDep
from app.core.config import settings
from app.core.errors import AuthenticationRequiredError, InvalidCsvError
from app.sources.public_api.good_price import (
    parse_csv_bytes,
    parse_xls_bytes,
    store_rows,
    sync_good_price_stores,
)
from app.sources.public_api.service import sync_all_public_sources

router = APIRouter(tags=["admin"], prefix="/admin")


@router.post("/sync/public-data")
async def trigger_public_data_sync(
    x_admin_key: str | None = Header(default=None),
    session: AsyncSession = SessionDep,
) -> dict:
    """공공데이터 수집을 즉시 실행한다. Celery worker가 없는 배포 환경(현재 Render 무료 플랜)에서
    수동/크론으로 동기화를 트리거하기 위한 엔드포인트. ADMIN_SYNC_KEY 미설정 시 항상 거부된다."""
    if not settings.admin_sync_key or x_admin_key != settings.admin_sync_key:
        raise AuthenticationRequiredError("관리자 키가 필요합니다 (X-Admin-Key 헤더)")
    return await sync_all_public_sources(session)


@router.post("/sync/good-price-stores")
async def trigger_good_price_sync(
    region: str | None = Query(default=None, description="주소에 포함될 지역명 (예: 평택). 비우면 전국"),
    offset: int = Query(default=0, ge=0, description="이 지역 매칭 결과 중 몇 번째부터 처리할지"),
    limit: int | None = Query(
        default=None, ge=1, description="한 번에 몇 건까지 처리할지 — 큰 지역은 이걸로 쪼개서 여러 번 호출"
    ),
    x_admin_key: str | None = Header(default=None),
    session: AsyncSession = SessionDep,
) -> dict:
    """행정안전부 착한가격업소(정부 지정 저렴 업소 + 실제 대표메뉴 가격)를 가져와
    Place/MenuItem으로 저장한다 — 초기 사용자에게 보여줄 실제 절약 정보의 콜드스타트 시드.
    전국 한 번에 넣으면 Render 무료 플랜 요청 제한에 걸릴 수 있으니 region으로 나눠 실행하고,
    서울처럼 지역 하나가 커도(수천 건) offset/limit으로 더 쪼개서 여러 번 호출한다 — 응답의
    next_offset/done을 보고 done이 false면 같은 region으로 offset=next_offset을 넣어 이어서 호출."""
    if not settings.admin_sync_key or x_admin_key != settings.admin_sync_key:
        raise AuthenticationRequiredError("관리자 키가 필요합니다 (X-Admin-Key 헤더)")
    return await sync_good_price_stores(session, region=region, offset=offset, limit=limit)


@router.post("/import/good-price-csv")
async def import_good_price_csv(
    file: UploadFile = File(...),
    region: str | None = Query(default=None, description="주소에 포함될 지역명 (예: 평택). 비우면 전체"),
    offset: int = Query(default=0, ge=0, description="이 지역 매칭 결과 중 몇 번째부터 처리할지"),
    limit: int | None = Query(
        default=None, ge=1, description="한 번에 몇 건까지 처리할지 — 큰 지역은 이걸로 쪼개서 여러 번 호출"
    ),
    dry_run: bool = Query(default=False, description="true면 DB에 저장하지 않고 파싱 결과만 미리보기"),
    x_admin_key: str | None = Header(default=None),
    session: AsyncSession = SessionDep,
) -> dict:
    """착한가격업소 파일(CSV 또는 goodprice.go.kr에서 받은 xls)을 직접 업로드해서
    저장한다 — data.go.kr이 점검 중이거나 활용신청이 안 될 때, 지자체 홈페이지·
    경기데이터드림·goodprice.go.kr 등에서 받은 파일로 같은 파이프라인(Place + 실제
    메뉴 가격 → 절약 엔진)을 태우는 우회 경로. 확장자로 형식을 판단한다.
    offset/limit: 서울처럼 한 지역이 커도(1,989건) 지오코딩+저장을 한 요청 안에서
    다 처리하면 배포 환경 타임아웃(502)에 걸린다 — 응답의 next_offset/done을 보고
    done이 false면 같은 region으로 offset=next_offset을 넣어 이어서 호출한다."""
    if not settings.admin_sync_key or x_admin_key != settings.admin_sync_key:
        raise AuthenticationRequiredError("관리자 키가 필요합니다 (X-Admin-Key 헤더)")

    content = await file.read()
    filename = (file.filename or "").lower()
    try:
        if filename.endswith(".xls") or filename.endswith(".xlsx"):
            raw_rows = parse_xls_bytes(content)
        else:
            raw_rows = parse_csv_bytes(content)
    except ValueError as exc:
        raise InvalidCsvError(str(exc)) from exc
    if not raw_rows:
        raise InvalidCsvError("파일에서 데이터 행을 찾지 못했습니다")

    if dry_run:
        from app.sources.public_api.good_price import parse_row

        parsed = [p for p in (parse_row(r) for r in raw_rows) if p is not None]
        if region:
            parsed = [p for p in parsed if p["address"] and region in p["address"]]
        return {
            "dry_run": True,
            "raw_rows": len(raw_rows),
            "usable_rows": len(parsed),
            "needs_geocoding": sum(1 for p in parsed if p["lat"] is None),
            "preview": parsed[:10],
        }

    return await store_rows(session, raw_rows, region=region, offset=offset, limit=limit)
