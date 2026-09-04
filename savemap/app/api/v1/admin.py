from datetime import UTC, datetime

from fastapi import APIRouter, File, Query, UploadFile
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import RequireAdminDep, SessionDep
from app.api.schemas.merchant import MerchantVerificationGrant, MerchantVerificationResponse
from app.core.errors import (
    InvalidCsvError,
    PriceDiscoveryJobNotFoundError,
    PriceDiscoveryJobNotReviewableError,
)
from app.domain.menu_item import MenuItem
from app.domain.place import Place
from app.domain.price_discovery import DiscoveryJobStatus, PriceDiscoveryJob
from app.domain.price_history import PriceHistory
from app.engine.freshness import freshness_breakdown
from app.engine.price_discovery.metrics import get_discovery_metrics
from app.engine.price_discovery.orchestrator import (
    approve_job,
    enqueue_candidates,
    reject_job,
    run_discovery_batch,
)
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
from app.sources.public_api.local_currency import (
    apply_local_currency_rows,
    get_cached_raw_rows as get_cached_local_currency_rows,
    import_rows as import_local_currency_rows,
    parse_csv_bytes as parse_local_currency_csv_bytes,
    sync_local_currency_merchants,
)
from app.domain.enums import SourceType
from app.engine.menu_name import normalize_menu_name
from app.engine.franchise_keyword_discovery import discover_franchise_keywords
from app.engine.menu_synonym_discovery import discover_menu_synonym_candidates
from app.engine.offer_blurb_backfill import backfill_offer_blurbs
from app.engine.typical_price_backfill import backfill_typical_prices
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


@router.post("/sync/local-currency-merchants")
async def trigger_local_currency_sync(
    region: str | None = Query(default=None, description="주소에 포함될 지역명 (예: 평택). 비우면 전체"),
    offset: int = Query(default=0, ge=0, description="이 지역 매장 중 몇 번째부터 매칭을 시도할지"),
    limit: int = Query(default=500, ge=1, le=2000, description="한 번에 훑을 매장 수"),
    _admin: None = RequireAdminDep,
    session: AsyncSession = SessionDep,
) -> dict:
    """전국지역화폐가맹점표준데이터를 가져와 상호명이 일치하는 기존 매장에
    accepts_local_currency 배지를 붙인다. 가격 정보는 없어 MenuItem/Offer는
    건드리지 않는다 — 검색 결과에 정보성 배지로만 노출된다.

    LOCAL_CURRENCY_API_URL이 설정돼 있어야 동작하고, 미설정이면 아무것도 지어내지
    않고 skipped로 응답한다. 매장이 많으면 done이 false로 오니 offset=next_offset으로
    이어서 호출한다. 상호명은 같은데 주소가 다른 지점이면 unmatched로 집계되고
    배지는 안 붙는다(잘못된 매장에 붙이느니 안 붙이는 쪽을 택함)."""
    return await sync_local_currency_merchants(session, region=region, offset=offset, limit=limit)


@router.post("/import/local-currency-csv")
async def import_local_currency_csv(
    file: UploadFile = File(...),
    _admin: None = RequireAdminDep,
) -> dict:
    """data.go.kr이 점검 중이거나 활용신청 전이어도, 직접 받은 지역화폐 가맹점
    CSV를 올려서 같은 매칭 파이프라인을 태울 수 있다(착한가격업소·참가격과 동일한
    우회 경로). 올린 뒤 /admin/apply/local-currency-merchants를 호출해야 실제로
    매장에 배지가 붙는다 — 이 엔드포인트는 파싱 가능 여부만 확인하고 캐시해둔다."""
    content = await file.read()
    try:
        raw_rows = parse_local_currency_csv_bytes(content)
    except ValueError as exc:
        raise InvalidCsvError(str(exc)) from exc
    if not raw_rows:
        raise InvalidCsvError("파일에서 데이터 행을 찾지 못했습니다")
    return import_local_currency_rows(raw_rows)


