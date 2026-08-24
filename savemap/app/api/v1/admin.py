from fastapi import APIRouter, File, Query, UploadFile
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import RequireAdminDep, SessionDep
from app.api.schemas.merchant import MerchantVerificationGrant, MerchantVerificationResponse
from app.core.errors import InvalidCsvError
from app.domain.menu_item import MenuItem
from app.domain.place import Place
from app.sources.merchant_console.service import (
    grant_merchant_verification,
    revoke_merchant_verification,
)
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
from app.sources.public_api.dine_out_price import (
    parse_csv_bytes as parse_dine_out_csv_bytes,
)
from app.sources.public_api.dine_out_price import (
    store_rows as store_dine_out_rows,
)
from app.sources.public_api.dine_out_price import (
    sync_dine_out_prices,
)
from app.sources.public_api.franchise_price import (
    apply_to_places as apply_franchise_prices,
)
from app.sources.public_api.franchise_price import (
    import_price_rows as import_franchise_price_rows,
)
from app.sources.public_api.franchise_price import (
    parse_csv_bytes as parse_franchise_csv_bytes,
)
from app.domain.enums import SourceType
from app.engine.menu_name import normalize_menu_name
from app.engine.offer_resync import resync_offers
from app.sources.public_api.restaurant_registry import sync_restaurant_registry
from app.sources.public_api.service import sync_all_public_sources

router = APIRouter(tags=["admin"], prefix="/admin")


@router.post("/merchant-verifications", response_model=MerchantVerificationResponse, status_code=201)
async def grant_merchant_verification_endpoint(
    payload: MerchantVerificationGrant,
    _admin: None = RequireAdminDep,
    session: AsyncSession = SessionDep,
) -> MerchantVerificationResponse:
    """특정 사용자에게 사업자 콘솔 접근 권한을 부여한다(2-3, 2026-08-13). 자동 심사는
    이번 최소 기능 범위에 없다 — 관리자가 사업자등록증 등을 오프라인으로 확인한 뒤
    이 엔드포인트로 수동 부여한다. 이미 인증돼 있으면 note만 갱신(upsert)한다."""
    row = await grant_merchant_verification(session, payload.user_id, note=payload.note)
    return MerchantVerificationResponse(user_id=row.user_id, note=row.note, verified_at=row.created_at)


@router.delete("/merchant-verifications/{user_id}", status_code=204)
async def revoke_merchant_verification_endpoint(
    user_id: str,
    _admin: None = RequireAdminDep,
    session: AsyncSession = SessionDep,
) -> None:
    await revoke_merchant_verification(session, user_id)


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


@router.post("/sync/dine-out-prices")
async def trigger_dine_out_price_sync(
    _admin: None = RequireAdminDep,
    session: AsyncSession = SessionDep,
) -> dict:
    """한국소비자원 참가격 외식비(시도별 평균가)를 가져와 저장한다.

    이 통계는 개별 매장 가격이 아니라 시도 평균이라, 주변에 비교할 매장이 없을 때만
    쓰는 예비 기준이다 — 그동안 그 자리를 AI 추정 통상가가 차지하고 있었는데, 정부가
    실제로 조사한 값으로 바꾸는 게 목적이다. 우선순위는 항상 실측 > 정부 통계 > AI 추정.

    DINE_OUT_PRICE_API_URL이 설정돼 있어야 동작하고, 미설정이면 아무것도 지어내지 않고
    skipped로 응답한다. 한 건도 못 읽으면 응답의 sample_raw_keys에 실제 컬럼명이 담겨
    나오므로 그걸 보고 파서를 맞추면 된다."""
    return await sync_dine_out_prices(session)


@router.post("/import/dine-out-price-csv")
async def import_dine_out_price_csv(
    file: UploadFile = File(...),
    dry_run: bool = Query(default=False, description="true면 저장하지 않고 파싱 결과만 미리보기"),
    _admin: None = RequireAdminDep,
    session: AsyncSession = SessionDep,
) -> dict:
    """참가격에서 내려받은 외식비 CSV를 직접 올려서 저장한다 — 오픈API 활용신청이
    안 됐거나 점검 중일 때 같은 파이프라인을 태우는 우회 경로(착한가격업소와 동일한 구조)."""
    content = await file.read()
    try:
        raw_rows = parse_dine_out_csv_bytes(content)
    except ValueError as exc:
        raise InvalidCsvError(str(exc)) from exc
    if not raw_rows:
        raise InvalidCsvError("파일에서 데이터 행을 찾지 못했습니다")

    if dry_run:
        from app.sources.public_api.dine_out_price import parse_row as parse_dine_out_row

        parsed = [p for p in (parse_dine_out_row(r) for r in raw_rows) if p is not None]
        return {
            "dry_run": True,
            "raw_rows": len(raw_rows),
            "usable_rows": len(parsed),
            "sample_raw_keys": sorted(raw_rows[0].keys())[:40],
            "preview": parsed[:10],
        }

    return await store_dine_out_rows(session, raw_rows)


