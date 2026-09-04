"""전국지역화폐가맹점표준데이터(data.go.kr/data/15100062) — 지자체가 매달 등록하는
지역화폐/지역사랑상품권 가맹점 명단.

왜 넣는가: `PaymentMethodType.LOCAL_CURRENCY`(`app/domain/payment_method.py`)는
지금까지 100% 자기신고였다 — 사용자가 "이 매장 지역화폐 됨"이라고 스스로 체크하는
값일 뿐, 그 매장이 실제로 지역화폐 가맹점인지 검증할 데이터가 하나도 없었다. 이
데이터는 지자체가 공식으로 등록한 가맹점 명단이라 무료로 이 검증 공백을 메울 수
있는 유일하게 확인된 출처다(평택 모아페이·천안·아산 아산페이 등 포함).

지어내지 않기 원칙: 이 데이터셋에는 **가격·할인율이 없다** — 상호명·주소·업종뿐이다.
그래서 이 모듈은 할인 계산(`app/engine/benefit_combiner.py`)에 전혀 관여하지 않고,
`Place.accepts_local_currency`/`local_currency_verified_at`만 채운다 — 검색 결과에
정보성 배지로만 노출된다(금액에는 영향 없음).

**기존 Place만 대상, 새 Place는 절대 만들지 않는다** — 신규 매장 발굴은
`restaurant_registry.py`가 이미 전담하고, 여긴 "이미 있는 매장이 진짜 가맹점인지"
검증 플래그만 붙인다. 상호명이 같아도 다른 지점일 수 있어(같은 프랜차이즈가 여러
곳에 있는 경우), 주소 앞부분이 다르면 매칭하지 않고 unmatched로 집계한다 — 잘못된
매장에 배지를 붙이느니 안 붙이는 쪽을 택한다.

엔드포인트: UDDI는 포털 업로드 회차마다 바뀌므로 코드에 하드코딩하지 않고
LOCAL_CURRENCY_API_URL 환경변수로 받는다(착한가격업소·참가격과 동일한 관례).
미설정이면 아무것도 지어내지 않고 건너뛴다. 관리자가 직접 받은 CSV로 우회하는
경로도 열어둔다.
"""

import csv
import io
import logging
from datetime import UTC, datetime

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.domain.place import Place
from app.sources.public_api.franchise_price import normalize_store_name

logger = logging.getLogger(__name__)

_TIMEOUT = 30.0
_PER_PAGE = 1000
_MAX_PAGES = 100  # 전국 가맹점 명단 규모를 정확히 모르는 상태라 넉넉히 잡은 안전 상한


def _row_value(row: dict, *candidates: str):
    """지자체별로 컬럼명이 조금씩 갈릴 수 있어(착한가격업소·참가격과 동일한 이유)
    후보를 순서대로 본다."""
    for key in candidates:
        value = row.get(key)
        if value not in (None, ""):
            return value
    stripped = {str(k).replace(" ", ""): v for k, v in row.items()}
    for key in candidates:
        value = stripped.get(key.replace(" ", ""))
        if value not in (None, ""):
            return value
    return None


def parse_row(row: dict) -> dict | None:
    """한 행 → {name, address, category}. 상호명이 없으면 None (주소는 매칭
    disambiguation에 쓰지만 없어도 상호명만으로 매칭을 시도한다)."""
    name = _row_value(row, "가맹점명", "상호명", "업체명", "업소명", "storeName", "name")
    if not name:
        return None
    address = _row_value(
        row,
        "소재지도로명주소",
        "소재지 도로명주소",
        "도로명주소",
        "소재지지번주소",
        "지번주소",
        "소재지주소",
        "주소",
        "address",
    )
    category = _row_value(row, "업종", "업종명", "업태", "category")
    return {
        "name": str(name).strip(),
        "address": str(address).strip() if address else None,
        "category": str(category).strip() if category else None,
    }