@router.post("/apply/local-currency-merchants")
async def apply_local_currency_merchants_endpoint(
    region: str | None = Query(default=None, description="주소에 포함될 지역명 (예: 평택). 비우면 전체"),
    offset: int = Query(default=0, ge=0, description="매장 목록 중 몇 번째부터 처리할지"),
    limit: int = Query(default=500, ge=1, le=2000, description="한 번에 훑을 매장 수"),
    _admin: None = RequireAdminDep,
    session: AsyncSession = SessionDep,
) -> dict:
    """/sync/local-currency-merchants 또는 /import/local-currency-csv로 이미 가져와
    캐시해둔 가맹점 명단을 다시 매칭만 재실행한다 — 관리자가 매칭 로직 조정 후
    재적용하거나, 새 지역으로 다시 훑을 때 데이터를 다시 안 받아도 되게 한다."""
    raw_rows = get_cached_local_currency_rows()
    if not raw_rows:
        return {
            "skipped": True,
            "reason": "가져온 지역화폐 가맹점 데이터가 없습니다. 먼저 "
            "/admin/sync/local-currency-merchants 또는 /admin/import/local-currency-csv로 "
            "데이터를 가져와주세요.",
        }
    return await apply_local_currency_rows(session, raw_rows, region=region, offset=offset, limit=limit)


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


@router.post("/maintenance/backfill-offer-blurbs")
async def backfill_offer_blurbs_endpoint(
    offset: int = Query(default=0, ge=0, description="offer.id 기준 몇 번째부터 처리할지"),
    limit: int = Query(default=50, ge=1, le=500, description="한 번에 처리할 건수"),
    dry_run: bool = Query(default=False, description="true면 생성만 하고 저장하지 않음"),
    _admin: None = RequireAdminDep,
    session: AsyncSession = SessionDep,
) -> dict:
    """AI 활용 확대 안건 D(2026-08-31) — 절약을 주장하는(store_discount>0) 오퍼 중
    아직 ai_one_line이 없는 것에 대해 매장 카드 한 줄 소개를 AI로 생성해 캐시한다.
    resync-offers와 같은 관례: Render 무료 플랜엔 크론이 없으므로 응답의
    next_offset/done을 보고 외부에서 done:true까지 이어서 호출해야 한다. limit
    기본값을 resync-offers(500)보다 작게(50) 잡은 이유는 이 배치가 건당 실제
    Gemini API 호출(네트워크 왕복)을 하기 때문 — DB만 훑는 재동기화보다 한 건당
    훨씬 오래 걸려서, 너무 크게 잡으면 Render 요청 타임아웃(502)에 걸릴 수 있다
    (AI Price Discovery에서 이미 겪은 문제, price_discovery_max_jobs_per_run
    참고).

    생성된 문장에 사실 목록에 없는 숫자가 하나라도 있으면(app.engine.ai_text_guard)
    저장하지 않고 건너뛴다 — 다음 실행 때 다시 시도된다(ai_one_line이 여전히
    null이므로)."""
    return await backfill_offer_blurbs(session, offset=offset, limit=limit, dry_run=dry_run)


@router.post("/maintenance/backfill-typical-prices")
async def backfill_typical_prices_endpoint(
    offset: int = Query(default=0, ge=0, description="menu_item.id 기준 몇 번째부터 처리할지"),
    limit: int = Query(default=50, ge=1, le=500, description="한 번에 처리할 건수"),
    dry_run: bool = Query(default=False, description="true면 채우기만 하고 저장하지 않음"),
    _admin: None = RequireAdminDep,
    session: AsyncSession = SessionDep,
) -> dict:
    """절약 기회 점수 활성화(2026-09-01, §17~18)의 구제 경로 — ai_typical_price가
    아직 없는 메뉴에 AI 통상가를 채운다. backfill-offer-blurbs와 같은 관례로
    limit 기본값을 작게(50) 잡는다(행당 실제 Gemini 호출). 같은 (정규화된 메뉴명,
    지역) 조합은 API를 다시 부르지 않고 이미 채워진 값을 복사한다
    (reused_from_cache로 집계, §42 "동일 benchmark 반복 생성 금지"). 채운 뒤
    기존 "오퍼 일괄 재동기화"를 다시 돌리면 compare_menu_item이 재평가되어
    ai 벤치마크가 오퍼에 자동으로 붙는다(새 발행 경로 없음)."""
    return await backfill_typical_prices(session, offset=offset, limit=limit, dry_run=dry_run)


