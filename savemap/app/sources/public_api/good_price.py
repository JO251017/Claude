import asyncio
import logging
import time
import uuid

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.spatial import ewkt_point, to_h3
from app.domain.enums import SourceType
from app.domain.menu_item import MenuItem
from app.engine.menu_name import normalize_menu_name
from app.domain.place import Place
from app.engine.offer_sync import sync_menu_offer
from app.engine.spatial_query import EXCLUDED_CATEGORY_KEYWORDS
from app.integrations.gemini import GeminiVisionClient
from app.integrations.kakao import KakaoClient

logger = logging.getLogger(__name__)

# 행정안전부 "착한가격업소 현황" (data.go.kr 파일데이터 → odcloud 표준 오픈API, 또는
# goodprice.go.kr에서 직접 받은 xls/csv). 정부·지자체가 "가격이 저렴한 업소"로 직접
# 지정·공표한 실제 데이터로, 업소명·주소·전화번호·대표 품목/가격을 제공한다 —
# 카카오/네이버가 메뉴를 API로 주지 않는 상황에서, 지어내지 않고 초기(콜드스타트)
# 절약 정보를 채울 수 있는 유일하게 확인된 합법적 원천이다.
#
# 실제 다운로드 파일(goodprice.go.kr, 2026-07-31 확인)에는 좌표(위도/경도)가 아예
# 없다 — 업소명/주소만 있고, 품목/가격도 "주요품목"/"가격" 단일 쌍 하나뿐이다(품목1,
# 품목2 형태 아님). odcloud API도 같은 원본 파일을 변환한 것이라 컬럼이 비슷할
# 가능성이 높아, 두 패턴(단일 쌍 + 번호 붙은 패턴) 둘 다 인식하게 하고, 좌표가 없으면
# 카카오 주소 검색으로 지오코딩한다(좌표를 지어내지 않고, 실제 주소 매칭 결과만 사용).
#
# 엔드포인트 UDDI는 포털 업로드 회차마다 바뀌므로 코드에 하드코딩하지 않고
# GOOD_PRICE_API_URL 환경변수로 받는다. 미설정이면 아무것도 지어내지 않고 건너뛴다.

_PER_PAGE = 300
_MAX_PAGES = 40  # 전국 약 6~7천 건 안전 상한


def _row_value(row: dict, *candidates: str):
    """공공 파일데이터의 한글 컬럼명이 회차/출처별로 조금씩 달라서(띄어쓰기 등) 후보를 순서대로 본다."""
    for key in candidates:
        value = row.get(key)
        if value not in (None, ""):
            return value
    stripped = {k.replace(" ", ""): v for k, v in row.items()}
    for key in candidates:
        value = stripped.get(key.replace(" ", ""))
        if value not in (None, ""):
            return value
    return None


def parse_price(value) -> float | None:
    """엑셀에서 온 순수 숫자(8800.0)와, '9,000원' 같은 문자열 표기를 둘 다 다룬다.
    문자열의 소수점을 숫자로 오인해 자릿수가 밀리지 않도록 숫자 타입은 바로 float
    변환한다. 해석 불가면 None (버림)."""
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        price = float(value)
    else:
        digits = "".join(ch for ch in str(value) if ch.isdigit())
        if not digits:
            return None
        price = float(digits)
    return price if 100 <= price <= 10_000_000 else None


