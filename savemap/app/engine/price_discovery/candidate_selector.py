"""AI Price Discovery Engine — 조사 대상 매장 선정(지시서 28-2/28-3).

가격 데이터가 없는 매장 전부를 AI에게 조사시키지 않는다. 먼저 진짜로 가격이
없는 매장만 후보로 좁히고(app/api/v1/admin.py의 GET /admin/places/stats가
이미 쓰는 "MenuItem이 하나도 없는 Place" 정의를 그대로 재사용 — 새 기준을
만들지 않는다), 그 안에서 "AI가 먼저 조사할 가치가 있는가"를 candidate_score로
매겨 우선순위를 정한다. 이 점수는 가격 자체의 신뢰도가 아니다."""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import Category
from app.domain.franchise import FranchiseBrand
from app.domain.menu_item import MenuItem
from app.domain.offer import Offer
from app.domain.place import Place
from app.domain.price_discovery import DiscoveryJobStatus, PriceDiscoveryJob
from app.sources.public_api.franchise_price import matches_brand

# 이 두 카테고리는 "메뉴/가격"이 아니라 시설·혜택 안내 데이터라, AI에게 "메뉴 가격을
# 찾아줘"라고 시키는 게 애초에 말이 안 된다 — 전국주차장정보표준데이터(FREE_PARKING)/
# 체육시설 공공데이터(LOCAL_BENEFIT) 어댑터(app/sources/public_api/adapters.py)가
# MenuItem 없이 Offer만 만드는 자리라, 예전엔 candidate_selector가 "MenuItem이
# 없다"는 것만 보고 이런 매장까지 후보로 골랐다 — 실사용 중 발견된 버그(2026-08-31,
# "매장명이 다 주차장이랑 상관없어 보여서 전부 거절했다").
_NON_MENU_CATEGORIES = (Category.FREE_PARKING, Category.LOCAL_BENEFIT)

# 정확한 가중치는 현재 데이터에 맞게 조정 가능한 값이다(지시서 28-3) — 하드코딩된
# "정답"이 아니라 초기 추정치. 프랜차이즈면 공식 가격표를 찾을 가능성이 가장
# 높다고 보고 가장 크게 준다.
FRANCHISE_BONUS = 40
PHONE_BONUS = 15
ADDRESS_BONUS = 10
CATEGORY_BONUS = 5


@dataclass
class DiscoveryCandidate:
    place: Place
    score: int
    is_franchise: bool


async def _is_franchise(session: AsyncSession, place_name: str | None) -> bool:
    if not place_name:
        return False
    brands = (await session.execute(select(FranchiseBrand))).scalars().all()
    return any(matches_brand(place_name, b) for b in brands)


def _score(place: Place, is_franchise: bool) -> int:
    score = 0
    if is_franchise:
        score += FRANCHISE_BONUS
    if place.phone:
        score += PHONE_BONUS
    if place.address:
        score += ADDRESS_BONUS
    if place.category_name:
        score += CATEGORY_BONUS
    return score


def _candidate_stmt(*, region: str | None, pool_limit: int):
    """순수 함수로 분리 — DB 없이도 컴파일된 SQL로 필터 조건을 검증할 수 있다
    (price_comparison._region_prices_stmt와 같은 이유)."""
    priced_place_ids = select(MenuItem.place_id).distinct()
    active_job_place_ids = select(PriceDiscoveryJob.place_id).where(
        PriceDiscoveryJob.status.in_(
            [DiscoveryJobStatus.PENDING, DiscoveryJobStatus.PROCESSING]
        )
    )
    # 관리자가 명시적으로 거절(reject_job)한 매장은 다시 후보로 뽑지 않는다 —
    # 실사용 중 발견된 버그(2026-08-31): 거절해도 job.status는 FAILED가 될 뿐이라
    # "진행 중" 조건(위 active_job_place_ids)에 안 걸리고, MenuItem도 여전히
    # 없으니 다음 "한 번 실행" 때 같은 매장이 새 job으로 또 뽑혀서 관리자가
    # 거절해도 거절한 티가 안 났다("또 떠 3건이"). REJECTED_BY_ADMIN은
    # reject_job(orchestrator.py)이 남기는 값 그대로 — 여기서 새 상수로 만들지
    # 않고 그 문자열을 그대로 재사용한다.
    rejected_place_ids = select(PriceDiscoveryJob.place_id).where(
        PriceDiscoveryJob.error_code == "REJECTED_BY_ADMIN"
    )
    non_menu_place_ids = select(Offer.place_id).where(Offer.category.in_(_NON_MENU_CATEGORIES))
    stmt = select(Place).where(
        Place.id.notin_(priced_place_ids),
        Place.id.notin_(active_job_place_ids),
        Place.id.notin_(rejected_place_ids),
        Place.id.notin_(non_menu_place_ids),
        Place.geom.isnot(None),
    )
    if region:
        stmt = stmt.where(Place.address.ilike(f"%{region}%"))
    return stmt.order_by(Place.id).limit(pool_limit)


async def get_discovery_candidates(
    session: AsyncSession, *, region: str | None = None, limit: int = 20
) -> list[DiscoveryCandidate]:
    """가격이 없는(MenuItem이 하나도 없는) Place 중, 주차장/체육시설처럼 애초에
    메뉴가 있을 수 없는 곳과 이미 진행 중인 조사 작업이 있는 곳을 제외하고,
    좌표가 있는 곳만 candidate_score 내림차순으로 최대 limit개 돌려준다. 큐
    유니크 인덱스(place_id, status IN pending/processing)와 이중으로 방어해서
    같은 매장에 조사 작업이 중복 생성되지 않게 한다(28-19)."""
    # SQL에서 우선순위를 다 매기지 않고, 후보 풀을 넉넉히(limit*5) 가져와 파이썬에서
    # 점수를 매긴다 — 프랜차이즈 매칭이 SQL 표현식으로 깔끔히 안 되고(브랜드 키워드가
    # 가변적), 이 정도 규모(관리자가 한 번에 몇 건만 돌리는 배치)에선 성능 문제가 없다.
    stmt = _candidate_stmt(region=region, pool_limit=limit * 5)
    places = list((await session.execute(stmt)).scalars().all())

    candidates: list[DiscoveryCandidate] = []
    for place in places:
        is_franchise = await _is_franchise(session, place.name)
        candidates.append(
            DiscoveryCandidate(place=place, score=_score(place, is_franchise), is_franchise=is_franchise)
        )
    candidates.sort(key=lambda c: (-c.score, c.place.id))
    return candidates[:limit]
