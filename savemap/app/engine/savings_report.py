from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

# SaveMap은 메뉴를 보여주는 서비스가 아니라 "이 매장이 실제로 얼마나 절약되고,
# 그 정보를 얼마나 믿을 수 있는지"를 분석해 보여주는 서비스다. 이 모듈이 그 핵심
# 산출물인 "AI 절약 리포트"를 만든다.
#
# 점수/등급/근거/한줄분석 전부 실제 집계값(절약률, 발견 수, 영수증 인증 수, 추천 수,
# 최근 검증 시각)만으로 계산되는 결정론적 함수다 — 매 검색 요청마다 LLM을 부르면
# 느리고 비싸고 무엇보다 매번 다른 문구가 나올 위험이 있어서, "AI가 즉석에서 지어내는"
# 문장이 아니라 실제 숫자에서 규칙적으로 도출되는 문장만 쓴다. 데이터가 부족하면
# 점수/등급을 아예 내지 않고 "데이터 부족"으로만 표시한다 (지어내지 않기).

FRESHNESS_WINDOW_DAYS = 30


@dataclass
class SavingsReport:
    score: int | None
    grade: str | None
    confidence_tier: str  # "high" | "medium" | "low"
    confidence_stars: int  # 1~5
    confidence_label: str
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


def _confidence(
    dining_count: int, discover_count: int, verification_count: int, recommend_count: int
) -> tuple[str, int, str]:
    total_signal = dining_count + discover_count + verification_count + recommend_count
    if dining_count >= 2 or total_signal >= 10:
        return "high", 5, "신뢰도 높음"
    if dining_count >= 1 or discover_count >= 3 or verification_count >= 2 or total_signal >= 3:
        return "medium", 3, "신뢰도 보통"
    return "low", 0, "데이터 부족"


def build_savings_report(
    *,
    savings_rate: float,
    discover_count: int,
    dining_count: int,
    recommend_count: int,
    verification_count: int,
    last_verified_at: datetime | None,
    benchmark_source: str | None,
    region_label: str = "주변",
) -> SavingsReport:
    tier, stars, label = _confidence(dining_count, discover_count, verification_count, recommend_count)

    fresh = (
        last_verified_at is not None
        and (datetime.now(timezone.utc) - last_verified_at) <= timedelta(days=FRESHNESS_WINDOW_DAYS)
    )

    reasons: list[str] = []
    if dining_count > 0:
        reasons.append(f"최근 영수증 인증 {dining_count}건")
    if discover_count > 0:
        reasons.append(f"실제 방문(발견) {discover_count}명")
    if recommend_count > 0:
        reasons.append(f"사용자 추천 {recommend_count}건")
    if fresh:
        reasons.append(f"최근 {FRESHNESS_WINDOW_DAYS}일 이내 데이터 반영")
    if benchmark_source == "region":
        reasons.append("주변 매장 실측 가격 데이터 반영")

    if tier == "low":
        if not reasons:
            reasons = ["실제 방문 데이터 부족", "영수증 데이터 부족", "가격 데이터 부족"]
        return SavingsReport(
            score=None,
            grade=None,
            confidence_tier=tier,
            confidence_stars=stars,
            confidence_label=label,
            reasons=reasons,
            one_line="아직 충분한 데이터가 쌓이지 않아 절약 정보를 계산 중이에요.",
        )

    score = 0.0
    score += min(max(savings_rate, 0.0), 40.0)  # 가격 경쟁력, 최대 40점
    score += min(dining_count * 5, 25)  # 영수증 인증, 최대 25점
    score += min(discover_count * 1, 15)  # 실제 발견/방문, 최대 15점
    score += min(recommend_count * 2, 10)  # 추천, 최대 10점
    score += 10 if fresh else 0  # 데이터 최신성, 최대 10점
    score = min(round(score), 100)
    grade = _grade_for_score(score)

    if tier == "high" and score >= 60:
        one_line = f"{region_label}에서 가격 경쟁력이 높은 매장으로 실제 이용 데이터도 충분해 신뢰도가 높습니다."
    elif tier == "high":
        one_line = f"{region_label} 평균과 비슷한 가격대지만, 실제 이용 데이터는 충분해 신뢰할 수 있는 정보예요."
    else:
        one_line = "일부 실제 이용 데이터가 있어 참고할 만하지만, 데이터가 더 쌓이면 신뢰도가 올라가요."

    return SavingsReport(
        score=score,
        grade=grade,
        confidence_tier=tier,
        confidence_stars=stars,
        confidence_label=label,
        reasons=reasons,
        one_line=one_line,
    )
