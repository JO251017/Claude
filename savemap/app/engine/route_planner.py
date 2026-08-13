from dataclasses import dataclass
from datetime import datetime, timezone

from app.domain.enums import RoutePreference
from app.engine.ranker import RankedOffer

# SaveMap의 원래 기획(하이브리드 AI 동선 추천)은 "예산/인원을 넣으면 실제로 얼마나
# 아끼는 코스가 나오는지"를 구체적으로 보여주는 게 핵심 차별화였다. 이 모듈은 그
# 1단계(어떤 후보를 코스에 넣을지)를 담당한다 — 전부 결정론적 순수 함수다. 요금/조합
# 선택 자체를 LLM에 맡기면 매 요청마다 느리고 비싸고 재현이 안 되므로, "실제 계산은
# 여기서 하고 LLM은 결과를 문장으로만 설명한다"는 이 코드베이스 전체의 원칙(예:
# savings_report.py, gemini.estimate_typical_price)을 그대로 따른다.


@dataclass
class RouteStop:
    ranked: RankedOffer
    order: int  # 화면에 보여줄 순서(1부터) — 선택 순서가 아니라 표시 순서


@dataclass
class RoutePlan:
    stops: list[RouteStop]
    budget: float
    total_spend: float
    total_savings: float
    remaining_budget: float
    fits_budget: bool  # True면 최소 1개 이상 선택됨


# preference별 후보 정렬 기준 — build_route가 "어떤 후보부터 예산에 채울지" 순서를
# 정하는 데 쓴다. 전부 이미 계산/저장돼 있는 실측값만 쓰고(가격/trust_score/
# verification_count/last_verified_at/distance_m), 값이 없는 항목은 임의로 좋은
# 점수를 주지 않고 정렬상 뒤로 민다(예: trust_score는 OfferCandidate 기본값 0.5가
# 이미 "모른다"는 뜻이라 그대로 둔다).
_EPOCH = datetime.min.replace(tzinfo=timezone.utc)


def _preference_sort_key(preference: RoutePreference):
    if preference == RoutePreference.CHEAPEST:
        return lambda r: r.breakdown.final_price
    if preference == RoutePreference.VERIFIED:
        return lambda r: (-r.candidate.trust_score, -r.candidate.verification_count)
    if preference == RoutePreference.RECENT:
        return lambda r: -(r.candidate.last_verified_at or _EPOCH).timestamp()
    if preference == RoutePreference.DISTANCE:
        return lambda r: r.candidate.distance_m
    raise ValueError(f"알 수 없는 RoutePreference: {preference}")


def _ordered_by_preference(
    ranked: list[RankedOffer], preference: RoutePreference | None
) -> list[RankedOffer]:
    """preference가 없으면 기존 그대로(rank_candidates가 이미 매긴 점수순) 순서를
    유지한다 — 이게 기존 build_route 호출부(파라미터 안 넘기는 곳)의 동작을 그대로
    보존하는 방법이다."""
    if preference is None:
        return ranked
    return sorted(ranked, key=_preference_sort_key(preference))