def parse_row(row: dict) -> dict | None:
    """odcloud/xls/csv 행 → 저장에 필요한 필드. 이름/메뉴가격 중 하나라도 없으면
    None (불완전한 데이터를 지어내서 채우지 않는다). 좌표는 없어도 되고(지오코딩으로
    나중에 채움), 있으면 그대로 신뢰한다."""
    name = _row_value(row, "업소명")
    if not name:
        return None

    category = _row_value(row, "업종명", "업종", "구분", "업소구분")
    if category and any(kw in str(category) for kw in EXCLUDED_CATEGORY_KEYWORDS):
        # 미용실/이발소 등은 SaveMap이 지금 다루는 음식점·카페 범위 밖이라 비활성화
        # 상태다(사용자 지시, 2026-08-12) — 지오코딩·AI 통상가 추정 비용을 아예 안
        # 들이도록 저장 전(파싱 단계)에서부터 걸러낸다. spatial_query의 검색 필터와
        # 같은 키워드를 공유해 기준이 어긋나지 않게 한다.
        return None

    lat = lng = None
    raw_lat, raw_lng = _row_value(row, "위도"), _row_value(row, "경도")
    if raw_lat not in (None, "") and raw_lng not in (None, ""):
        try:
            lat, lng = float(raw_lat), float(raw_lng)
            if not (33.0 < lat < 39.5 and 124.0 < lng < 132.0):
                lat = lng = None
        except (TypeError, ValueError):
            lat = lng = None

    menu_items: list[tuple[str, float]] = []
    # 실제 goodprice.go.kr 다운로드 형식: 품목/가격이 한 쌍뿐이다.
    single_name = _row_value(row, "주요품목", "착한가격품목", "품목", "메뉴")
    single_price = parse_price(_row_value(row, "가격", "착한가격"))
    if single_name and single_price:
        menu_items.append((str(single_name).strip(), single_price))
    # 다른 배포본(odcloud 등)이 번호 붙은 여러 품목을 줄 수도 있으니 함께 지원.
    for i in ("1", "2", "3"):
        item_name = _row_value(row, f"품목{i}", f"착한가격품목{i}", f"메뉴{i}")
        price = parse_price(_row_value(row, f"가격{i}", f"품목{i}가격"))
        if item_name and price and str(item_name).strip() != (single_name or "").strip():
            menu_items.append((str(item_name).strip(), price))
    if not menu_items:
        return None

    return {
        "name": str(name).strip(),
        "address": _row_value(row, "주소", "소재지도로명주소", "소재지 도로명 주소", "소재지"),
        "phone": _row_value(row, "업소 전화번호", "전화번호", "연락처"),
        "category": category,
        "lat": lat,
        "lng": lng,
        "menu_items": menu_items,
    }


async def _fetch_rows() -> list[dict]:
    rows: list[dict] = []
    async with httpx.AsyncClient(timeout=30) as client:
        for page in range(1, _MAX_PAGES + 1):
            resp = await client.get(
                settings.good_price_api_url,
                params={
                    "page": page,
                    "perPage": _PER_PAGE,
                    "returnType": "JSON",
                    "serviceKey": settings.data_go_kr_key,
                },
            )
            resp.raise_for_status()
            body = resp.json()
            batch = body.get("data", [])
            rows.extend(batch)
            if len(batch) < _PER_PAGE:
                break
    return rows


async def sync_good_price_stores(
    session: AsyncSession, region: str | None = None, offset: int = 0, limit: int | None = None
) -> dict:
    """착한가격업소를 Place + MenuItem(실제 대표메뉴 가격)으로 저장한다. 메뉴가 들어가면
    기존 절약 엔진(지역 비교 → 오퍼 자동 생성 → AI 절약 리포트)이 그대로 동작한다.
    region이 주어지면 주소에 그 문자열이 포함된 행만 (예: '평택') — Render 무료 플랜의
    요청 시간 제한 안에서 지역 단위로 나눠 실행하기 위함.
    offset/limit: CSV 업로드 경로(store_rows)와 동일하게, 지역 하나가 커도(서울 등)
    지오코딩+저장을 여러 번의 작은 호출로 쪼갤 수 있게 그대로 전달한다 — 안 넘기면
    이전에 CSV 대량 임포트에서 겪은 것과 같은 502 타임아웃을 그대로 다시 겪는다."""
    if not settings.good_price_api_url:
        return {"skipped": "GOOD_PRICE_API_URL 미설정 — data.go.kr 활용신청 승인 후 요청 URL을 환경변수로 넣어주세요"}
    if not settings.data_go_kr_key:
        return {"skipped": "DATA_GO_KR_KEY 미설정"}

    raw_rows = await _fetch_rows()
    result = await store_rows(session, raw_rows, region=region, offset=offset, limit=limit)
    return {"fetched_rows": len(raw_rows), **result}


