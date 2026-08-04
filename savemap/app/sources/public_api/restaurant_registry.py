import logging

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.spatial import ewkt_point, to_h3
from app.domain.place import Place
from app.sources.public_api.good_price import _geocode_missing_coords, _row_value, _truncate

logger = logging.getLogger(__name__)

# 행정안전부 지방행정 인허가 데이터(음식점/카페/술집) — 착한가격업소(수천 건)와 달리
# "정부가 실제로 영업 허가를 낸 업소 전체"라 전국 수십만 건 규모다. 가격 정보는 없지만
# (인허가 데이터라 당연히 없음), 지도의 기본 커버리지를 채우는 베이스로 우선 쓴다 —
# 절약/가격비교는 이 위에 착한가격업소·사용자제보 등 다른 소스가 나중에 얹힌다.
#
# apis.data.go.kr 표준 오픈API라 odcloud와 달리 요청 URL이 고정이고(UDDI 회차 없음),
# 계정 공용 일반 인증키(DATA_GO_KR_KEY)를 그대로 쓴다.
#
# 실제 응답 컬럼명은 문서를 직접 확인하지 못했다 — 행안부 LOCALDATA 표준 컬럼명(한글)과
# API 요청 필드코드(BPLC_NM 등) 계열 이름을 후보로 폭넓게 받아준다(good_price.py의
# _row_value와 동일한 방식). 실행 결과 usable_rows가 0으로 나오면 실제 필드명이
# 후보 목록과 달라서 그런 것이므로, 컬럼명을 확인해 후보를 추가해야 한다 — 필드명을
# 지어내는 게 아니라 실측 응답을 보고 조정하는 것.

_BASE_URL = "https://apis.data.go.kr/1741000"
CATEGORY_SLUGS = {
    "일반음식점": "general_restaurants",
    "휴게음식점": "rest_cafes",
    "유흥주점": "entertainment_bars",
}
_MAX_PER_PAGE = 100  # API 상한
_CLOSED_STATUS_WORDS = ("폐업", "휴업", "취소", "말소")


def parse_row(row: dict, category_label: str) -> dict | None:
    """인허가 행 → Place 저장에 필요한 필드. 상호명/주소 중 하나라도 없으면 None.
    폐업/휴업으로 표시된 행은 지도에 살아있는 가게처럼 보이면 안 되므로 건너뛴다."""
    name = _row_value(row, "사업장명", "업소명", "상호명", "BPLCNM", "bplcNm")
    if not name:
        return None
    address = _row_value(
        row, "도로명전체주소", "소재지도로명주소", "소재지전체주소", "지번주소", "RDNWHLADDR", "rdnWhlAddr"
    )
    if not address:
        return None

    status = _row_value(row, "영업상태명", "영업상태구분명", "TRDSTATENM", "trdStateNm") or ""
    if any(word in str(status) for word in _CLOSED_STATUS_WORDS):
        return None

    lat = lng = None
    raw_lat, raw_lng = _row_value(row, "위도", "좌표정보x", "LAT"), _row_value(row, "경도", "좌표정보y", "LOT")
    if raw_lat not in (None, "") and raw_lng not in (None, ""):
        try:
            lat, lng = float(raw_lat), float(raw_lng)
            if not (33.0 < lat < 39.5 and 124.0 < lng < 132.0):
                lat = lng = None
        except (TypeError, ValueError):
            lat = lng = None

    business_type = _row_value(row, "업태구분명", "위생업태명", "업종명", "UPTAENM")
    category = f"{category_label} > {business_type}" if business_type else category_label

    return {
        "name": str(name).strip(),
        "address": str(address).strip(),
        "phone": _row_value(row, "소재지전화", "전화번호", "지번전화", "LOCALPHONE"),
        "category": category,
        "lat": lat,
        "lng": lng,
    }