@router.post("/import/franchise-prices-csv")
async def import_franchise_prices_csv(
    file: UploadFile = File(...),
    _admin: None = RequireAdminDep,
    session: AsyncSession = SessionDep,
) -> dict:
    """프랜차이즈 본사 공식 가격표 CSV를 올린다.

    컬럼: 브랜드, 매칭키워드(선택, 파이프 구분), 메뉴명, 가격, 출처URL(선택), 기준년월(선택)
    예) 스타벅스,스타벅스|starbucks,아메리카노,4500,https://...,2026-08

    가격은 여기 올린 값만 쓴다 — 이 서버가 가격을 만들어내는 일은 없다. 올린 뒤
    /admin/apply/franchise-prices를 호출하면 상호명이 맞는 매장에 실제로 붙는다."""
    content = await file.read()
    try:
        raw_rows = parse_franchise_csv_bytes(content)
    except ValueError as exc:
        raise InvalidCsvError(str(exc)) from exc
    if not raw_rows:
        raise InvalidCsvError("파일에서 데이터 행을 찾지 못했습니다")
    return await import_franchise_price_rows(session, raw_rows)


@router.post("/apply/franchise-prices")
async def apply_franchise_prices_endpoint(
    region: str | None = Query(default=None, description="주소에 포함될 지역명 (예: 평택). 비우면 전체"),
    offset: int = Query(default=0, ge=0, description="매장 목록 중 몇 번째부터 처리할지"),
    limit: int = Query(default=500, ge=1, le=2000, description="한 번에 훑을 매장 수"),
    _admin: None = RequireAdminDep,
    session: AsyncSession = SessionDep,
) -> dict:
    """올려둔 브랜드 가격표를 상호명이 맞는 매장에 MenuItem으로 붙인다.

    매장이 수만 건이라 한 번에 다 돌리면 타임아웃에 걸린다 — 응답의 done이 false면
    offset=next_offset으로 이어서 호출한다. 사용자가 사진으로 제보한 가격은 덮어쓰지
    않고 그대로 둔다(menu_items_kept_user_reported로 몇 건인지 보고한다)."""
    return await apply_franchise_prices(session, region=region, offset=offset, limit=limit)


@router.post("/maintenance/backfill-menu-normalized-names")
async def backfill_menu_normalized_names(
    offset: int = Query(default=0, ge=0, description="menu_item.id 기준 몇 번째부터 처리할지"),
    limit: int = Query(default=2000, ge=1, le=5000, description="한 번에 처리할 건수"),
    _admin: None = RequireAdminDep,
    session: AsyncSession = SessionDep,
) -> dict:
    """menu_item.normalized_name이 비어 있는 기존 행을 채운다.

    Supabase SQL Editor에서 컬럼만 추가하면(ALTER TABLE ... ADD COLUMN) 기존 행은
    빈 값으로 남는다 — 정규화 규칙이 파이썬 쪽(app.engine.menu_name)에만 있어서 SQL로는
    못 채운다. 이후 새로 생기는 행은 모델이 저장 시점에 자동으로 채우므로(정규화 로직이
    바뀌지 않는 한) 이 호출은 한 번만 하면 된다 — 다시 돌려도 안전하다(멱등).
    매장이 많으면 한 요청에 다 못 하니 응답의 next_offset/done을 보고 이어서 호출한다."""
    rows = (
        await session.execute(
            select(MenuItem)
            .where(MenuItem.id >= offset)
            .order_by(MenuItem.id)
            .limit(limit)
        )
    ).scalars().all()

    updated = 0
    for item in rows:
        correct = normalize_menu_name(item.name)[:255]
        if item.normalized_name != correct:
            item.normalized_name = correct
            updated += 1
    await session.commit()

    next_offset = rows[-1].id + 1 if rows else offset
    return {
        "scanned": len(rows),
        "updated": updated,
        "next_offset": next_offset,
        "done": len(rows) < limit,
    }


