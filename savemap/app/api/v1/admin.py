from fastapi import APIRouter, File, Query, UploadFile
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import RequireAdminDep, SessionDep
from app.core.errors import InvalidCsvError
from app.domain.place import Place
from app.sources.public_api.good_price import (
    get_import_job,
    parse_csv_bytes,
    parse_row,
    parse_xls_bytes,
    register_import_job,
    store_parsed_rows,
    store_rows,
    sync_good_price_stores,
)
from app.sources.public_api.restaurant_registry import sync_restaurant_registry
from app.sources.public_api.service import sync_all_public_sources

router = APIRouter(tags=["admin"], prefix="/admin")


@router.post("/sync/public-data")
async def trigger_public_data_sync(
    _admin: None = RequireAdminDep,
    session: AsyncSession = SessionDep,
) -> dict:
    """공공데이터 수집을 즉시 실행한다. Celery worker가 없는 배포 환경(현재 Render 무료 플랜)에서
    수동/크론으로 동기화를 트리거하기 위한 엔드포인트. ADMIN_SYNC_KEY 미설정 시 항상 거부된다."""
    return await sync_all_public_sources(session)


@router.post("/sync/good-price-stores")
async def trigger_good_price_sync(
    region: str | None = Query(default=None, description="주소에 포함될 지역명 (예: 평택). 비우면 전국"),
    offset: int = Query(default=0, ge=0, description="이 지역 매칭 결과 중 몇 번째부터 처리할지"),
    limit: int | None = Query(
        default=None, ge=1, description="한 번에 몇 건까지 처리할지 — 큰 지역은 이걸로 쪼개서 여러 번 호출"
    ),
    _admin: None = RequireAdminDep,
    session: AsyncSession = SessionDep,
) -> dict:
    """행정안전부 착한가격업소(정부 지정 저렴 업소 + 실제 대표메뉴 가격)를 가져와
    Place/MenuItem으로 저장한다 — 초기 사용자에게 보여줄 실제 절약 정보의 콜드스타트 시드.
    전국 한 번에 넣으면 Render 무료 플랜 요청 제한에 걸릴 수 있으니 region으로 나눠 실행하고,
    서울처럼 지역 하나가 커도(수천 건) offset/limit으로 더 쪼개서 여러 번 호출한다 — 응답의
    next_offset/done을 보고 done이 false면 같은 region으로 offset=next_offset을 넣어 이어서 호출."""
    return await sync_good_price_stores(session, region=region, offset=offset, limit=limit)


@router.post("/sync/restaurant-registry")
async def trigger_restaurant_registry_sync(
    category: str = Query(..., description="일반음식점 | 휴게음식점 | 유흥주점"),
    region: str = Query(..., description="도로명주소에 포함될 지역명 (예: 평택시) — 전국 일괄은 지원하지 않음"),
    page: int = Query(default=1, ge=1, description="이 region/category 안에서 몇 번째 페이지인지"),
    per_page: int = Query(default=100, ge=1, le=100, description="페이지당 건수 (API 상한 100)"),
    _admin: None = RequireAdminDep,
    session: AsyncSession = SessionDep,
) -> dict:
    """행정안전부 일반음식점/휴게음식점(카페)/유흥주점 인허가 현황을 Place로 저장한다.
    착한가격업소와 달리 가격 정보는 없지만 전국 커버리지가 훨씬 커서, 지도의 기본
    베이스를 먼저 채우는 용도다 — 절약/가격비교는 이 위에 착한가격업소·사용자제보 등
    다른 소스가 나중에 얹힌다. 전국은 한 번에 못 돌리니 region으로 나누고, 한 지역도
    응답의 has_more가 true면 같은 region/category로 page+1을 넣어 이어서 호출한다."""
    return await sync_restaurant_registry(session, category=category, region=region, page=page, per_page=per_page)


@router.get("/places/stats")
async def get_places_stats(
    region: str | None = Query(default=None, description="주소에 포함될 문자열로 필터 (예: 평택시). 비우면 전체"),
    _admin: None = RequireAdminDep,
    session: AsyncSession = SessionDep,
) -> dict:
    """방금 실행한 임포트(인허가 데이터/착한가격업소 등)가 실제로 DB에 반영됐는지 확인하는
    조회 전용 엔드포인트. 관리자 페이지 브라우저 콘솔에 찍히는 places_created 합계는 API
    응답값일 뿐 실제로 커밋됐다는 증거는 아니라서, place 테이블을 직접 세어 보여준다
    (전체 건수 + 업종(카테고리)별 분포 + 가장 최근에 생성된 샘플)."""

    filters = [Place.address.ilike(f"%{region}%")] if region else []

    total = (await session.execute(select(func.count()).select_from(Place).where(*filters))).scalar_one()

    # category_name은 "일반음식점 > 한식"처럼 "소스 라벨 > 세부업종"으로 저장되므로,
    # 앞부분(소스 라벨)만 잘라서 묶어야 소스별 임포트 현황을 한눈에 볼 수 있다.
    category_label = func.split_part(func.coalesce(Place.category_name, ""), " > ", 1).label("category")
    by_category_stmt = (
        select(category_label, func.count()).where(*filters).group_by(category_label).order_by(func.count().desc())
    )
    by_category = {
        (row[0] or "(미분류)"): row[1] for row in (await session.execute(by_category_stmt)).all()
    }

    recent_stmt = (
        select(Place.name, Place.address, Place.category_name, Place.created_at)
        .where(*filters)
        .order_by(Place.created_at.desc())
        .limit(5)
    )
    recent_samples = [
        {"name": r[0], "address": r[1], "category": r[2], "created_at": r[3].isoformat() if r[3] else None}
        for r in (await session.execute(recent_stmt)).all()
    ]

    return {
        "region_filter": region,
        "total_places": total,
        "by_category": by_category,
        "recent_samples": recent_samples,
    }


