"""수익성 계산 코어 (PRD 9장 1단계). 모든 요율·기준값은 Config에서만 읽는다.
내부 계산은 Fraction(정확 계산), 저장·보고는 1원 단위 반올림."""
import math
from dataclasses import dataclass, field
from fractions import Fraction
from typing import NamedTuple

from src.common.config import Config
from src.common.csvio import parse_number

VERDICT_RANK = {"통과": 0, "보류": 1, "탈락": 2}
LABEL = "관측: C·S·M / 추정: 광고비·반품률·수수료율"
TAX_NOTE = "세전(부가세·소득세 미반영)"

# 사유 코드 -> 분포 집계용 라벨
REASON_LABELS = {
    "P_NONPOS": "고객 배송비가 시장 기준가 이상",
    "BELOW_TMIN": "T_sug < T_min",
    "STRESS_NEG": "보수 시나리오 순손실",
    "STALE": "최신성 초과 - 참고용",
    "GROWTH_FAIL": "성장률 조회 실패",
    "GROWTH_UNCONFIRMED": "성장률 미확인",
    "GROWTH_FLOOR": "성장률 하한 미달",
    "NO_COST": "원가 미입력",
    "NO_MARKET": "시세 미입력",
    "AI_INFO_MISSING": "AI 노출 정보 부족",
    "INPUT_ERROR": "입력 오류",
}


class Reason(NamedTuple):
    code: str
    text: str


def round_half_up(x: Fraction) -> int:
    """1원 단위 반올림(0.5는 절댓값이 커지는 쪽)."""
    if x >= 0:
        return math.floor(x + Fraction(1, 2))
    return -math.floor(-x + Fraction(1, 2))


def coerce_number(x) -> Fraction | None:
    if x is None or isinstance(x, bool):
        return None
    if isinstance(x, Fraction):
        return x
    if isinstance(x, int):
        return Fraction(x)
    if isinstance(x, float):
        return Fraction(str(x)) if math.isfinite(x) else None
    return parse_number(x)


@dataclass
class ProfitResult:
    input_error: bool = False
    verdict: str = ""               # 통과/보류/탈락 (입력 오류면 "")
    reasons: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    t_min: int | None = None
    t_sug: int | None = None
    p: int | None = None
    profit: int | None = None
    margin: float | None = None
    stress_profit: int | None = None
    a_star: float | None = None
    shortfall: int | None = None
    label: str = LABEL
    tax_note: str = TAX_NOTE
    # 판정에 쓴 정확값(보고에는 쓰지 않음)
    profit_exact: Fraction | None = None
    stress_exact: Fraction | None = None


def compute_profit(cost, ship, market, cfg: Config, customer_ship=None) -> ProfitResult:
    C, S, M = coerce_number(cost), coerce_number(ship), coerce_number(market)
    errs = []
    for name, val in (("C(도매 원가)", C), ("S(도매 배송비)", S), ("M(시장 기준가)", M)):
        if val is None or val < 0:
            errs.append(Reason("INPUT_ERROR", f"입력 오류: {name} 결측·음수·비숫자"))
    F = S if customer_ship in (None, "") else coerce_number(customer_ship)
    if customer_ship not in (None, "") and (F is None or F < 0):
        errs.append(Reason("INPUT_ERROR", "입력 오류: F(고객 부담 배송비) 음수·비숫자"))
    if errs:
        return ProfitResult(input_error=True, reasons=errs)

    v, v_st, m_min = cfg.v, cfg.v_stress, cfg.margin_min
    denom = 1 - v - m_min
    if denom <= 0:
        raise ValueError("config 오류: 1-v-margin_min <= 0")

    t_sug = math.floor(M * (1 - cfg.discount))
    if t_sug <= 0:
        return ProfitResult(input_error=True, t_sug=0,
                            reasons=[Reason("INPUT_ERROR", "입력 오류: T=0 (시장 기준가 0)")])
    T = Fraction(t_sug)

    t_min = math.ceil(max((C + S) / denom, (C + S + cfg.profit_min_won) / (1 - v)))
    P = t_sug - F
    profit = T - C - S - T * v
    stress = T - C - S - T * v_st
    a_star = 1 - (cfg.fee_sales_pct + cfg.fee_payment_pct) / 100 - cfg.return_rate_pct / 100 - (C + S) / T

    reasons: list[Reason] = []
    shortfall = None
    if P <= 0:
        reasons.append(Reason("P_NONPOS", REASON_LABELS["P_NONPOS"]))
    if t_sug < t_min:
        shortfall = t_min - t_sug
        reasons.append(Reason("BELOW_TMIN", f"{REASON_LABELS['BELOW_TMIN']} (부족액 {shortfall}원)"))
    elif stress < 0:
        reasons.append(Reason("STRESS_NEG", REASON_LABELS["STRESS_NEG"]))

    if any(r.code in ("P_NONPOS", "BELOW_TMIN") for r in reasons):
        verdict = "탈락"
    elif reasons:
        verdict = "보류"
    else:
        verdict = "통과"

    warnings = []
    if verdict in ("통과", "보류") and P < F:
        warnings.append("배송비 비중 과다")

    return ProfitResult(
        verdict=verdict, reasons=reasons, warnings=warnings,
        t_min=t_min, t_sug=t_sug, p=round_half_up(P),
        profit=round_half_up(profit), margin=float(profit / T),
        stress_profit=round_half_up(stress), a_star=float(a_star),
        shortfall=shortfall, profit_exact=profit, stress_exact=stress,
    )
