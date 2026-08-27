from dataclasses import dataclass

from app.core.config import settings
from app.domain.enums import RouteActivity
from app.engine.activity_classifier import classify_activity
from app.engine.models import OfferCandidate
from app.engine.savings_calculator import SavingsBreakdown, calculate_savings
from app.integrations.weather import WeatherSnapshot

# 날씨가 실제로 그 업종과 맞아떨어질 때만 중립(0.5)에서 이만큼 올려준다 — 지어낸
# 취향이 아니라 "비 오면 카페 간다"류의 상식적인 상관관계만 반영(아래 _weather_norm
# 주석 참고).
_WEATHER_BOOST = 0.30


@dataclass
class RankedOffer:
    candidate: OfferCandidate
    breakdown: SavingsBreakdown
    score: float


def _distance_norm(distance_m: float) -> float:
    """쌍곡 감쇠: 0m→1.0, half_m(기본 500m)→0.5, 3km→0.14. 지수 감쇠와 달리 반경
    끝에서 0으로 붕괴하지 않는다 — 멀지만 절약이 큰 매장이 점수에서 완전히
    사라지지 않게 하려는 것이다."""
    return 1.0 / (1.0 + max(distance_m, 0.0) / settings.rank_distance_half_m)


def _weather_norm(place_category_name: str | None, weather: WeatherSnapshot | None) -> float:
    """날씨 데이터가 없거나(키 미설정/조회 실패) 매장 업종을 못 알아내면 모든
    후보가 똑같이 0.5(중립)를 받는다 — 가중치를 곱해도 순위가 바뀌지 않는다는 뜻.
    실제로 날씨와 업종이 맞아떨어지는 경우만 살짝(0.5→0.8) 올려준다:
    비/눈 오는 날엔 카페(실내에서 비를 피하기 좋은 곳), 무더운 날엔 카페·디저트
    (빙수/아이스크림 등), 추운 날엔 식사류(activity_classifier의 DINING엔 국밥/
    찌개/탕 같은 따뜻한 메뉴 키워드가 이미 들어 있다) — activity_classifier.py가
    이미 검증해둔 키워드 매핑을 그대로 재사용할 뿐, 새 분류를 지어내지 않는다."""
    if weather is None:
        return 0.5
    activity = classify_activity(place_category_name)
    if activity is None:
        return 0.5

    if weather.condition in ("rain", "snow") and activity == RouteActivity.CAFE:
        return 0.5 + _WEATHER_BOOST
    if weather.is_hot and activity in (RouteActivity.CAFE, RouteActivity.DESSERT):
        return 0.5 + _WEATHER_BOOST
    if weather.is_cold and activity == RouteActivity.DINING:
        return 0.5 + _WEATHER_BOOST
    return 0.5


def _score(
    breakdown: SavingsBreakdown,
    trust: float,
    distance_m: float,
    place_category_name: str | None,
    weather: WeatherSnapshot | None,
) -> float:
    savings_norm = min(breakdown.savings_rate / 100.0, 1.0)
    trust_norm = min(max(trust, 0.0), 1.0)
    distance_norm = _distance_norm(distance_m)
    weather_norm = _weather_norm(place_category_name, weather)
    return (
        savings_norm * settings.rank_savings_weight
        + trust_norm * settings.rank_trust_weight
        + distance_norm * settings.rank_distance_weight
        + weather_norm * settings.rank_weather_weight
    )


def rank_candidates(
    candidates: list[OfferCandidate], weather: WeatherSnapshot | None = None
) -> list[RankedOffer]:
    ranked = []
    for candidate in candidates:
        breakdown = calculate_savings(candidate)
        score = _score(
            breakdown, candidate.trust_score, candidate.distance_m, candidate.place_category_name, weather
        )
        ranked.append(RankedOffer(candidate, breakdown, score))
    # 동점은 흔하다(콜드스타트에서 특히) — 예전엔 안정정렬이라 입력 순서(대개 거리순)가
    # "우연히" 남았을 뿐이다. 거리→offer_id를 명시적 타이브레이크로 둬서 의도된
    # 동작으로 확정한다(완전 결정론적).
    ranked.sort(key=lambda r: (-r.score, r.candidate.distance_m, r.candidate.offer_id))
    return ranked


def dedupe_by_place(ranked: list[RankedOffer], max_results: int | None = None) -> list[RankedOffer]:
    """매장 하나가 오퍼를 여러 개 가질 수 있어(메뉴마다 오퍼 하나) 그대로 보여주면
    매장 하나가 카드/마커 여러 개로 쪼개져 뜬다 — SaveMap은 매장 단위 절약 리포트를
    보여주는 서비스라, 매장당 가장 점수 높은 오퍼(= ranked에서 그 매장이 처음 나오는
    자리, 이미 점수순 정렬됨) 하나만 남긴다.
    max_results: 밀집 지역에서 결과가 수백 건씩 튀는 걸 막는 최종 상한 — 이미 점수순
    정렬된 뒤라 잘라내도 상위 결과는 바뀌지 않는다."""
    seen_places: set[int] = set()
    deduped: list[RankedOffer] = []
    for r in ranked:
        if r.candidate.place_id in seen_places:
            continue
        seen_places.add(r.candidate.place_id)
        deduped.append(r)
        if max_results is not None and len(deduped) >= max_results:
            break
    return deduped
