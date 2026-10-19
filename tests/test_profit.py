import copy
import os
from fractions import Fraction

import pytest

from src.common.config import load_config
from src.common.csvio import read_csv
from src.sourcing.profit import compute_profit

ROOT = os.path.join(os.path.dirname(__file__), "..")
CFG = load_config(os.path.join(ROOT, "config.yaml"))


def with_cfg(**kw):
    import dataclasses
    return dataclasses.replace(CFG, **{k: Fraction(str(v)) if not isinstance(v, (bool, str)) else v for k, v in kw.items()})


def test_manual_samples_match():
    rows = read_csv(os.path.join(ROOT, "tests", "fixtures", "profit_samples.csv"))
    assert len(rows) == 3
    for r in rows:
        res = compute_profit(r["cost"], r["ship"], r["market"], CFG, customer_ship=r["customer_ship"] or None)
        assert res.t_min == int(r["expected_t_min"]), r["id"]
        assert res.t_sug == int(r["expected_t_sug"])
        assert res.p == int(r["expected_p"])
        assert res.profit == int(r["expected_profit"])
        assert res.stress_profit == int(r["expected_stress_profit"])
        assert res.verdict == r["expected_verdict"]


def test_t_min_ceiling():
    # (C+S)/(1-v-m) = 14921.767.. -> 14922 (올림)
    assert compute_profit(8000, 2500, 19800, CFG).t_min == 14922


def test_t_min_exact_integer_not_bumped():
    # v=0.1, margin=0.1 -> denom 0.8, C+S=800 -> 정확히 1000: 올림이 1001이 되면 안 된다
    c = with_cfg(fee_sales_pct=4, fee_payment_pct=3, ad_rate_pct=2, return_rate_pct=1, margin_min_pct=10, profit_min_won=0)
    assert compute_profit(700, 100, 5000, c).t_min == 1000


def test_t_min_second_term_binds():
    import math
    c = with_cfg(margin_min_pct=0)  # 이익 하한 항이 지배
    r = compute_profit(1000, 0, 100000, c)
    assert r.t_min == math.ceil(Fraction(3000) / (1 - CFG.v))


def test_t_sug_floor_with_discount():
    c = with_cfg(discount_rate_pct=10)
    r = compute_profit(1000, 500, 10009, c)  # 10009*0.9 = 9008.1 -> 9008
    assert r.t_sug == 9008


def test_verdict_pass_hold_reject_priority():
    # 탈락(T_sug<T_min) 우선: 보수 순손실이어도 탈락
    r = compute_profit(15000, 3000, 21000, CFG)
    assert r.verdict == "탈락" and r.shortfall == 25581 - 21000
    assert any(x.code == "BELOW_TMIN" for x in r.reasons)


def test_p_nonpositive_rejects_and_keeps_all_reasons():
    r = compute_profit(15000, 25000, 20000, CFG, customer_ship=20000)  # P = 0
    assert r.verdict == "탈락"
    codes = {x.code for x in r.reasons}
    assert {"P_NONPOS", "BELOW_TMIN"} <= codes


def test_p_less_than_f_warning_on_pass():
    # F=14000 > P=6000: 통과이지만 배송비 비중 과다
    r = compute_profit(2000, 500, 20000, CFG, customer_ship=14000)
    assert r.verdict == "통과" and r.p == 6000
    assert "배송비 비중 과다" in r.warnings


def test_no_warning_when_rejected():
    r = compute_profit(15000, 3000, 21000, CFG)
    assert r.warnings == []


def test_stress_scenario_hold():
    c = with_cfg(margin_min_pct=5)  # 기본 15%에서는 보수 순손실이 수학적으로 불가능
    r = compute_profit(29000, 2500, 40000, c)
    assert r.t_sug >= r.t_min
    assert r.stress_profit < 0 and r.verdict == "보류"
    assert r.reasons[0].code == "STRESS_NEG"


def test_stress_never_negative_when_default_margin():
    # 기본 설정에서 T_sug >= T_min 이면 보수 순이익 >= 0.07*T 임을 경계 근처에서 확인
    for cs in range(1000, 60000, 997):
        r = compute_profit(cs, 0, 80000, CFG)
        if r.t_sug >= r.t_min:
            assert r.stress_profit > 0


def test_a_star_formula_and_breakeven():
    r = compute_profit(8000, 2500, 19800, CFG)
    expected = 1 - 0.03003 - 0.0363 - 0.03 - 10500 / 19800
    assert r.a_star == pytest.approx(expected)
    # a* == 광고율이면 순이익 0: 광고율을 a*로 바꿔 재계산
    import dataclasses
    c2 = dataclasses.replace(CFG, ad_rate_pct=Fraction(str(r.a_star * 100)))
    assert abs(float(compute_profit(8000, 2500, 19800, c2).profit_exact)) < 1e-6


@pytest.mark.parametrize("c,s,m", [(None, 1, 1), (-1, 1, 1000), ("abc", 1, 1000), (1, "", 1000), (1, 1, None), (1, 1, -5), (1, 1, "1,000")])
def test_input_errors(c, s, m):
    r = compute_profit(c, s, m, CFG)
    assert r.input_error and r.verdict == "" and r.profit is None


def test_t_zero_is_input_error():
    r = compute_profit(100, 100, 0, CFG)
    assert r.input_error


def test_cost_zero_is_allowed():
    assert not compute_profit(0, 0, 10000, CFG).input_error


def test_f_defaults_to_s():
    r1 = compute_profit(1000, 700, 20000, CFG)
    r2 = compute_profit(1000, 700, 20000, CFG, customer_ship=700)
    assert r1.p == r2.p == 19300