@router.post("/maintenance/discover-menu-synonyms")
async def discover_menu_synonyms_endpoint(
    offset: int = Query(default=0, ge=0, description="탐색 대상 메뉴명 목록 기준 몇 번째부터"),
    limit: int = Query(default=300, ge=20, le=1000, description="한 번에 훑을 메뉴명 개수(내부에서 60개씩 묶어 호출)"),
    dry_run: bool = Query(default=False, description="true면 후보를 찾기만 하고 저장하지 않음"),
    _admin: None = RequireAdminDep,
    session: AsyncSession = SessionDep,
) -> dict:
    """AI 기능 확대(2026-09-04) — "표기만 다른 같은 메뉴" 후보를 AI로 넓게
    찾아 menu_synonym_candidate 테이블에 쌓는다. **여기서 실제 정규화 규칙
    (_SYNONYMS)에 자동 반영되는 건 하나도 없다** — 잘못 합치면 값이 다른
    메뉴끼리 비교해 없는 절약률을 만들어내므로, 후보는 사람이 검토한 뒤
    app/engine/menu_name.py를 직접 고쳐 커밋해야 실제로 적용된다. 이 배치는
    "검토할 후보를 모으는" 역할까지만 한다."""
    return await discover_menu_synonym_candidates(session, offset=offset, limit=limit, dry_run=dry_run)


@router.post("/maintenance/discover-franchise-keywords")
async def discover_franchise_keywords_endpoint(
    offset: int = Query(default=0, ge=0, description="탐색 대상 브랜드 목록 기준 몇 번째부터"),
    limit: int = Query(default=100, ge=1, le=500, description="한 번에 훑을 브랜드 개수"),
    dry_run: bool = Query(default=False, description="true면 제안을 찾기만 하고 저장하지 않음"),
    _admin: None = RequireAdminDep,
    session: AsyncSession = SessionDep,
) -> dict:
    """AI 기능 확대(2026-09-04) — 프랜차이즈 브랜드의 상호명 매칭 키워드
    변형(띄어쓰기/영문 표기/줄임말)을 AI로 찾아 franchise_brand.
    suggested_match_keywords 컬럼에 쌓는다. **여기서 실제 매칭 컬럼
    (match_keywords)에 자동 반영되는 건 하나도 없다** — 브랜드 매칭이
    잘못 넓혀지면 엉뚱한 매장에 그 브랜드의 공식 가격이 그대로 붙어버리므로,
    제안은 사람이 검토한 뒤 match_keywords에 직접 옮겨야 실제로 적용된다."""
    return await discover_franchise_keywords(session, offset=offset, limit=limit, dry_run=dry_run)


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

    # 가격 이력/신선도 검증(2026-08-31) — 오퍼 재동기화 배치(resync-offers)가 실제로
    # DB에 이력을 남겼는지, 그 결과 신선도가 "정보없음(unknown)"이 아니라 실제
    # 등급으로 잡히는지를 이 엔드포인트 하나로 확인할 수 있게 한다. 이 세션은 도구
    # 연결이 끊기면 DB를 직접 조회할 방법이 없어서, 이미 있는 조회 전용 엔드포인트에
    # 얹는 편이 새 엔드포인트를 만드는 것보다 낫다(이 함수 자체의 목적과도 정확히
    # 일치 — "방금 한 작업이 실제로 반영됐는지 확인").
    history_filters = [Place.address.ilike(f"%{region}%")] if region else []
    total_history_rows = (
        await session.execute(
            select(func.count())
            .select_from(PriceHistory)
            .join(Place, PriceHistory.place_id == Place.id)
            .where(*history_filters)
        )
    ).scalar_one()
    current_rows_stmt = (
        select(PriceHistory.observed_at)
        .join(Place, PriceHistory.place_id == Place.id)
        .where(PriceHistory.is_current.is_(True), *history_filters)
    )
    current_observed_ats = (await session.execute(current_rows_stmt)).scalars().all()

    breakdown = freshness_breakdown(current_observed_ats, now=datetime.now(UTC))

    return {
        "region_filter": region,
        "total_places": total,
        "by_category": by_category,
        "price_coverage": {
            "places_with_price": places_with_price,
            "coverage_pct": round(places_with_price / total * 100, 1) if total else 0.0,
            "places_with_price_by_source": by_source,
        },
        "price_history": {
            "total_rows": total_history_rows,
            "current_rows": len(current_observed_ats),
            "freshness_breakdown": breakdown,
        },
        "recent_samples": recent_samples,
    }


