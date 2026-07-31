from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.spatial import ewkt_point, to_h3
from app.domain.enums import SourceType, XpReason
from app.domain.menu_item import MenuItem
from app.domain.place import Place
from app.engine.offer_sync import sync_menu_offer
from app.engine.price_comparison import MenuPriceComparison
from app.gamification.service import award_xp
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
    category_name: str | None = None,
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
        category_name=category_name,
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
    user_id: str,
    place: Place,
    name: str,
    price: float,
    source_url: str | None = None,
) -> tuple[MenuItem, MenuPriceComparison, int]:
    """메뉴판 사진 제보 저장. 같은 매장에 같은 이름의 메뉴가 이미 있으면 중복 행을
    만들지 않고 가격만 최신으로 갱신한다. XP는 그 매장에 "새로운" 메뉴 정보를 더했을
    때만 지급 — 같은 메뉴를 반복 제보해서 XP를 캐는 걸 막기 위함."""
    existing = (
        await session.execute(
            select(MenuItem).where(
                MenuItem.place_id == place.id,
                func.lower(func.trim(MenuItem.name)) == name.strip().lower(),
            )
        )
    ).scalars().first()

    xp_awarded = 0
    if existing is not None:
        item = existing
        item.price = price
        item.verified_at = datetime.now(timezone.utc)
        if source_url:
            item.source_url = source_url
        await session.commit()
        await session.refresh(item)
    else:
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
        xp_awarded = await award_xp(session, user_id, XpReason.MENU_REPORT)

    cmp = await sync_menu_offer(session, place, item)
    return item, cmp, xp_awarded