def parse_csv_bytes(content: bytes) -> list[dict]:
    """지자체/포털에서 받은 착한가격업소 CSV(공공기관 파일은 cp949인 경우가 많다)를
    odcloud 응답과 같은 dict 행 목록으로 변환한다 — data.go.kr이 점검 중이어도
    파일만 구하면 같은 파이프라인으로 넣을 수 있게 하는 우회로."""
    text = None
    for encoding in ("utf-8-sig", "cp949", "utf-8"):
        try:
            text = content.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        raise ValueError("CSV 인코딩을 해석할 수 없습니다 (utf-8/cp949 지원)")
    import csv
    import io

    reader = csv.DictReader(io.StringIO(text))
    return [dict(row) for row in reader]


def parse_xls_bytes(content: bytes) -> list[dict]:
    """goodprice.go.kr에서 직접 받은 .xls 다운로드 파일을 dict 행 목록으로 변환한다.
    실제 파일은 1행 제목 + 1빈행 + 3행 헤더로 시작한다 — 헤더 행을 "번호" 컬럼이
    있는 줄로 자동 탐지해서, 포맷이 살짝 바뀌어도(제목 줄 유무 등) 안전하게 찾는다."""
    import xlrd

    book = xlrd.open_workbook(file_contents=content)
    sheet = book.sheet_by_index(0)

    header_row_idx = None
    for r in range(min(10, sheet.nrows)):
        values = [str(sheet.cell_value(r, c)).strip() for c in range(sheet.ncols)]
        if "업소명" in values:
            header_row_idx = r
            break
    if header_row_idx is None:
        raise ValueError("엑셀에서 헤더 행(업소명 컬럼)을 찾지 못했습니다")

    headers = [str(sheet.cell_value(header_row_idx, c)).strip() for c in range(sheet.ncols)]
    rows = []
    for r in range(header_row_idx + 1, sheet.nrows):
        values = [sheet.cell_value(r, c) for c in range(sheet.ncols)]
        rows.append(dict(zip(headers, values)))
    return rows


_GEOCODE_CONCURRENCY = 10


async def _geocode_missing_coords(rows: list[dict]) -> None:
    """좌표 없는 행을 주소 기준으로 지오코딩한다 — 좌표를 지어내지 않고, 카카오
    주소 검색이 실제로 찾아준 좌표만 채운다. 실패하면 그 행은 좌표 없이 남고
    store_rows에서 걸러진다. 전국 규모(1만 건 이상)에서 한 건씩 순차 호출하면
    배포 환경(Render)의 요청 타임아웃을 넘기므로, 제한된 동시성으로 병렬 처리한다."""
    if not settings.kakao_rest_api_key:
        return
    kakao = KakaoClient()
    semaphore = asyncio.Semaphore(_GEOCODE_CONCURRENCY)

    async def _geocode_one(row: dict) -> None:
        async with semaphore:
            try:
                geocoded = await kakao.geocode(row["address"])
            except Exception as exc:  # noqa: BLE001 - 한 건 실패가 전체를 막으면 안 됨
                logger.warning("착한가격업소 지오코딩 실패: %s: %s", row["address"], exc)
                return
            if geocoded is not None:
                row["lat"], row["lng"] = geocoded.lat, geocoded.lng

    targets = [row for row in rows if row["lat"] is None and row.get("address")]
    await asyncio.gather(*(_geocode_one(row) for row in targets))


# 착한가격업소 데이터는 품목명이 크게 겹친다("이용료", "커트", "짜장면" 등이 전국에서
# 수백~수천 번 반복). 행 하나마다 Gemini를 부르면 13,000행 기준 13,000번 호출이 되어
# 시간·비용이 그대로 폭발한다 — 청크 안의 "고유 품목명" 단위로만 한 번씩 물어보고,
# 그 결과를 프로세스가 살아있는 동안(TTL) 재사용해 다음 청크·다음 지역이 같은
# 품목명을 다시 물어보지 않게 한다.
_TYPICAL_PRICE_CACHE: dict[str, tuple[float | None, float]] = {}
_TYPICAL_PRICE_CACHE_TTL_SEC = 24 * 3600
_TYPICAL_PRICE_CACHE_MAX = 2000
_TYPICAL_PRICE_CONCURRENCY = 5