# --- AI Price Discovery Engine(2026-08-31) — 가격 없는 매장을 Gemini 검색
# 그라운딩으로 조사해 공개 자료에서 실제 가격을 찾는다. 실제 파이프라인은
# app/engine/price_discovery/*에 있고, 여기는 관리자 인증 + Render 무료
# 플랜(상시 worker 없음)을 고려한 배치 실행 엔드포인트만 둔다. 일반 사용자에게는
# 노출되지 않는다(28-21) — 다른 관리자 엔드포인트와 동일하게 RequireAdminDep. ---


@router.post("/price-discovery/run")
async def run_price_discovery_endpoint(
    region: str | None = Query(default=None, description="주소에 포함될 지역명 (예: 평택). 비우면 전체"),
    limit: int | None = Query(
        default=None,
        ge=1,
        le=100,
        description="이번 실행에서 새로 큐에 넣고 처리할 최대 매장 수 (비우면 설정값 사용)",
    ),
    _admin: None = RequireAdminDep,
    session: AsyncSession = SessionDep,
) -> dict:
    """가격 없는 매장을 candidate_selector로 큐에 채운 뒤(이미 큐에 있으면 건너뜀),
    PENDING 큐에서 우선순위 순으로 처리한다. 한 번 클릭에 무제한 실행되지 않도록
    limit(기본 PRICE_DISCOVERY_MAX_JOBS_PER_RUN, 기본 3 — 요청 하나가 HTTP
    타임아웃 안에 끝나도록 보수적으로 잡음, 2026-08-31 502 재현 후 20에서
    낮춤)까지만 처리한다(28-22) —
    Render 무료 플랜엔 크론이 없으므로 전체를 처리하려면 이 엔드포인트를 여러 번
    반복 호출해야 한다(admin-import.html의 자동 이어호출 루프 패턴과 동일)."""
    enqueued = await enqueue_candidates(session, region=region, limit=limit)
    result = await run_discovery_batch(session, limit=limit)
    result["enqueued_this_run"] = enqueued
    return result


@router.get("/price-discovery/status")
async def price_discovery_status_endpoint(
    _admin: None = RequireAdminDep,
    session: AsyncSession = SessionDep,
) -> dict:
    """큐 상태별 건수 — /run을 반복 호출해야 하는지(pending이 남아있는지) 바로
    확인할 수 있다."""
    rows = (
        await session.execute(
            select(PriceDiscoveryJob.status, func.count()).group_by(PriceDiscoveryJob.status)
        )
    ).all()
    counts = {status_.value: 0 for status_ in DiscoveryJobStatus}
    for status_, count in rows:
        counts[status_.value] = count
    return counts


