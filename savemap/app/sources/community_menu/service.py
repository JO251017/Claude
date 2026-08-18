from datetime import UTC, datetime

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

# 가격이 이 이하로 차이나면 반올림/오탈자 오차로 보고 "동일"로 취급한다 — 1원
# 단위까지 완전히 일치해야만 갱신 스킵이 되면, 사실상 같은 가격도 매번 AI 검토를
# 태우게 된다.
PRICE_UNCHANGED_TOLERANCE = 0.5

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
) -> list[tuple[MenuItem, MenuPriceComparison | None, int, str, str | None]]:
    """메뉴판 사진 제보 저장. 예전엔 한 매장이 이 경로로 최초 1건만 등록되면
    이후 누구도 다시 등록할 수 없었다(2026-08-13, "한번 등록되면 추가 등록은
    안되게해") — 정보가 틀렸거나 가격이 올라도 영영 못 고치는 구조였다.
    사용자 지시(2026-08-18: "사장님 등록은 비활성화하고 사용자가 메뉴 등록하는
    구조로 바꿔 ... 가격이 다를경우 사진에 정보 시간 및 일자, 최신성을 반영해서
    검토해 AI로")에 따라 항목 단위 갱신으로 바꿨다:
    - 같은 이름의 기존 메뉴가 없으면 새로 만든다("created").
    - 있고 가격이 사실상 같으면 아무것도 안 바꾼다("unchanged") — 중복 제보로
      XP를 파밍하거나 매번 AI를 태우는 걸 막는다.
    - 있고 가격이 다르면 AI가 새로 올라온 사진과 기존 가격의 최신성(마지막
      확인 시각)을 보고 갱신할지 판단한다("updated"면 갱신, "rejected"면
      기존 값 유지). 검토할 사진(source_url)이 없으면 보수적으로 거부한다 —
      근거 없는 숫자로 덮어쓰지 않는다.
    반환값의 4번째 항목이 상태("created"/"unchanged"/"updated"/"rejected"),
    5번째가 AI 검토 사유(해당 없으면 None)다."""
    results: list[tuple[MenuItem, MenuPriceComparison | None, int, str, str | None]] = []
    for name, price, source_url in items:
        existing = (
            await session.execute(
                select(MenuItem).where(
                    MenuItem.place_id == place.id,
                    func.lower(func.trim(MenuItem.name)) == name.strip().lower(),
                )
            )
        ).scalar_one_or_none()

        if existing is None:
            item = MenuItem(
                place_id=place.id,
                name=name,
                price=price,
                source=SourceType.S4_REPORT,
                source_url=source_url,
                verified_at=datetime.now(UTC),
                ai_typical_price=await GeminiVisionClient().estimate_typical_price(name),
            )
            session.add(item)
            await session.commit()
            await session.refresh(item)
            xp_awarded = await award_xp(session, user_id, XpReason.MENU_REPORT)
            cmp = await sync_menu_offer(session, place, item)
            results.append((item, cmp, xp_awarded, "created", None))
            continue

        if abs(float(existing.price) - price) <= PRICE_UNCHANGED_TOLERANCE:
            cmp = await sync_menu_offer(session, place, existing)
            results.append((existing, cmp, 0, "unchanged", None))
            continue

        if not source_url:
            results.append(
                (existing, None, 0, "rejected", "새 가격을 확인할 사진이 없어 기존 가격을 유지했어요")
            )
            continue

        accept, reason = await GeminiVisionClient().review_price_update(
            item_name=name,
            image_url=source_url,
            old_price=float(existing.price),
            old_verified_at=existing.verified_at.isoformat() if existing.verified_at else "확인 시각 없음",
            new_price=price,
        )
        if not accept:
            results.append((existing, None, 0, "rejected", reason))
            continue

        existing.price = price
        existing.source_url = source_url
        existing.verified_at = datetime.now(UTC)
        existing.ai_typical_price = await GeminiVisionClient().estimate_typical_price(name)
        await session.commit()
        await session.refresh(existing)
        xp_awarded = await award_xp(session, user_id, XpReason.MENU_REPORT)
        cmp = await sync_menu_offer(session, place, existing)
        results.append((existing, cmp, xp_awarded, "updated", reason))

    return results