def build_route(
    ranked: list[RankedOffer],
    budget: float,
    max_stops: int,
    preference: RoutePreference | None = None,
) -> RoutePlan:
    """예산 안에서 실제 후보만 골라 코스를 짠다 — 지어낸 장소/가격 없이, ranked에 이미
    있는(점수순 정렬된) 실제 오퍼만 대상으로 한다.

    preference가 있으면 "어떤 후보부터 담을지" 순서를 그 기준으로 바꾼다(사용자가
    Step2에서 고른 조건, 2026-08-13) — 예산 제약 자체나 다양성 우선/채우기 2단계
    구조는 그대로다.

    두 번의 순회로 나눈다:
    1) 다양성 우선: 아직 안 쓴 카테고리인 후보만, 예산 안에서 채택.
    2) 채우기: 슬롯/예산이 남으면 카테고리 제약 없이 나머지 후보로 채운다.
    두 순회 모두 같은 정렬된 순서를 그대로 훑기만 해서 결정론적이다."""
    ordering = _ordered_by_preference(ranked, preference)
    selected: list[RankedOffer] = []
    used_categories: set = set()
    remaining = budget

    def _try_take(r: RankedOffer) -> bool:
        nonlocal remaining
        price = r.breakdown.final_price
        if price > remaining or len(selected) >= max_stops:
            return False
        selected.append(r)
        remaining -= price
        return True

    # 1차: 카테고리 다양성 우선
    for r in ordering:
        if len(selected) >= max_stops:
            break
        if r.candidate.category in used_categories:
            continue
        if _try_take(r):
            used_categories.add(r.candidate.category)

    # 2차: 남은 예산/슬롯을 카테고리 제약 없이 채움
    if len(selected) < max_stops:
        already = {id(r) for r in selected}
        for r in ordering:
            if len(selected) >= max_stops:
                break
            if id(r) in already:
                continue
            _try_take(r)

    # 표시 순서: 무료(0원) 먼저, 그다음 유료를 가격 오름차순 — 기획서 예시(무료주차 →
    # 무료체험 → 할인카페 → 마감할인식당)와 같은 모양을 재현한다.
    ordered = sorted(selected, key=lambda r: r.breakdown.final_price)

    total_spend = sum(r.breakdown.final_price for r in ordered)
    total_savings = sum(r.breakdown.total_savings for r in ordered)

    return RoutePlan(
        stops=[RouteStop(ranked=r, order=i + 1) for i, r in enumerate(ordered)],
        budget=budget,
        total_spend=total_spend,
        total_savings=total_savings,
        remaining_budget=budget - total_spend,
        fits_budget=bool(ordered),
    )


def _fallback_summary(stops: list[RouteStop], total_spend: float, total_savings: float) -> str:
    """Gemini가 없거나 실패했을 때 쓰는 결정론적 문장 — estimate_typical_price가 실패
    시 None으로 fail-soft하는 것과 같은 원칙: 절대 숫자/장소를 지어내지 않고, 이미
    계산된 값만 그대로 문장에 넣는다."""
    if not stops:
        return "지금 조건에 맞는 절약 코스를 만들 수 없어요. 예산이나 반경을 늘려서 다시 시도해보세요."
    names = ", ".join(s.ranked.candidate.place_name for s in stops[:3])
    more = f" 외 {len(stops) - 3}곳" if len(stops) > 3 else ""
    return (
        f"{names}{more}을(를) 이 순서로 다니면 총 {total_spend:,.0f}원만 쓰고 "
        f"{total_savings:,.0f}원을 아낄 수 있어요."
    )


async def generate_summary(
    plan: RoutePlan, party_size: int, gemini=None, context_note: str | None = None
) -> tuple[str, str]:
    """(문장, 출처) — 출처는 "ai" | "template". benchmark_source처럼 어디서 나온
    문장인지 그대로 노출해서 프론트/사용자가 AI 추정과 결정론적 결과를 구분할 수
    있게 한다. 코스가 비어 있으면 지어낼 게 없으니 Gemini를 아예 부르지 않는다.

    context_note: 사용자가 고른 활동/조건을 사람이 읽는 문장으로 미리 요약한 것
    (예: "활동: 식사, 커피 · 조건: 검증된 정보 우선"). Gemini가 "왜 이 코스를
    추천하는지" 설명할 때 참고만 하는 배경 정보이고, 숫자/장소는 여전히 stops에
    있는 것만 쓰게 프롬프트에서 강제한다(gemini._route_summary_prompt)."""
    if not plan.stops:
        return _fallback_summary(plan.stops, 0.0, 0.0), "template"

    from app.integrations.gemini import GeminiVisionClient

    client = gemini or GeminiVisionClient()
    text = await client.summarize_route(
        stops=[
            {
                "place_name": s.ranked.candidate.place_name,
                "category": s.ranked.candidate.category.value,
                "final_price": s.ranked.breakdown.final_price,
                "savings_rate": s.ranked.breakdown.savings_rate,
            }
            for s in plan.stops
        ],
        budget=plan.budget,
        party_size=party_size,
        total_spend=plan.total_spend,
        total_savings=plan.total_savings,
        context_note=context_note,
    )
    if text:
        return text, "ai"
    return _fallback_summary(plan.stops, plan.total_spend, plan.total_savings), "template"
