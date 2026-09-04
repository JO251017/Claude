from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.engine.price_comparison import NEARBY_RADIUS_MAX_KM
from app.engine.freshness import FRESHNESS_LABELS, freshness_tier

# SaveMap은 메뉴를 보여주는 서비스가 아니라 "이 매장이 실제로 얼마나 절약되고,
# 그 정보를 얼마나 믿을 수 있는지"를 분석해 보여주는 서비스다. 이 모듈이 그 핵심
# 산출물인 "AI 절약 리포트"를 만든다.
#
# 점수/등급/근거/한줄분석 전부 실제 집계값(절약률, 발견 수, 영수증 인증 수, 추천 수,
# 최근 검증 시각)만으로 계산되는 결정론적 함수다 — 매 검색 요청마다 LLM을 부르면
# 느리고 비싸고 무엇보다 매번 다른 문구가 나올 위험이 있어서, "AI가 즉석에서 지어내는"
# 문장이 아니라 실제 숫자에서 규칙적으로 도출되는 문장만 쓴다. 데이터가 부족하면
# 점수/등급을 아예 내지 않고 "데이터 부족"으로만 표시한다 (지어내지 않기).


@dataclass
class SavingsReport:
    score: int | None
    grade: str | None
    confidence_tier: str  # "high" | "medium" | "low"
    confidence_stars: int  # 0, 2, 3, 4, 5 중 하나 (0 = 데이터 부족, 별 미표시)
    confidence_label: str
    # 다단계 최신성(vNext, 2026-08-31) — "unknown"(확인 시각 정보 없음)/"fresh"(7일
    # 이내)/"normal"(30일 이내)/"stale"(90일 이내)/"expired"(90일 초과).
    freshness_tier: str = "unknown"
    freshness_label: str = FRESHNESS_LABELS["unknown"]
    days_since_verified: int | None = None
    reasons: list[str] = field(default_factory=list)
    one_line: str = ""


def _grade_for_score(score: int) -> str:
    if score >= 90:
        return "S+"
    if score >= 80:
        return "S"
    if score >= 70:
        return "A+"
    if score >= 60:
        return "A"
    if score >= 40:
        return "B"
    return "C"


# 비교 기준을 화면에 쓸 때의 표기. 근거가 강한 순서대로 region > gov > ai이며,
# 어느 기준인지 절대 감추지 않는다 — 추정치를 실측처럼 보이게 하지 않기 위해서다.
BENCHMARK_LABELS = {
    "region": "주변 매장 실측가",
    "gov": "한국소비자원 참가격 시도 평균가",
    "ai": "AI 추정 통상가",
}


_TIER_LABEL = {"high": "신뢰도 높음", "medium": "신뢰도 보통", "low": "데이터 부족"}


def region_scope_label(benchmark_radius_km: float | None) -> str:
    """실측 비교에 실제로 쓴 반경을 사용자에게 보일 말로 바꾼다(2026-09-04).

    3km 안에서 표본을 못 구하면 10km까지 넓혀서 비교하는데(price_comparison의
    BENCHMARK_RADIUS_LADDER_KM), 그걸 그대로 "주변"이라고 부르면 사실과 다르다 —
    10km 밖 매장 가격과 비교해놓고 "주변보다 싸다"고 말하는 셈이다. 반경이
    넓어졌으면 표현도 같이 넓힌다. 반경을 모르면(구 데이터) 기존 표현을 유지한다."""
    if benchmark_radius_km is None:
        return "주변"
    return "주변" if benchmark_radius_km <= NEARBY_RADIUS_MAX_KM else "같은 지역"
_TIER_ORDER = {"low": 0, "medium": 1, "high": 2}

