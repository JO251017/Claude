import logging

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.spatial import ewkt_point, to_h3
from app.domain.enums import SourceType
from app.domain.menu_item import MenuItem
from app.domain.place import Place
from app.engine.offer_sync import sync_menu_offer

logger = logging.getLogger(__name__)

# 행정안전부 "착한가격업소 현황" (data.go.kr 파일데이터 → odcloud 표준 오픈API).
# 정부·지자체가 "가격이 저렴한 업소"로 직접 지정·공표한 실제 데이터로, 업소명·주소·
# 전화번호·대표 품목/가격·좌표를 제공한다 — 카카오/네이버가 메뉴를 API로 주지 않는
# 상황에서, 지어내지 않고 초기(콜드스타트) 절약 정보를 전국 단위로 채울 수 있는
# 유일하게 확인된 합법적 원천이다.
#
# 엔드포인트 UDDI는 포털 업로드 회차마다 바뀌므로 코드에 하드코딩하지 않고
# GOOD_PRICE_API_URL 환경변수로 받는다 (활용신청 승인 후 포털 "오픈API 상세" 화면의
# 요청 URL 그대로). 미설정이면 아무것도 지어내지 않고 그냥 건너뛴다.

_PER_PAGE = 300
_MAX_PAGES = 40  # 전국 약 6~7천 건 안전 상한


def _row_value(row: dict, *candidates: str):
    """공공 파일데이터의 한글 컬럼명이 회차별로 조금씩 달라서(띄어쓰기 등) 후보를 순서대로 본다."""
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
    """'9,000', '9000원', '9,000원~' 같은 실데이터 표기를 숫자로. 해석 불가면 None (버림)."""
    if value in (None, ""):
        return None
    digits = "".join(ch for ch in str(value) if ch.isdigit())
    if not digits:
        return None
    price = float(digits)
    return price if 100 <= price <= 10_000_000 else None


def parse_row(row: dict) -> dict | None:
    """odcloud 응답 한 행 → 저장에 필요한 필드. 이름/좌표/메뉴가격 중 하나라도 없으면
    None (불완전한 데이터를 지어내서 채우지 않는다)."""
    name = _row_value(row, "업소명")
    try:
        lat = float(_row_value(row, "위도") or "")
        lng = float(_row_value(row, "경도") or "")
    except (TypeError, ValueError):
        return None
    if not name or not (33.0 < lat < 39.5 and 124.0 < lng < 132.0):
        return None

    menu_items: list[tuple[str, float]] = []
    for i in ("1", "2", "3"):
        item_name = _row_value(row, f"품목{i}", f"착한가격품목{i}", f"메뉴{i}")
        price = parse_price(_row_value(row, f"가격{i}", f"품목{i}가격"))
        if item_name and price:
            menu_items.append((str(item_name).strip(), price))
    if not menu_items:
        return None

    return {
        "name": str(name).strip(),
        "address": _row_value(row, "소재지도로명주소", "소재지 도로명 주소", "소재지", "주소"),
        "phone": _row_value(row, "전화번호", "연락처"),
        "category": _row_value(row, "업종", "구분", "업소구분"),
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


async def sync_good_price_stores(session: AsyncSession, region: str | None = None) -> dict:
    """착한가격업소를 Place + MenuItem(실제 대표메뉴 가격)으로 저장한다. 메뉴가 들어가면
    기존 절약 엔진(지역 비교 → 오퍼 자동 생성 → AI 절약 리포트)이 그대로 동작한다.
    region이 주어지면 주소에 그 문자열이 포함된 행만 (예: '평택') — Render 무료 플랜의
    요청 시간 제한 안에서 지역 단위로 나눠 넣기 위함."""
    if not settings.good_price_api_url:
        return {"skipped": "GOOD_PRICE_API_URL 미설정 — data.go.kr 활용신청 승인 후 요청 URL을 환경변수로 넣어주세요"}
    if not settings.data_go_kr_key:
        return {"skipped": "DATA_GO_KR_KEY 미설정"}

    raw_rows = await _fetch_rows()

    parsed = [p for p in (parse_row(r) for r in raw_rows) if p is not None]
    if region:
        parsed = [p for p in parsed if p["address"] and region in p["address"]]

    places_created = 0
    items_created = 0
    items_updated = 0
    for row in parsed:
        place = (
            await session.execute(
                select(Place).where(Place.name == row["name"], Place.address == row["address"])
            )
        ).scalars().first()
        if place is None:
            place = Place(
                name=row["name"],
                address=row["address"],
                phone=row["phone"],
                category_name=f"착한가격업소 > {row['category']}" if row["category"] else "착한가격업소",
                owner_user_id=None,
                geom=ewkt_point(row["lat"], row["lng"]),
                h3_r9=to_h3(row["lat"], row["lng"]),
            )
            session.add(place)
            await session.flush()
            places_created += 1

        for item_name, price in row["menu_items"]:
            existing = (
                await session.execute(
                    select(MenuItem).where(
                        MenuItem.place_id == place.id,
                        func.lower(func.trim(MenuItem.name)) == item_name.lower(),
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
                    # 대량 임포트라 AI 추정 통상가는 채우지 않는다 — 실측 데이터가
                    # 수천 건 들어오면 지역 비교가 자연스럽게 가능해진다.
                    ai_typical_price=None,
                )
                session.add(item)
                await session.flush()
                items_created += 1
            await sync_menu_offer(session, place, item)

    await session.commit()
    return {
        "fetched_rows": len(raw_rows),
        "usable_rows": len(parsed),
        "region": region,
        "places_created": places_created,
        "menu_items_created": items_created,
        "menu_items_updated": items_updated,
    }
