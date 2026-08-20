"""프랜차이즈 본사 공식 가격표를 상호명 매칭으로 매장에 붙인다.

인허가 데이터로 들어온 매장 수만 건은 이름과 주소만 있고 가격이 비어 있다. 그중
체인점은 본사가 공식 가격을 공개하고 전국이 대체로 같은 값이라, 브랜드 가격표를 한 번
넣어두면 상호명만 보고 수천 곳의 가격을 채울 수 있다.

지어내지 않기 원칙: 이 모듈은 **가격을 만들어내지 않는다.** 관리자가 본사 공식 자료를
보고 올린 CSV의 값만 저장하고, 각 MenuItem에 브랜드 공식 페이지 URL과 기준 시점을
같이 남겨 출처를 추적할 수 있게 한다. 가격표가 비어 있으면 아무 일도 일어나지 않는다.

사용자 제보와의 우선순위: 같은 매장·같은 메뉴에 이미 사용자가 사진으로 제보한 가격이
있으면 덮어쓰지 않는다. 프랜차이즈라도 가맹점별로 가격이 다를 수 있고, 그 매장에서
실제로 찍힌 사진이 본사 표준가보다 구체적인 증거이기 때문이다.
"""

import csv
import io
import logging
import re
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import SourceType
from app.domain.franchise import FranchiseBrand, FranchisePrice
from app.domain.menu_item import MenuItem
from app.domain.place import Place
from app.engine.menu_name import normalize_menu_name
from app.engine.offer_sync import sync_menu_offer

logger = logging.getLogger(__name__)

# 상호명 매칭에서 무시할 문자(공백·괄호·구분자). "스타벅스 아산점" → "스타벅스아산점"
_NOISE = re.compile(r"[\s()（）\[\]{}·・\-–—_/\\,.']+")

# 키워드가 너무 짧으면 엉뚱한 가게에 붙는다("본"이 "본죽"뿐 아니라 "본가한식"에도
# 걸리는 식). 두 글자 미만은 아예 받지 않는다.
MIN_KEYWORD_LEN = 2


def normalize_store_name(name: str | None) -> str:
    if not name:
        return ""
    return _NOISE.sub("", name).lower()


def brand_keywords(brand: FranchiseBrand) -> list[str]:
    raw = brand.match_keywords or brand.name
    keywords = [normalize_store_name(k) for k in str(raw).split("|")]
    return [k for k in keywords if len(k) >= MIN_KEYWORD_LEN]


def matches_brand(store_name: str | None, brand: FranchiseBrand) -> bool:
    normalized = normalize_store_name(store_name)
    if not normalized:
        return False
    return any(keyword in normalized for keyword in brand_keywords(brand))


def parse_price(value) -> float | None:
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        price = float(value)
    else:
        digits = "".join(ch for ch in str(value) if ch.isdigit())
        if not digits:
            return None
        price = float(digits)
    return price if 100 <= price <= 1_000_000 else None


def parse_csv_bytes(content: bytes) -> list[dict]:
    """관리자가 올린 브랜드 가격표 CSV. 공공기관 파일과 달리 사람이 엑셀로 만드는
    경우가 많아 utf-8-sig(엑셀 기본 저장)를 먼저 본다."""
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


def _cell(row: dict, *candidates: str):
    for key in candidates:
        value = row.get(key)
        if value not in (None, ""):
            return str(value).strip()
    stripped = {str(k).replace(" ", ""): v for k, v in row.items()}
    for key in candidates:
        value = stripped.get(key.replace(" ", ""))
        if value not in (None, ""):
            return str(value).strip()
    return None


def parse_row(row: dict) -> dict | None:
    """CSV 한 줄 → {brand, keywords, official_url, item_name, price, period}.
    브랜드·메뉴명·가격 중 하나라도 없으면 None."""
    brand = _cell(row, "브랜드", "브랜드명", "brand")
    item_name = _cell(row, "메뉴명", "메뉴", "품목", "item")
    price = parse_price(_cell(row, "가격", "price"))
    if not brand or not item_name or price is None:
        return None
    return {
        "brand": brand,
        "keywords": _cell(row, "매칭키워드", "키워드", "keywords"),
        "official_url": _cell(row, "출처URL", "출처", "공식페이지", "url"),
        "item_name": item_name,
        "price": price,
        "period": (_cell(row, "기준년월", "기준", "period") or None),
    }


