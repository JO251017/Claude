from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import PlaceMenuAlreadyRegisteredError
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
    name: str,
    address: str | None,
    phone: str | None,
    lat: float,
    lng: float,
    category_name: str | None = None,
    place_id: int | None = None,
    kakao_place_id: str | None = None,
) -> Place:
    # place_id가 있으면 최우선 — 인허가 데이터 등으로 이미 SaveMap DB에 있는 Place를
    # kakao_place_id 없이(=None) 바로 붙여야 하는 경우라, kakao_place_id 조회보다 먼저
    # 확인해야 한다. kakao_place_id는 nullable+unique라 None으로 조회하면 registry
    # Place가 수천 건이라 여러 행이 걸려 MultipleResultsFound가 나므로, None일 땐
    # 아예 조회하지 않는다.
    if place_id is not None:
        existing = await session.get(Place, place_id)
        if existing is not None:
            return existing
    if kakao_place_id:
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


async def submit_menu_report_batch(
    session: AsyncSession,
    user_id: str,
    place: Place,
    items: list[tuple[str, float, str | None]],
) -> list[tuple[MenuItem, MenuPriceComparison, int]]:
    """메뉴판 사진 제보 저장. 한 매장은 이 오픈된(사업자 인증 불필요, 로그인만
    필요) 제보 경로로 최초 1회만 등록할 수 있다 — 이미 메뉴가 하나라도 있으면
    배치 전체를 거부한다(사용자 지시, 2026-08-13: "한번 등록되면 일단 추가 등록은
    안되게해"). 프론트가 애초에 가격 정보 없는 매장에서만 이 흐름을 보여주므로
    보통은 걸릴 일이 없고, 두 사용자가 거의 동시에 같은 매장을 제보하는 경쟁 상황을
    막는 서버 사이드 안전장치 역할이 크다. 사업자 콘솔(소유권 확인된 별도
    엔드포인트)은 이 제한과 무관하게 계속 자유롭게 수정 가능.

    사진 한 장에서 메뉴 여러 개가 한 번에 인식되는 게 정상 흐름이라(예: 아메리카노
    +라떼+...) items를 배치로 받고, "이미 등록됨" 판정은 배치 시작 전 딱 한 번만
    한다 — 항목마다 확인하면 같은 배치의 두 번째 항목부터 스스로를 막아버린다."""
    already_registered = (
        await session.execute(
            select(func.count()).select_from(MenuItem).where(MenuItem.place_id == place.id)
        )
    ).scalar_one()
    if already_registered > 0:
        raise PlaceMenuAlreadyRegisteredError()

    results: list[tuple[MenuItem, MenuPriceComparison, int]] = []
    for name, price, source_url in items:
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
        results.append((item, cmp, xp_awarded))

    return results