async def _fetch_page(slug: str, region: str, page: int, per_page: int) -> tuple[list[dict], bool]:
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            f"{_BASE_URL}/{slug}",
            params={
                "serviceKey": settings.data_go_kr_key,
                "pageNo": page,
                "numOfRows": per_page,
                "returnType": "JSON",
                "cond[RDN_WHLADDR::LIKE]": region,
            },
        )
        resp.raise_for_status()
        body = resp.json()
    rows = body.get("data", [])
    total_count = body.get("totalCount")
    has_more = (page * per_page) < total_count if isinstance(total_count, int) else len(rows) == per_page
    return rows, has_more


async def store_rows(session: AsyncSession, raw_rows: list[dict], category_label: str) -> dict:
    """파싱 → 지오코딩 → Place 저장. MenuItem은 만들지 않는다 — 이 소스에는 가격이 없다.
    이미 같은 이름+주소로 등록된 Place(착한가격업소 등 다른 소스가 먼저 넣은 경우 포함)는
    중복 생성하지 않고 건너뛴다."""
    parsed = [p for p in (parse_row(r, category_label) for r in raw_rows) if p is not None]
    geocoded_count = sum(1 for p in parsed if p["lat"] is None and p.get("address"))
    await _geocode_missing_coords(parsed)
    parsed = [p for p in parsed if p["lat"] is not None]  # 좌표 못 찾은 행은 지어내지 않고 버림

    places_created = 0
    places_skipped = 0
    failed_rows: list[dict] = []
    for row in parsed:
        try:
            existing = (
                await session.execute(
                    select(Place).where(Place.name == row["name"], Place.address == row["address"])
                )
            ).scalars().first()
            if existing is not None:
                places_skipped += 1
                continue
            place = Place(
                name=_truncate(row["name"], 255),
                address=_truncate(row["address"], 500),
                phone=_truncate(row["phone"], 32),
                category_name=_truncate(row["category"], 255),
                owner_user_id=None,
                geom=ewkt_point(row["lat"], row["lng"]),
                h3_r9=to_h3(row["lat"], row["lng"]),
            )
            session.add(place)
            await session.flush()
            places_created += 1
        except Exception as exc:  # noqa: BLE001 - 행 하나 실패가 나머지 수백~수천 건을 막으면 안 됨
            logger.warning("인허가 데이터 저장 실패 (%s): %s", row.get("name"), exc)
            await session.rollback()
            failed_rows.append({"name": row.get("name"), "reason": str(exc)[:200]})
            continue

    await session.commit()
    return {
        "parsed_rows": len(parsed),
        "geocoded": geocoded_count,
        "places_created": places_created,
        "places_skipped_existing": places_skipped,
        "failed_rows": len(failed_rows),
        "failed_samples": failed_rows[:5],
    }


async def sync_restaurant_registry(
    session: AsyncSession, category: str, region: str, page: int = 1, per_page: int = 100
) -> dict:
    """일반음식점/휴게음식점(카페)/유흥주점 인허가 현황 한 페이지를 가져와 Place로 저장한다.
    전국을 한 번에 돌리면 배포 환경 타임아웃에 걸리므로 region은 필수이고, region 안에서도
    page를 늘려가며 여러 번 호출한다 — 응답의 has_more가 true면 같은 region/category로
    page+1을 넣어 이어서 호출."""
    if category not in CATEGORY_SLUGS:
        return {"skipped": f"알 수 없는 category '{category}' — {', '.join(CATEGORY_SLUGS)} 중 하나여야 합니다"}
    if not region:
        return {"skipped": "region은 필수입니다 — 전국을 한 번에 가져오면 배포 환경 타임아웃(502)에 걸립니다"}
    if not settings.data_go_kr_key:
        return {"skipped": "DATA_GO_KR_KEY 미설정"}

    per_page = min(per_page, _MAX_PER_PAGE)
    raw_rows, has_more = await _fetch_page(CATEGORY_SLUGS[category], region, page, per_page)
    result = await store_rows(session, raw_rows, category_label=category)
    return {
        "category": category,
        "region": region,
        "page": page,
        "per_page": per_page,
        "fetched_rows": len(raw_rows),
        "has_more": has_more,
        **result,
    }
