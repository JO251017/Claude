"""AI Price Discovery Engine — 조사 대상 매장 선정(지시서 28-2/28-3).

가격 데이터가 없는 매장 전부를 AI에게 조사시키지 않는다. 먼저 진짜로 가격이
없는 매장만 후보로 좁히고(app/api/v1/admin.py의 GET /admin/places/stats가
이미 쓰는 "MenuItem이 하나도 없는 Place" 정의를 그대로 재사용 — 새 기준을
만들지 않는다), 그 안에서 "AI가 먼저 조사할 가치가 있는가"를 candidate_score로
매겨 우선순위를 정한다. 이 점수는 가격 자체의 신뢰도가 아니다."""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.franchise import FranchiseBrand
from app.domain.menu_item import MenuItem
from app.domain.place import Place
from app.domain.price_discovery import DiscoveryJobStatus, PriceDiscoveryJob
from app.sources.public_api.franchise_price import matches_brand

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


async def get_discovery_candidates(
    session: AsyncSession, *, region: str | None = None, limit: int = 20
) -> list[DiscoveryCandidate]:
    """가격이 없는(MenuItem이 하나도 없는) Place 중, 이미 진행 중인 조사 작업이
    없고 좌표가 있는 곳만 candidate_score 내림차순으로 최대 limit개 돌려준다.
    큐 유니크 인덱스(place_id, status IN pending/processing)와 이중으로 방어해서
    같은 매장에 조사 작업이 중복 생성되지 않게 한다(28-19)."""
    priced_place_ids = select(MenuItem.place_id).distinct()
    active_job_place_ids = select(PriceDiscoveryJob.place_id).where(
        PriceDiscoveryJob.status.in_(
            [DiscoveryJobStatus.PENDING, DiscoveryJobStatus.PROCESSING]
        )
    )
    stmt = select(Place).where(
        Place.id.notin_(priced_place_ids),
        Place.id.notin_(active_job_place_ids),
        Place.geom.isnot(None),
    )
    if region:
        stmt = stmt.where(Place.address.ilike(f"%{region}%"))
    # SQL에서 우선순위를 다 매기지 않고, 후보 풀을 넉넉히(limit*5) 가져와 파이썬에서
    # 점수를 매긴다 — 프랜차이즈 매칭이 SQL 표현식으로 깔끔히 안 되고(브랜드 키워드가
    # 가변적), 이 정도 규모(관리자가 한 번에 20건 정도만 돌리는 배치)에선 성능
    # 문제가 없다.
    stmt = stmt.order_by(Place.id).limit(limit * 5)
    places = list((await session.execute(stmt)).scalars().all())

    candidates: list[DiscoveryCandidate] = []
    for place in places:
        is_franchise = await _is_franchise(session, place.name)
        candidates.append(
            DiscoveryCandidate(place=place, score=_score(place, is_franchise), is_franchise=is_franchise)
        )
    candidates.sort(key=lambda c: (-c.score, c.place.id))
    return candidates[:limit]