@router.get("/price-discovery/jobs")
async def list_price_discovery_jobs_endpoint(
    status: DiscoveryJobStatus = Query(
        default=DiscoveryJobStatus.MANUAL_REVIEW,
        description="이 상태의 작업만 (기본 manual_review — 승인/거절이 필요한 것부터).",
    ),
    limit: int = Query(default=50, ge=1, le=200),
    _admin: None = RequireAdminDep,
    session: AsyncSession = SessionDep,
) -> list[dict]:
    """개별 작업의 id/매장 정보/결과 요약을 실제로 확인할 수 있는 목록 —
    /status(건수만)와 /jobs/{id}/approve·reject(id를 미리 알아야 함) 사이의
    빠진 연결고리였다. approve/reject에 넣을 job_id를 여기서 확인한다."""
    stmt = (
        select(PriceDiscoveryJob, Place.name, Place.address)
        .join(Place, PriceDiscoveryJob.place_id == Place.id)
        .where(PriceDiscoveryJob.status == status)
        .order_by(PriceDiscoveryJob.completed_at.desc().nullslast(), PriceDiscoveryJob.id.desc())
        .limit(limit)
    )
    rows = (await session.execute(stmt)).all()
    return [
        {
            "job_id": job.id,
            "place_id": job.place_id,
            "place_name": place_name,
            "place_address": place_address,
            "status": job.status.value,
            "priority": job.priority,
            "attempt_count": job.attempt_count,
            "error_code": job.error_code,
            "result_summary": job.result_summary,
            "last_attempted_at": job.last_attempted_at.isoformat() if job.last_attempted_at else None,
            "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        }
        for job, place_name, place_address in rows
    ]


@router.get("/price-discovery/metrics")
async def price_discovery_metrics_endpoint(
    region: str | None = Query(default=None, description="주소에 포함될 지역명 (예: 평택). 비우면 전체"),
    _admin: None = RequireAdminDep,
    session: AsyncSession = SessionDep,
) -> dict:
    """가격 커버리지 + 발견 성공률(28-24/28-25) — 전부 실제 DB 집계, 하드코딩 없음.
    region을 바꿔가며 여러 번 호출하면 지역별 발견률을 비교할 수 있다(28-25 —
    이 저장소는 주소 문자열에서 시/군/구를 정규화해 자동 그룹핑하는 로직이
    없어서, 다른 admin 엔드포인트와 같은 방식으로 region 필터를 그대로 재사용
    했다)."""
    return await get_discovery_metrics(session, region=region)


async def _get_reviewable_job(session: AsyncSession, job_id: int) -> PriceDiscoveryJob:
    job = await session.get(PriceDiscoveryJob, job_id)
    if job is None:
        raise PriceDiscoveryJobNotFoundError()
    if job.status != DiscoveryJobStatus.MANUAL_REVIEW:
        raise PriceDiscoveryJobNotReviewableError()
    return job


@router.post("/price-discovery/jobs/{job_id}/approve")
async def approve_price_discovery_job_endpoint(
    job_id: int,
    _admin: None = RequireAdminDep,
    session: AsyncSession = SessionDep,
) -> dict:
    """manual_review 작업을 관리자가 승인 — 매장을 강제 모드로 재조사해서 이번엔
    검토 보류 없이 게시한다(28-30, 복잡한 검토 UI 없이 최소 기능만). 매장 매칭
    자체를 AI가 거절한 작업(FAILED)은 승인 대상이 아니다."""
    job = await _get_reviewable_job(session, job_id)
    published = await approve_job(session, job)
    return {"job_id": job.id, "status": job.status.value, "prices_published": published}


@router.post("/price-discovery/jobs/{job_id}/reject")
async def reject_price_discovery_job_endpoint(
    job_id: int,
    _admin: None = RequireAdminDep,
    session: AsyncSession = SessionDep,
) -> dict:
    job = await _get_reviewable_job(session, job_id)
    await reject_job(session, job)
    return {"job_id": job.id, "status": job.status.value}


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