@router.post("/import/good-price-csv")
async def import_good_price_csv(
    file: UploadFile = File(...),
    region: str | None = Query(default=None, description="주소에 포함될 지역명 (예: 평택). 비우면 전체"),
    offset: int = Query(default=0, ge=0, description="이 지역 매칭 결과 중 몇 번째부터 처리할지"),
    limit: int | None = Query(
        default=None, ge=1, description="한 번에 몇 건까지 처리할지 — 큰 지역은 이걸로 쪼개서 여러 번 호출"
    ),
    dry_run: bool = Query(default=False, description="true면 DB에 저장하지 않고 파싱 결과만 미리보기"),
    _admin: None = RequireAdminDep,
    session: AsyncSession = SessionDep,
) -> dict:
    """착한가격업소 파일(CSV 또는 goodprice.go.kr에서 받은 xls)을 직접 업로드해서
    저장한다 — data.go.kr이 점검 중이거나 활용신청이 안 될 때, 지자체 홈페이지·
    경기데이터드림·goodprice.go.kr 등에서 받은 파일로 같은 파이프라인(Place + 실제
    메뉴 가격 → 절약 엔진)을 태우는 우회 경로. 확장자로 형식을 판단한다.
    offset/limit: 서울처럼 한 지역이 커도(1,989건) 지오코딩+저장을 한 요청 안에서
    다 처리하면 배포 환경 타임아웃(502)에 걸린다 — 응답의 next_offset/done을 보고
    done이 false면 같은 region으로 offset=next_offset을 넣어 이어서 호출한다."""

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


@router.post("/import/good-price-file")
async def upload_good_price_file(
    file: UploadFile = File(...),
    _admin: None = RequireAdminDep,
) -> dict:
    """대용량 착한가격업소 파일(xls/csv, 전국 1만 건 이상)을 한 번만 업로드해서 파싱
    결과를 서버 메모리에 잠깐 캐시해두고 import_id를 돌려준다. 기존
    /import/good-price-csv는 region×offset 청크마다 파일 전체를 재업로드+재파싱해서,
    큰 파일(17MB, 1만2천 행) 기준 청크 수십~수백 번이면 업로드 트래픽만 1GB를 넘고
    파싱 시간도 그만큼 누적돼 체감상 매우 느렸다(실제로 겪은 문제, 2026-08-11).
    이 import_id를 /import/good-price-run에 이어서 넣으면 파일을 다시 안 보내도 된다.
    (Render 무료 플랜은 재시작되면 캐시가 날아간다 — 그때는 여기부터 다시 업로드)"""

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

    parsed = [p for p in (parse_row(r) for r in raw_rows) if p is not None]
    import_id = register_import_job(parsed)
    return {
        "import_id": import_id,
        "raw_rows": len(raw_rows),
        "usable_rows": len(parsed),
        "needs_geocoding": sum(1 for p in parsed if p["lat"] is None),
    }


@router.post("/import/good-price-run")
async def run_good_price_import(
    import_id: str = Query(..., description="/import/good-price-file 응답의 import_id"),
    region: str | None = Query(default=None, description="주소에 포함될 지역명 (예: 평택). 비우면 전체"),
    offset: int = Query(default=0, ge=0, description="이 지역 매칭 결과 중 몇 번째부터 처리할지"),
    limit: int | None = Query(
        default=None, ge=1, description="한 번에 몇 건까지 처리할지 — 큰 지역은 이걸로 쪼개서 여러 번 호출"
    ),
    dry_run: bool = Query(default=False, description="true면 DB에 저장하지 않고 파싱 결과만 미리보기"),
    _admin: None = RequireAdminDep,
    session: AsyncSession = SessionDep,
) -> dict:
    """/import/good-price-file로 업로드해둔 import_id를 이어서 실행한다 — 파일을
    다시 보내지도, 다시 파싱하지도 않는다(캐시된 파싱 결과를 그대로 재사용)."""

    parsed = get_import_job(import_id)
    if parsed is None:
        raise InvalidCsvError(
            "import_id를 찾을 수 없습니다 — 서버가 재시작됐거나 시간이 많이 지나 캐시가 "
            "만료됐을 수 있어요. /import/good-price-file로 파일을 다시 업로드해주세요."
        )

    if dry_run:
        filtered = [p for p in parsed if not region or (p["address"] and region in p["address"])]
        return {
            "dry_run": True,
            "import_id": import_id,
            "usable_rows": len(filtered),
            "needs_geocoding": sum(1 for p in filtered if p["lat"] is None),
            "preview": filtered[:10],
        }

    return await store_parsed_rows(session, parsed, region=region, offset=offset, limit=limit)
