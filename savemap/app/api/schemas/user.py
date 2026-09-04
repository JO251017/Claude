from pydantic import BaseModel


class DailySavedPointResponse(BaseModel):
    """MY탭 절약 추이 미니 차트 한 칸(2026-09-04). date는 "YYYY-MM-DD"(UTC 일 기준,
    SavingsSummaryResponse.today_saved와 같은 자정 경계)."""

    date: str
    amount: float


class MerchantStatusResponse(BaseModel):
    """MY 탭 "사업자 콘솔" 바로가기를 조건부로 보여줄지 판단하는 용도(2-3, 2026-08-13)."""

    is_verified_merchant: bool


class SavingsSummaryResponse(BaseModel):
    total_saved: float
    level: int
    title: str
    next_threshold: float | None
    remaining_to_next: float | None
    progress_pct: float
    certification_count: int
    monthly_saved: float = 0.0
    # MY 탭 절약 요약 재구조화(2-1, 2026-08-13): 오늘 누적 절약을 메인으로,
    # 주간/한달(monthly_saved)/연간을 나란히 보여준다.
    today_saved: float = 0.0
    weekly_saved: float = 0.0
    yearly_saved: float = 0.0
    # 탐험가 칭호(2026-08-13) — 절약금액이 아니라 실제 방문 인증한 서로 다른 매장
    # 수 기반. 위 level/title(절약금액 기준)과는 독립된 축이라 explorer_ 접두어로
    # 스키마에서부터 확실히 구분한다("레벨 시스템 두 벌" 혼선을 반복하지 않기 위함).
    discovered_place_count: int
    explorer_title: str
    explorer_next_threshold: int | None
    explorer_remaining_to_next: int | None
    # 방문 횟수 칭호(2-2, 2026-08-13) — certification_count(영수증/직접입력 인증
    # 건수)를 그대로 재사용한 칭호 사다리. 기존 .certify-row UI는 숨기고 이 값을
    # "방문 인증" 진행도로 노출한다(사용자 확정).
    visit_count: int
    visit_title: str
    visit_next_threshold: int | None
    visit_remaining_to_next: int | None
    # 추천 횟수 칭호(2-2, 2026-08-13)
    recommend_count: int
    recommend_title: str
    recommend_next_threshold: int | None
    recommend_remaining_to_next: int | None
    # 연속 방문 스트릭(2026-08-30, "재미 개선 — 연속 방문 스트릭") — 발견/영수증
    # 인증/추천 중 하나라도 한 날을 "활동한 날"로 센다. streak_at_risk가 true면
    # 스트릭이 있는데 오늘 아직 활동을 안 한 상태 — 오늘 안에 하나라도 하면 이어지고,
    # 자정을 넘기면 0으로 끊긴다.
    streak_days: int = 0
    streak_active_today: bool = False
    streak_at_risk: bool = False
    # 펫 성장치(2026-09-01, 사용자 확정 비율: 발견 2/추천 4/방문 6/가격 인증 12) —
    # 예전엔 프론트가 discovered_place_count+visit_count+recommend_count를 전부
    # 가중치 1로 직접 더했다(app.js:1124). 이제 서버가 가중치를 적용해 계산한
    # 값을 그대로 내려준다 — "실제 행동으로만 증가한다"를 서버가 보장하기 위함.
    growth_score: int = 0
    # 절약 통계(2026-09-04, "마이탭에서 절약을 얼마나 했는지도 통계로 나타내") —
    # 최근 7일 일별 절약액 추이. 활동 없는 날도 0으로 채워져 있다(zero-fill).
    daily_saved: list[DailySavedPointResponse] = []


class DigestResponse(BaseModel):
    """AI 활용 확대 안건 C(2026-08-31) — 개인화 절약 다이제스트. source가
    one_line_source(SavingsReportItem)와 같은 원칙으로 "ai"|"template"를 그대로
    노출한다 — AI 문장인지 결정론적 폴백인지 감추지 않는다."""

    summary_text: str
    source: str


class PetReactionResponse(BaseModel):
    """AI MVP §D(2026-09-01) — 펫 레벨업 축하 대사. source는 다른 AI 캐시
    필드들과 같은 원칙으로 "ai"|"template"."""

    message: str
    source: str