# 가격 근거가 약할수록 절약률 점수 기여를 깎는다 — 그동안 AI 추정에서 나온
# 절약률도 실측과 똑같은 무게로 "신뢰도 높음" 점수에 들어가고 있었다(2026-08-22
# 확인). region은 표본 두께에 따라 별도 판정하므로 여기엔 없다.
BENCHMARK_SCORE_WEIGHT = {"gov": 0.75, "ai": 0.45}
# region이라도 이웃이 이 개수 미만(또는 재동기화 전이라 표본 수 자체를 모름)이면
# 아직 "얇은" 표본으로 보고 약간만 깎는다.
THIN_REGION_SAMPLE = 5
THIN_REGION_WEIGHT = 0.85
# AI 추정 절약률만으로는 tier가 "high"까지 못 간다 — 방문/인증이 아무리 많아도
# 가격 근거 자체가 약하면 상한을 씌운다.
BENCHMARK_TIER_CAP = {"ai": "medium"}

# 다단계 최신성 점수 보정 — 예전엔 30일 이내면 무조건 +10, 아니면 0이었다.
# expired(90일 초과)는 이제 감점한다: "오래된 정보인데도 신뢰도 점수는 그대로"가
# 되지 않게 하려는 것(vNext 지시서, "90일 이상 된 데이터는... 검색 ranking 감점").
# unknown(확인 시각 정보 자체가 없음)은 "모른다"일 뿐 "나쁘다"가 아니므로 0 —
# 데이터가 아예 없다고 벌점을 주면 없는 사실을 있는 것처럼 취급하는 셈이 된다.
_FRESHNESS_SCORE_BONUS = {"unknown": 0, "fresh": 10, "normal": 6, "stale": 0, "expired": -10}

# "절약 기회 점수"와 신뢰도(confidence_tier)는 서로 독립된 축이다(2026-09-01,
# 사용자 지시 §18 "점수가 높다고 신뢰도가 자동 상승하지 않는다"). 예전엔 사람
# 신호(방문/인증/추천)가 하나도 없으면(tier=="low") 점수 자체를 아예 안 매겨서,
# 활동 이력이 없는 콜드스타트 매장은 가격 비교가 끝났는데도 화면에 "계산 중"만
# 떴다. 이제 가격 근거만 있으면 tier와 무관하게 점수를 계산하되, 사람 신호가
# 전혀 없는 상태에서는 점수가 아무리 싸도 여기까지만 올라가게 상한을 둔다 —
# "절약 기회는 있어 보이지만 아직 아무도 검증하지 않았다"는 사실 자체를 점수에도
# 정직하게 반영한다.
_NO_SIGNAL_SCORE_CAP = 75


def _confidence_tier(
    dining_count: int, discover_count: int, verification_count: int, recommend_count: int
) -> str:
    total_signal = dining_count + discover_count + verification_count + recommend_count
    if dining_count >= 2 or total_signal >= 10:
        return "high"
    if dining_count >= 1 or discover_count >= 3 or verification_count >= 2 or total_signal >= 3:
        return "medium"
    return "low"


def _cap_tier_for_benchmark(tier: str, benchmark_source: str | None, savings_rate: float) -> str:
    """벤치마크가 아예 없어(savings_rate<=0) 절약을 안 주장하는 매장을, 방문 신호가
    많다는 이유로 끌어내릴 이유는 없다 — 절약을 주장할 때만 상한을 적용한다."""
    if savings_rate <= 0 or benchmark_source not in BENCHMARK_TIER_CAP:
        return tier
    cap = BENCHMARK_TIER_CAP[benchmark_source]
    return cap if _TIER_ORDER[tier] > _TIER_ORDER[cap] else tier


def _benchmark_score_weight(benchmark_source: str | None, sample_count: int | None) -> float:
    if benchmark_source == "region":
        if sample_count is not None and sample_count >= THIN_REGION_SAMPLE:
            return 1.0
        return THIN_REGION_WEIGHT
    return BENCHMARK_SCORE_WEIGHT.get(benchmark_source, 1.0)