def _prune_typical_price_cache() -> None:
    now = time.time()
    for key in [
        k for k, (_, ts) in _TYPICAL_PRICE_CACHE.items() if now - ts > _TYPICAL_PRICE_CACHE_TTL_SEC
    ]:
        del _TYPICAL_PRICE_CACHE[key]
    while len(_TYPICAL_PRICE_CACHE) > _TYPICAL_PRICE_CACHE_MAX:
        oldest_key = min(_TYPICAL_PRICE_CACHE, key=lambda k: _TYPICAL_PRICE_CACHE[k][1])
        del _TYPICAL_PRICE_CACHE[oldest_key]


async def _estimate_typical_prices(item_names: set[str]) -> dict[str, float | None]:
    """청크 안 고유 품목명별로 Gemini에게 통상 시세를 한 번씩만 물어보고 캐시한다.
    GEMINI_API_KEY가 없으면(미설정) 아무것도 지어내지 않고 빈 dict를 돌려준다 —
    이 경우 기존과 동일하게 ai_typical_price는 None으로 남고, 실측 비교만 쓰인다."""
    if not settings.gemini_api_key or not item_names:
        return {}

    now = time.time()
    results: dict[str, float | None] = {}
    to_fetch: list[str] = []
    for name in item_names:
        cached = _TYPICAL_PRICE_CACHE.get(name)
        if cached is not None and now - cached[1] <= _TYPICAL_PRICE_CACHE_TTL_SEC:
            results[name] = cached[0]
        else:
            to_fetch.append(name)

    if to_fetch:
        client = GeminiVisionClient()
        semaphore = asyncio.Semaphore(_TYPICAL_PRICE_CONCURRENCY)

        async def _fetch_one(name: str) -> None:
            async with semaphore:
                try:
                    price = await client.estimate_typical_price(name)
                except Exception as exc:  # noqa: BLE001 - 한 품목 실패가 나머지를 막으면 안 됨
                    logger.warning("착한가격업소 AI 통상가 추정 실패: %s: %s", name, exc)
                    price = None
                results[name] = price
                _TYPICAL_PRICE_CACHE[name] = (price, time.time())

        await asyncio.gather(*(_fetch_one(name) for name in to_fetch))
        _prune_typical_price_cache()

    return results


def _truncate(value: str | None, max_len: int) -> str | None:
    """DB 컬럼 길이를 넘는 실데이터(전화번호 여러 개 붙여쓴 경우 등)가 와도 잘라서
    저장할 뿐, 행 전체를 실패시키지 않는다 — 잘못된 값을 지어내는 게 아니라 실제
    값의 일부를 그대로 쓰는 것이므로 원칙에 어긋나지 않는다."""
    if value is None:
        return None
    value = str(value).strip()
    return value[:max_len] if len(value) > max_len else value


# 전국 단위 파일(1만 건 이상, 수십 MB)을 region×offset 조합으로 쪼개 여러 번 호출하는
# 기존 방식(/import/good-price-csv)은 매 호출마다 파일 전체를 다시 업로드하고
# xlrd/csv로 다시 파싱한다 — 17MB 파일에 청크 60~70번이면 업로드만 1GB 넘게 반복되고
# 파싱 비용도 그만큼 누적돼 체감상 매우 느렸다(실제로 겪은 문제, 2026-08-11). 파일을
# 한 번만 업로드해 파싱 결과를 잠깐 메모리에 캐시해두고, 이어지는 청크 호출은 이
# import_id만 참조하게 해서 재업로드/재파싱을 없앤다. Render 무료 플랜은 재시작되면
# 메모리가 날아가므로 오래 들고 있지 않고 개수/시간으로 정리한다 — 오래 걸리는
# "정확성이 중요한 저장"은 여전히 DB(source of truth)에서 하고, 여긴 그 앞 단계
# (업로드·파싱)의 중복 비용만 없애는 캐시일 뿐이다.
_IMPORT_JOBS: dict[str, dict] = {}
_IMPORT_JOB_TTL_SEC = 3 * 3600
_IMPORT_JOB_MAX = 5


