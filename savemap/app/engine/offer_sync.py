from datetime import UTC, datetime

from geoalchemy2.shape import to_shape
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import Category, Layer
from app.domain.menu_item import MenuItem
from app.domain.offer import Offer
from app.domain.place import Place
from app.engine.price_comparison import MenuPriceComparison, compare_menu_item

# select(Offer)에서 온 게 아니라 "아직 안 찾아봤다"는 뜻 — None(찾아봤는데 없음)과
# 구분해야 배치 재동기화(app/engine/offer_resync.py)가 미리 IN절로 조회해 넘긴 결과를
# 그대로 신뢰하고 건당 SELECT를 또 안 날릴 수 있다.
_UNSET = object()


async def sync_menu_offer(
    session: AsyncSession,
    place: Place,
    item: MenuItem,
    *,
    commit: bool = True,
    existing_offer: Offer | None = _UNSET,  # type: ignore[assignment]
) -> MenuPriceComparison:
    """메뉴 가격이 등록/제보되면(사장님 등록이든 사용자 제보든) 지도 검색에 뜨도록
    오퍼를 항상 생성/갱신한다 — 지도 검색(/v1/search)이 offer 테이블만 보는 구조라,
    메뉴만 있고 오퍼가 없으면 매장이 지도에서 완전히 사라지고(가격 없는 "발견됨"으로도
    못 뜸) "찾아갈 이유"가 안 보이는 문제를 해결하기 위함.
    지역 평균보다 확실히 싸면(비교 데이터 신뢰 가능) 절약률/절약액을 보여주고, 아직
    비교할 실측 데이터가 부족하면 AI 추정 통상가라도 기준으로 삼아 절약을 계산한다
    (실측이 항상 우선). 그것도 없으면 지어낸 할인 없이 등록된 실제 가격 그대로를
    보여준다 — 가격 정보 자체가 방문 여부를 판단할 "찾아갈 이유"다. menu_item_id로
    추적해 중복 생성하지 않는다. 비교 결과를 반환해 등록자에게 "지금 지도에 절약
    정보로 떴는지" 그 자리에서 알려줄 수 있게 한다.

    주의: 이 함수는 호출된 그 순간의 벤치마크로만 계산한다 — 나중에 주변에 매장이
    더 생기거나 새 벤치마크 소스가 채워져도 이미 만들어진 오퍼는 자동으로 안 바뀐다.
    "표본이 쌓이면 자동 승격"은 이 함수가 다시 불릴 때(직접 갱신 또는
    app/engine/offer_resync.py의 재동기화 배치)만 일어난다.

    commit/existing_offer는 재동기화 배치 전용 — 개별 호출부(사용자 제보, 착한가격업소
    임포트 등)는 기본값을 그대로 쓰면 예전과 동일하게 동작한다. 배치는 여러 건을 한
    트랜잭션에 묶고(commit=False), 기존 오퍼를 IN절로 미리 조회해 넘겨서(existing_offer=)
    건당 SELECT를 없앤다."""
    point = to_shape(place.geom)
    cmp = await compare_menu_item(session, item, point.y, point.x)

    if existing_offer is _UNSET:
        existing_offer = (
            await session.execute(select(Offer).where(Offer.menu_item_id == item.id))
        ).scalar_one_or_none()

    cheaper = bool(cmp.savings_amount and cmp.savings_amount > 0)
    if cheaper:
        label = {
            "region": "지역 평균보다 저렴",
            "gov": "참가격 시도 평균보다 저렴",
        }.get(cmp.benchmark_source, "통상가보다 저렴 (AI 추정)")
        title = f"{item.name} {round(item.price):,}원 · {label}"
        base_price = cmp.benchmark_price
        store_discount = cmp.savings_amount
    else:
        title = f"{item.name} {round(item.price):,}원"
        base_price = float(item.price)
        store_discount = 0.0

    # 벤치마크 메타(표본 수·재계산 시각)는 cheaper 여부와 무관하게 항상 기록한다 —
    # "비교는 했는데 안 싸더라"도 유효한 재계산 결과이고, 재동기화가 언제 마지막으로
    # 이 오퍼를 훑었는지는 benchmark_source가 None이어도 알아야 한다.
    now = datetime.now(UTC)
    if existing_offer is None:
        session.add(
            Offer(
                place_id=place.id,
                source=item.source,
                layer=Layer.CORE_BASE,
                category=Category.DISCOUNT,
                title=title,
                base_price=base_price,
                store_discount=store_discount,
                benchmark_source=cmp.benchmark_source if cheaper else None,
                benchmark_sample_count=cmp.sample_count,
                benchmark_synced_at=now,
                menu_item_id=item.id,
            )
        )
    else:
        existing_offer.title = title
        existing_offer.base_price = base_price
        existing_offer.store_discount = store_discount
        existing_offer.benchmark_source = cmp.benchmark_source if cheaper else None
        existing_offer.benchmark_sample_count = cmp.sample_count
        existing_offer.benchmark_synced_at = now

    if commit:
        await session.commit()
    return cmp
