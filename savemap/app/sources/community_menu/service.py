from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.spatial import ewkt_point, to_h3
from app.domain.enums import SourceType
from app.domain.menu_item import MenuItem
from app.domain.place import Place
from app.engine.offer_sync import sync_menu_offer
from app.engine.price_comparison import MenuPriceComparison
from app.integrations.gemini import GeminiVisionClient

# 카카오/네이버 둘 다 메뉴·가격을 API로 제공하지 않는다 (공식 문서 확인됨) — 그리고
# 지어내지 않기 원칙상 크롤링도 안 쓴다. 그래서 실제 메뉴판을 본 "아무 사용자"나
# 사진으로 제보할 수 있게 한다 (기획 원안 S4). 사업자 등록(S3)과 달리 제보자가
# 그 매장의 "주인"이 되는 게 아니므로 owner_user_id는 비워둔다 — 나중에 실제
# 사장님이 사업자 콘솔에서 자기 매장으로 등록(claim)하면 그때 채워진다.


async def find_or_create_place(
    session: AsyncSession,
    kakao_place_id: str,
    name: str,
    address: str | None,
    phone: str | None,
    lat: float,
    lng: float,
) -> Place:
    existing = (
        await session.execute(select(Place).where(Place.kakao_place_id == kakao_place_id))
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    place = Place(
        name=name,
        address=address,
        phone=phone,
        kakao_place_id=kakao_place_id,
        owner_user_id=None,
        geom=ewkt_point(lat, lng),
        h3_r9=to_h3(lat, lng),
    )
    session.add(place)
    await session.commit()
    await session.refresh(place)
    return place


async def submit_menu_report(
    session: AsyncSession,
    place: Place,
    name: str,
    price: float,
    source_url: str | None = None,
) -> tuple[MenuItem, MenuPriceComparison]:
    item = MenuItem(
        place_id=place.id,
        name=name,
        price=price,
        source=SourceType.S4_REPORT,
        source_url=source_url,
        verified_at=datetime.now(timezone.utc),
        ai_typical_price=await GeminiVisionClient().estimate_typical_price(name),
    )
    session.add(item)
    await session.commit()
    await session.refresh(item)

    cmp = await sync_menu_offer(session, place, item)
    return item, cmp