def _prune_import_jobs() -> None:
    now = time.time()
    for key in [k for k, v in _IMPORT_JOBS.items() if now - v["created_at"] > _IMPORT_JOB_TTL_SEC]:
        del _IMPORT_JOBS[key]
    while len(_IMPORT_JOBS) > _IMPORT_JOB_MAX:
        oldest_key = min(_IMPORT_JOBS, key=lambda k: _IMPORT_JOBS[k]["created_at"])
        del _IMPORT_JOBS[oldest_key]


def register_import_job(parsed_rows: list[dict]) -> str:
    """이미 parse_row를 거친 행 목록을 캐시에 등록하고 import_id를 돌려준다.
    정리(prune)는 등록 "후"에 해야 한다 — 등록 전에 하면 개수 상한 검사가 이번에
    새로 넣을 항목을 반영 못 해서, 매번 한 개씩 상한을 넘긴 채로 남는다."""
    job_id = uuid.uuid4().hex
    _IMPORT_JOBS[job_id] = {"parsed_rows": parsed_rows, "created_at": time.time()}
    _prune_import_jobs()
    return job_id


def get_import_job(job_id: str) -> list[dict] | None:
    job = _IMPORT_JOBS.get(job_id)
    return job["parsed_rows"] if job else None


async def store_parsed_rows(
    session: AsyncSession,
    parsed: list[dict],
    region: str | None = None,
    offset: int = 0,
    limit: int | None = None,
) -> dict:
    """이미 parse_row를 거친 행 목록을 받아 region 필터링 + offset/limit 슬라이스 +
    지오코딩 + DB 저장을 수행한다 — store_rows의 파일 파싱 이후 로직과 동일하다.
    import_id 캐시 경로(청크마다 파일을 다시 안 보내는 경로)와 기존 store_rows가
    이 함수를 공유한다.
    offset/limit: 지역 하나(예: 서울 1,989건)조차 지오코딩+저장을 한 요청 안에서 다
    처리하면 배포 환경 타임아웃(502)에 걸린다 — 지역별 매칭 결과를 이 범위로 한 번 더
    잘라서, 호출하는 쪽(관리자 페이지)이 작은 묶음으로 여러 번 나눠 부를 수 있게 한다."""
    if region:
        parsed = [p for p in parsed if p["address"] and region in p["address"]]
    total_matching = len(parsed)
    if limit is not None:
        parsed = parsed[offset : offset + limit]
    elif offset:
        parsed = parsed[offset:]
    slice_size = len(parsed)  # 지오코딩 실패로 나중에 줄어들어도 offset 전진 폭은 이 값 기준

    geocoded_count = sum(1 for p in parsed if p["lat"] is None and p.get("address"))
    await _geocode_missing_coords(parsed)
    parsed = [p for p in parsed if p["lat"] is not None]  # 좌표 못 찾은 행은 지어내지 않고 버림

    # 이 청크에 실제로 필요한 고유 품목명만 골라 한 번씩 AI 통상가를 물어본다 —
    # 청크 크기(관리자 페이지가 보통 300~500행씩 보냄)를 넘는 비용은 안 든다.
    unique_item_names = {
        _truncate(name, 255) for row in parsed for name, _ in row["menu_items"]
    }
    typical_prices = await _estimate_typical_prices(unique_item_names)

    places_created = 0
    items_created = 0
    items_updated = 0
    failed_rows: list[dict] = []
    for row in parsed:
        try:
            place = (
                await session.execute(
                    select(Place).where(Place.name == row["name"], Place.address == row["address"])
                )
            ).scalars().first()
            if place is None:
                category = row["category"]
                category_name = _truncate(
                    f"착한가격업소 > {category}" if category else "착한가격업소", 255
                )
                place = Place(
                    name=_truncate(row["name"], 255),
                    address=_truncate(row["address"], 500),
                    phone=_truncate(row["phone"], 32),
                    category_name=category_name,
                    owner_user_id=None,
                    geom=ewkt_point(row["lat"], row["lng"]),
                    h3_r9=to_h3(row["lat"], row["lng"]),
                )
                session.add(place)
                await session.flush()
                # flush 직후의 place.geom은 우리가 넣은 EWKT 문자열 그대로다 — DB에서
                # 다시 읽어오기 전까진 geoalchemy2가 WKBElement로 바꿔주지 않는다.
                # 바로 아래 sync_menu_offer가 to_shape(place.geom)을 호출하는데,
                # 문자열을 넘기면 "Only WKBElement and WKTElement objects are
                # supported"로 매 건 실패하고 rollback되어 아무것도 저장되지 않는
                # 실제 장애가 있었다(2026-08-11, 전국 착한가격업소 임포트에서 13,103건
                # 전부 "성공"으로 집계됐지만 실제로는 0건 저장). refresh로 DB가 반환한
                # WKBElement로 다시 채워야 한다.
                await session.refresh(place)
                places_created += 1

            for item_name, price in row["menu_items"]:
                item_name = _truncate(item_name, 255)
                existing = (
                    await session.execute(
                        select(MenuItem).where(
                            MenuItem.place_id == place.id,
                            MenuItem.normalized_name == normalize_menu_name(item_name),
                        )
                    )
                ).scalars().first()
                if existing is not None:
                    if float(existing.price) != price:
                        existing.price = price
                        items_updated += 1
                    item = existing
                else:
                    item = MenuItem(
                        place_id=place.id,
                        name=item_name,
                        price=price,
                        source=SourceType.S1_PUBLIC,
                        # 실측(지역 실제 등록가) 비교가 항상 우선이라 표본이 쌓이면
                        # 이 값은 자동으로 밀려난다 — 그전까지 콜드스타트 기준으로만 쓴다.
                        ai_typical_price=typical_prices.get(item_name),
                    )
                    session.add(item)
                    await session.flush()
                    items_created += 1
                await sync_menu_offer(session, place, item)
        except Exception as exc:  # noqa: BLE001 - 행 하나 실패가 나머지 수천 건을 막으면 안 됨
            logger.warning("착한가격업소 저장 실패 (%s): %s", row.get("name"), exc)
            await session.rollback()
            failed_rows.append({"name": row.get("name"), "reason": str(exc)[:200]})
            continue

    await session.commit()
    next_offset = offset + slice_size
    return {
        "usable_rows": len(parsed),
        "geocoded": geocoded_count,
        "region": region,
        "places_created": places_created,
        "menu_items_created": items_created,
        "menu_items_updated": items_updated,
        "failed_rows": len(failed_rows),
        "failed_samples": failed_rows[:5],
        "offset": offset,
        "total_matching_rows": total_matching,
        "next_offset": next_offset,
        "done": next_offset >= total_matching,
    }


async def store_rows(
    session: AsyncSession,
    raw_rows: list[dict],
    region: str | None = None,
    offset: int = 0,
    limit: int | None = None,
) -> dict:
    """파싱→저장 공통 경로 (odcloud API 동기화, 소용량 CSV/XLS 업로드가 함께 쓴다).
    실제 정부 데이터는 컬럼 길이 초과 등 예상 못 한 행이 섞여 있을 수 있어(예: 전화번호
    여러 개를 한 칸에 붙여쓴 경우), 행 하나가 실패해도 나머지 수천 건이 통째로 날아가지
    않도록 store_parsed_rows가 행 단위로 격리해서 처리한다.
    전국 단위 대용량 파일은 이 함수 대신 register_import_job + store_parsed_rows를
    직접 써서(admin.py의 /import/good-price-file, -run) 매 청크마다 파일을 다시
    파싱하는 비용을 피하는 게 훨씬 빠르다."""
    parsed = [p for p in (parse_row(r) for r in raw_rows) if p is not None]
    return await store_parsed_rows(session, parsed, region=region, offset=offset, limit=limit)