async def import_price_rows(session: AsyncSession, raw_rows: list[dict]) -> dict:
    """CSV 행을 브랜드/가격표로 저장(upsert)한다."""
    parsed = [p for p in (parse_row(r) for r in raw_rows) if p is not None]
    if not parsed:
        return {
            "raw_rows": len(raw_rows),
            "usable_rows": 0,
            "brands": 0,
            "prices_created": 0,
            "prices_updated": 0,
            "sample_raw_keys": sorted(raw_rows[0].keys())[:40] if raw_rows else [],
        }

    created = updated = 0
    touched_brands: set[str] = set()
    for item in parsed:
        brand = (
            await session.execute(
                select(FranchiseBrand).where(FranchiseBrand.name == item["brand"])
            )
        ).scalar_one_or_none()
        if brand is None:
            brand = FranchiseBrand(
                name=item["brand"],
                match_keywords=item["keywords"],
                official_url=item["official_url"],
            )
            session.add(brand)
            await session.flush()
        else:
            # 같은 브랜드의 뒷줄에서 키워드/URL을 채워 넣을 수 있게 하되, 이미 있는
            # 값을 빈 칸으로 지우지는 않는다.
            if item["keywords"]:
                brand.match_keywords = item["keywords"]
            if item["official_url"]:
                brand.official_url = item["official_url"]
        touched_brands.add(brand.name)

        normalized = normalize_menu_name(item["item_name"])[:255]
        existing = (
            await session.execute(
                select(FranchisePrice).where(
                    FranchisePrice.brand_id == brand.id,
                    FranchisePrice.normalized_item_name == normalized,
                )
            )
        ).scalar_one_or_none()
        if existing is None:
            session.add(
                FranchisePrice(
                    brand_id=brand.id,
                    item_name=item["item_name"],
                    price=item["price"],
                    effective_period=item["period"],
                )
            )
            created += 1
        else:
            existing.price = item["price"]
            existing.effective_period = item["period"]
            updated += 1

    await session.commit()
    return {
        "raw_rows": len(raw_rows),
        "usable_rows": len(parsed),
        "brands": len(touched_brands),
        "prices_created": created,
        "prices_updated": updated,
    }


async def apply_to_places(
    session: AsyncSession,
    region: str | None = None,
    offset: int = 0,
    limit: int = 500,
) -> dict:
    """저장된 브랜드 가격표를 상호명이 맞는 매장에 MenuItem으로 붙인다.

    매장 수가 수만 건이라 한 요청에 다 돌리면 배포 환경 타임아웃에 걸린다 —
    offset/limit으로 쪼개고, 응답의 next_offset/done을 보고 이어서 호출한다.
    """
    brands = (await session.execute(select(FranchiseBrand))).scalars().all()
    if not brands:
        return {
            "skipped": True,
            "reason": "등록된 프랜차이즈 가격표가 없습니다. "
            "먼저 /admin/import/franchise-prices-csv로 본사 공식 가격표를 올려주세요.",
        }

    brand_prices: dict[int, list[FranchisePrice]] = {}
    for brand in brands:
        rows = (
            await session.execute(
                select(FranchisePrice).where(FranchisePrice.brand_id == brand.id)
            )
        ).scalars().all()
        if rows:
            brand_prices[brand.id] = rows

    stmt = select(Place).order_by(Place.id)
    if region:
        stmt = stmt.where(Place.address.contains(region))
    places = (await session.execute(stmt.offset(offset).limit(limit))).scalars().all()

    matched_places = 0
    items_created = items_updated = items_kept = 0
    for place in places:
        brand = next((b for b in brands if matches_brand(place.name, b)), None)
        if brand is None or brand.id not in brand_prices:
            continue
        matched_places += 1

        for price_row in brand_prices[brand.id]:
            existing = (
                await session.execute(
                    select(MenuItem).where(
                        MenuItem.place_id == place.id,
                        MenuItem.normalized_name == price_row.normalized_item_name,
                    )
                )
            ).scalar_one_or_none()

            if existing is None:
                item = MenuItem(
                    place_id=place.id,
                    name=price_row.item_name,
                    price=float(price_row.price),
                    source=SourceType.S3_MERCHANT,
                    source_url=brand.official_url,
                    verified_at=datetime.now(UTC),
                )
                session.add(item)
                await session.flush()
                items_created += 1
            elif existing.source == SourceType.S3_MERCHANT:
                # 이전에 이 경로로 넣은 값이면 최신 가격표로 갱신한다.
                if float(existing.price) != float(price_row.price):
                    existing.price = float(price_row.price)
                    existing.verified_at = datetime.now(UTC)
                    items_updated += 1
                item = existing
            else:
                # 사용자가 그 매장에서 직접 찍어 올린 가격 등은 건드리지 않는다 —
                # 가맹점별로 값이 다를 수 있고, 현장 사진이 더 구체적인 증거다.
                items_kept += 1
                continue

            await sync_menu_offer(session, place, item)

    await session.commit()

    next_offset = offset + len(places)
    return {
        "region": region,
        "offset": offset,
        "scanned_places": len(places),
        "matched_places": matched_places,
        "menu_items_created": items_created,
        "menu_items_updated": items_updated,
        "menu_items_kept_user_reported": items_kept,
        "next_offset": next_offset,
        "done": len(places) < limit,
    }