@router.post("/maintenance/resync-offers")
async def resync_offers_endpoint(
    region: str | None = Query(default=None, description="주소에 포함될 지역명 (예: 평택). 비우면 전체"),
    offset: int = Query(default=0, ge=0, description="menu_item.id 기준 몇 번째부터 처리할지"),
    limit: int = Query(default=500, ge=1, le=2000, description="한 번에 처리할 건수"),
    source: SourceType | None = Query(default=None, description="이 소스로 등록된 메뉴만 (예: s1_public)"),
    dry_run: bool = Query(default=False, description="true면 계산만 하고 저장하지 않음 — 영향 범위 미리 확인용"),
    _admin: None = RequireAdminDep,
    session: AsyncSession = SessionDep,
) -> dict:
    """이미 만들어진 Offer를 다시 계산해서 최신 벤치마크(실측/참가격/AI추정)로 갱신한다.

    절약 계산은 메뉴가 적재/갱신될 때 딱 한 번만 돌고 결과가 Offer에 그대로 굳는다 —
    나중에 주변에 매장이 더 생기거나 새 벤치마크 소스(참가격 통계, 프랜차이즈 가격
    등)가 채워져도 이미 만들어진 오퍼는 이 엔드포인트를 돌리기 전까진 안 바뀐다.

    **반드시 실행해야 하는 시점** (옵션이 아니라 배포 절차의 일부):
    - 새 벤치마크 소스를 처음 채운 직후 — /admin/sync/dine-out-prices,
      /admin/apply/franchise-prices, /admin/maintenance/backfill-menu-normalized-names
      실행 뒤에는 전체(region 없이) 한 번 돌려야 실제 검색 결과에 반영된다.
    - price_comparison.py의 판정 로직/상수(반경, 표본 기준 등)를 바꾼 배포 직후.

    **부분 실행**: 착한가격업소/인허가 데이터를 특정 지역에 대량 적재한 뒤 — 새
    매장이 이웃 표본이 되어 주변 기존 오퍼가 ai/gov에서 region으로 승격될 수 있다.
    region으로 그 지역만 좁혀 돌리면 된다.

    **정기 실행**: 주 1회 전체. Render 무료 플랜엔 크론이 없으므로 응답의
    next_offset/done을 보고 외부에서 done:true까지 이어서 호출해야 한다.

    dry_run=true로 먼저 돌려서 benchmark_transitions(전이 행렬)를 보고 영향 범위를
    가늠한 뒤, 실제로(dry_run=false) 실행하는 걸 권장한다. 멱등이라 여러 번 돌려도
    안전하다."""
    return await resync_offers(
        session, region=region, offset=offset, limit=limit, source=source, dry_run=dry_run
    )


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

    # 이름·위치만 있고 "얼마인지"는 모르는 매장이 얼마나 되는지 — 오늘(2026-08-20)
    # 붙인 4가지 가격 채우기 작업(메뉴명 정규화/참가격 통계/프랜차이즈 매칭/영수증
    # 제보)이 실제로 커버리지를 얼마나 늘렸는지 이 숫자로만 확인할 수 있다. 소스별로
    # 나누면 어느 경로가 실제로 기여하고 있는지도 바로 보인다.
    with_price_stmt = (
        select(func.count(func.distinct(MenuItem.place_id)))
        .select_from(MenuItem)
        .join(Place, MenuItem.place_id == Place.id)
        .where(*filters)
    )
    places_with_price = (await session.execute(with_price_stmt)).scalar_one()

    by_source_stmt = (
        select(MenuItem.source, func.count(func.distinct(MenuItem.place_id)))
        .join(Place, MenuItem.place_id == Place.id)
        .where(*filters)
        .group_by(MenuItem.source)
    )
    by_source = {
        row[0].value: row[1] for row in (await session.execute(by_source_stmt)).all()
    }

    return {
        "region_filter": region,
        "total_places": total,
        "by_category": by_category,
        "price_coverage": {
            "places_with_price": places_with_price,
            "coverage_pct": round(places_with_price / total * 100, 1) if total else 0.0,
            "places_with_price_by_source": by_source,
        },
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