def _stars_for(
    tier: str, benchmark_source: str | None, sample_count: int | None, dining_count: int
) -> int:
    """실제로는 0/2/3/4/5 다섯 단계다. tier가 "high"라도 가격 근거가 region이 아니면
    (또는 region인데 아직 표본이 얇으면) 만점(5)은 안 준다."""
    if tier == "low":
        return 0
    if tier == "medium":
        return 3 if benchmark_source in ("region", "gov") else 2
    strong_region = benchmark_source == "region" and (
        dining_count >= 2 or (sample_count is not None and sample_count >= THIN_REGION_SAMPLE)
    )
    return 5 if strong_region else 4


def build_savings_report(
    *,
    savings_rate: float,
    discover_count: int,
    dining_count: int,
    recommend_count: int,
    verification_count: int,
    last_verified_at: datetime | None,
    benchmark_source: str | None,
    benchmark_sample_count: int | None = None,
    benchmark_radius_km: float | None = None,
    region_label: str | None = None,
) -> SavingsReport:
    # 호출부가 문구를 직접 지정하지 않으면 실제 비교 반경에서 도출한다.
    region_label = region_label or region_scope_label(benchmark_radius_km)
    raw_tier = _confidence_tier(dining_count, discover_count, verification_count, recommend_count)
    tier = _cap_tier_for_benchmark(raw_tier, benchmark_source, savings_rate)
    stars = _stars_for(tier, benchmark_source, benchmark_sample_count, dining_count)
    label = _TIER_LABEL[tier]
    capped_by_benchmark = tier != raw_tier

    fresh_tier, days_since_verified = freshness_tier(last_verified_at, now=datetime.now(timezone.utc))
    fresh_label = FRESHNESS_LABELS[fresh_tier]

    reasons: list[str] = []
    if dining_count > 0:
        reasons.append(f"최근 영수증 인증 {dining_count}건")
    if discover_count > 0:
        reasons.append(f"실제 방문(발견) {discover_count}명")
    if recommend_count > 0:
        reasons.append(f"사용자 추천 {recommend_count}건")
    if fresh_tier in ("fresh", "normal"):
        reasons.append(f"최근 확인된 정보예요 ({days_since_verified}일 전)")
    elif fresh_tier == "expired":
        reasons.append(f"정보가 오래됐어요 ({days_since_verified}일 전 확인) — 최신 정보인지 확인해보세요")
    if benchmark_source == "region":
        # 표본 2곳과 30곳을 같은 말("실측 데이터 반영")로 뭉개지 않는다 — 실제
        # 개수를 알면 그만큼 구체적으로, 모르면(재동기화 전 구 데이터) 기존 문구로.
        reasons.append(
            f"{region_label} 매장 {benchmark_sample_count}곳 실측가와 비교"
            if benchmark_sample_count is not None
            else f"{region_label} 매장 실측 가격 데이터 반영"
        )
    elif benchmark_source == "gov":
        reasons.append("한국소비자원 참가격 시도 평균가 대비 비교")
    elif benchmark_source == "ai":
        reasons.append("AI(Gemini) 추정 통상가 대비 비교")

    # medium/high tier(사람 신호가 이미 medium 문턱을 넘음)는 예전부터 benchmark_source
    # 유무와 무관하게 항상 점수를 계산해왔다 — 그 동작은 그대로 둔다. 이번에 새로
    # 여는 건 tier=="low"(사람 신호가 전혀 없는 콜드스타트) 케이스뿐이라, "진짜
    # 데이터 부족"(점수를 아예 못 매기는 경우) 판정도 low일 때만 가격 근거 유무로
    # 가른다.
    has_price_evidence = savings_rate > 0 and benchmark_source is not None

    if tier == "low" and not has_price_evidence:
        # 진짜 데이터 부족 — 가격 비교 자체가 안 됐으니 점수를 지어낼 게 없다.
        if not reasons:
            reasons = ["실제 방문 데이터 부족", "영수증 데이터 부족", "가격 데이터 부족"]
        return SavingsReport(
            score=None,
            grade=None,
            confidence_tier=tier,
            confidence_stars=stars,
            confidence_label=label,
            freshness_tier=fresh_tier,
            freshness_label=fresh_label,
            days_since_verified=days_since_verified,
            reasons=reasons,
            one_line="아직 충분한 데이터가 쌓이지 않아 절약 정보를 계산 중이에요.",
        )

    # 절약 기회 점수 배점(2026-09-01 재조정, 사용자 지시 §18 — 신뢰도와 독립):
    # 가격 경쟁력(최대 55점)에 벤치마크 품질을 곱한다 — AI 추정 기반 절약률은
    # 최대 24.75점, 참가격 통계는 41.25점, 실측(표본이 얇으면 46.75점)은 55점까지만
    # 받는다. 근거가 약한 숫자가 실측과 똑같은 무게로 점수를 만드는 일이 없게
    # 하려는 것이다.
    benchmark_weight = _benchmark_score_weight(benchmark_source, benchmark_sample_count)
    score = 0.0
    score += min(max(savings_rate, 0.0), 55.0) * benchmark_weight  # 가격 경쟁력, 최대 55점
    score += min(dining_count * 5, 18)  # 영수증 인증, 최대 18점
    score += min(discover_count * 1, 10)  # 실제 발견/방문, 최대 10점
    score += min(recommend_count * 2, 7)  # 추천, 최대 7점
    score += _FRESHNESS_SCORE_BONUS[fresh_tier]  # 데이터 최신성, -10~+10점
    score = max(0, min(round(score), 100))

    if tier == "low":
        # 사람 신호가 전혀 없다 — "절약 기회는 있어 보이지만 아직 아무도
        # 검증하지 않았다"는 사실을 점수에도 정직하게 반영해 상한을 씌운다
        # (confidence_tier/stars는 그대로 "low"/0 — 점수와 신뢰도는 독립된 축).
        score = min(score, _NO_SIGNAL_SCORE_CAP)
        grade = _grade_for_score(score)
        source_label = BENCHMARK_LABELS.get(benchmark_source, "비교 기준가")
        one_line = (
            f"{source_label} 대비로는 저렴하지만, 아직 실제 방문/인증 데이터가 부족해 "
            "신뢰도는 낮게 매겨졌어요."
        )
        if not reasons:
            reasons = ["실제 방문 데이터 부족", "영수증 데이터 부족"]
        return SavingsReport(
            score=score,
            grade=grade,
            confidence_tier=tier,
            confidence_stars=stars,
            confidence_label=label,
            freshness_tier=fresh_tier,
            freshness_label=fresh_label,
            days_since_verified=days_since_verified,
            reasons=reasons,
            one_line=one_line,
        )

    grade = _grade_for_score(score)

    if tier == "high" and score >= 60:
        one_line = f"{region_label}에서 가격 경쟁력이 높은 매장으로 실제 이용 데이터도 충분해 신뢰도가 높습니다."
    elif tier == "high":
        one_line = f"{region_label} 평균과 비슷한 가격대지만, 실제 이용 데이터는 충분해 신뢰할 수 있는 정보예요."
    else:
        one_line = "일부 실제 이용 데이터가 있어 참고할 만하지만, 데이터가 더 쌓이면 신뢰도가 올라가요."
    if capped_by_benchmark:
        # 방문/인증 신호는 "높음" 수준인데 tier가 "보통"에 묶인 이유를 감추지 않는다.
        one_line += " (AI 추정 기준이라 신뢰도는 '보통'까지만 매겼어요)"

    return SavingsReport(
        score=score,
        grade=grade,
        confidence_tier=tier,
        confidence_stars=stars,
        confidence_label=label,
        freshness_tier=fresh_tier,
        freshness_label=fresh_label,
        days_since_verified=days_since_verified,
        reasons=reasons,
        one_line=one_line,
    )