def parse_csv_bytes(content: bytes) -> list[dict]:
    """지자체/포털에서 받은 CSV를 dict 행 목록으로 변환한다. data.go.kr이 점검
    중이거나 활용신청 전이어도 관리자가 직접 받은 파일로 우회할 수 있게 하는
    경로다(공공기관 파일은 cp949인 경우가 많다)."""
    text = None
    for encoding in ("utf-8-sig", "cp949", "utf-8"):
        try:
            text = content.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        raise ValueError("CSV 인코딩을 해석할 수 없습니다 (utf-8/cp949 지원)")
    return [dict(row) for row in csv.DictReader(io.StringIO(text))]


def _extract_rows(payload) -> list[dict]:
    """응답 본문에서 행 목록을 찾는다. 공공데이터포털 배포본이 odcloud 형식
    ({"data": [...]})일 수도, apis.data.go.kr 표준 봉투일 수도 있어 둘 다 훑는다
    (참가격 어댑터와 동일한 방식)."""
    if isinstance(payload, list):
        return [r for r in payload if isinstance(r, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("data", "items", "row", "list"):
        value = payload.get(key)
        if isinstance(value, list):
            return [r for r in value if isinstance(r, dict)]
        if isinstance(value, dict):
            return [value]
    body = payload.get("response", {}).get("body", {}) if payload.get("response") else {}
    items = body.get("items") if isinstance(body, dict) else None
    if isinstance(items, dict):
        items = items.get("item")
    if isinstance(items, list):
        return [r for r in items if isinstance(r, dict)]
    if isinstance(items, dict):
        return [items]
    return []


async def _fetch_rows() -> list[dict]:
    rows: list[dict] = []
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        for page in range(1, _MAX_PAGES + 1):
            params = {"page": page, "perPage": _PER_PAGE, "returnType": "JSON"}
            if settings.data_go_kr_key and "serviceKey" not in settings.local_currency_api_url:
                params["serviceKey"] = settings.data_go_kr_key
            resp = await client.get(settings.local_currency_api_url, params=params)
            resp.raise_for_status()
            batch = _extract_rows(resp.json())
            rows.extend(batch)
            if len(batch) < _PER_PAGE:
                break
    return rows


# /apply 엔드포인트가 매번 파일을 다시 안 받아도 재실행할 수 있게(관리자가 매칭
# 로직을 조정한 뒤 재적용하는 경우), 마지막으로 가져온/올린 원본 행을 프로세스
# 메모리에 잠깐 들고 있는다 — good_price.py의 _IMPORT_JOBS와 같은 성격의 캐시다.
# Render 재시작으로 사라져도 sync/import를 다시 부르면 되니 문제 없다.
_cached_raw_rows: list[dict] = []


def cache_raw_rows(raw_rows: list[dict]) -> None:
    global _cached_raw_rows
    _cached_raw_rows = raw_rows


def get_cached_raw_rows() -> list[dict]:
    return _cached_raw_rows


def import_rows(raw_rows: list[dict]) -> dict:
    """CSV로 올린 원본 행을 다음 /apply 호출을 위해 캐시해두고 파싱 가능 여부만
    확인한다. 이 데이터셋은 가격이 없어 프랜차이즈 가격표처럼 별도 DB 테이블에
    저장하지 않는다 — 원본 행 자체가 이미 명단 전부이므로 캐시로 충분하다."""
    cache_raw_rows(raw_rows)
    parsed = [p for p in (parse_row(r) for r in raw_rows) if p is not None]
    if not parsed:
        return {
            "raw_rows": len(raw_rows),
            "usable_rows": 0,
            "sample_raw_keys": sorted(raw_rows[0].keys())[:40] if raw_rows else [],
        }
    return {"raw_rows": len(raw_rows), "usable_rows": len(parsed)}


def _address_prefix(address: str | None, tokens: int = 2) -> str | None:
    """주소 맨 앞 토큰 몇 개("충청남도 아산시 …" → "충청남도아산시")만 뽑아 지점
    구분에 쓴다 — 전체 주소를 비교하면 도로명/지번 표기 차이로 같은 매장도 다르게
    보일 수 있어, 시도+시군구 수준까지만 본다."""
    if not address:
        return None
    parts = address.strip().split()
    if not parts:
        return None
    return "".join(parts[:tokens])


def _addresses_compatible(place_address: str | None, row_address: str | None) -> bool:
    """둘 다 주소가 있는데 앞부분이 다르면 같은 상호명이라도 다른 지점으로 보고
    거부한다. 어느 한쪽이라도 주소가 없으면 상호명 일치만으로 매칭을 허용한다
    (이미 region으로 Place를 좁혀둔 상태라 위험이 크지 않다)."""
    place_prefix = _address_prefix(place_address)
    row_prefix = _address_prefix(row_address)
    if place_prefix is None or row_prefix is None:
        return True
    return place_prefix == row_prefix


async def apply_local_currency_rows(
    session: AsyncSession,
    raw_rows: list[dict],
    *,
    region: str | None = None,
    offset: int = 0,
    limit: int = 500,
) -> dict:
    """지역화폐 가맹점 명단(raw_rows)과 상호명이 일치하는 기존 Place에만
    accepts_local_currency 플래그를 붙인다. `franchise_price.apply_to_places`와
    동일한 offset/limit + next_offset/done 계약을 따른다 — 매장 수가 많아 한 요청에
    다 돌리면 배포 환경 타임아웃에 걸리므로, 응답의 next_offset/done을 보고
    이어서 호출한다.

    MenuItem/Offer는 전혀 건드리지 않는다(이 데이터에 가격이 없다).
    """
    parsed = [p for p in (parse_row(r) for r in raw_rows) if p is not None]
    if not parsed:
        return {
            "raw_rows": len(raw_rows),
            "usable_rows": 0,
            "region": region,
            "offset": offset,
            "scanned_places": 0,
            "matched_places": 0,
            "unmatched": 0,
            "next_offset": offset,
            "done": True,
            "sample_raw_keys": sorted(raw_rows[0].keys())[:40] if raw_rows else [],
        }

    by_name: dict[str, list[dict]] = {}
    for row in parsed:
        by_name.setdefault(normalize_store_name(row["name"]), []).append(row)

    stmt = select(Place).order_by(Place.id)
    if region:
        stmt = stmt.where(Place.address.contains(region))
    places = (await session.execute(stmt.offset(offset).limit(limit))).scalars().all()

    matched = unmatched = 0
    now = datetime.now(UTC)
    for place in places:
        candidates = by_name.get(normalize_store_name(place.name))
        if not candidates:
            continue
        row = next(
            (c for c in candidates if _addresses_compatible(place.address, c["address"])), None
        )
        if row is None:
            # 상호명은 같은데 주소 앞부분이 달라 다른 지점으로 보인다 — 잘못된
            # 매장에 배지를 붙이느니 안 붙이는 쪽을 택한다(지어내지 않기).
            unmatched += 1
            continue
        place.accepts_local_currency = True
        place.local_currency_verified_at = now
        matched += 1

    await session.commit()

    next_offset = offset + len(places)
    return {
        "raw_rows": len(raw_rows),
        "usable_rows": len(parsed),
        "region": region,
        "offset": offset,
        "scanned_places": len(places),
        "matched_places": matched,
        "unmatched": unmatched,
        "next_offset": next_offset,
        "done": len(places) < limit,
    }


async def sync_local_currency_merchants(
    session: AsyncSession,
    *,
    region: str | None = None,
    offset: int = 0,
    limit: int = 500,
) -> dict:
    """전국지역화폐가맹점표준데이터를 API에서 가져와 곧바로 매칭까지 적용한다.
    LOCAL_CURRENCY_API_URL 미설정이면 아무것도 지어내지 않고 건너뛴다."""
    if not settings.local_currency_api_url:
        return {
            "skipped": True,
            "reason": "LOCAL_CURRENCY_API_URL이 설정되지 않았습니다. data.go.kr 활용신청 승인 후 "
            "요청 URL을 환경변수로 넣어주세요.",
        }
    try:
        raw_rows = await _fetch_rows()
    except httpx.HTTPError as exc:
        logger.warning("전국지역화폐가맹점표준데이터 조회 실패: %s", exc)
        return {"skipped": True, "reason": f"조회 실패: {exc.__class__.__name__}: {exc}"}

    cache_raw_rows(raw_rows)
    result = await apply_local_currency_rows(session, raw_rows, region=region, offset=offset, limit=limit)
    return {"fetched_rows": len(raw_rows), **result}
