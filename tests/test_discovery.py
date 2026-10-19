import os
from datetime import date

import pytest

from src.common.config import load_config
from src.common.http_retry import HttpError
from src.discovery.market import compute_markets
from src.discovery.trends import (CachedTrendSource, HubTrendSource, MockTrendSource, RetryingTrendSource,
                                  TrendFetchError, complete_months, compute_growth)

CFG = load_config(os.path.join(os.path.dirname(__file__), "..", "config.yaml"))


def rows(*items):
    return [dict(keyword="k", seller=s, price=str(p), shipping=str(sh), researched_at="2026-07-10") for s, p, sh in items]


def test_market_lowest_k_mean_and_sellers():
    m = compute_markets(rows(("a", 10000, 0), ("b", 9000, 2500), ("c", 12000, 0), ("d", 20000, 0), ("a", 30000, 0)), 3)["k"]
    # 총지불: 10000, 11500, 12000, 20000, 30000 -> 하위 3개 평균 11166.67
    assert float(m.price) == pytest.approx(33500 / 3)
    assert m.seller_count == 4 and m.sample_count == 3 and m.warnings == []


def test_market_insufficient_sample_warning():
    m = compute_markets(rows(("a", 10000, 0), ("b", 12000, 0)), 3)["k"]
    assert m.sample_count == 2 and "표본 부족(2개)" in m.warnings and float(m.price) == 11000


def test_market_skips_bad_rows():
    r = rows(("a", 10000, 0)) + [dict(keyword="k", seller="x", price="abc", shipping="0")]
    m = compute_markets(r, 3)["k"]
    assert m.sample_count == 1 and m.skipped_rows == 1


def test_complete_months_excludes_current():
    ms = complete_months(date(2026, 7, 15))
    assert len(ms) == 15 and ms[-1] == "2026-06" and ms[0] == "2025-04"
    assert complete_months(date(2026, 1, 3))[-1] == "2025-12"


def series(base3, mid, recent3):
    return list(base3) + [mid] * 9 + list(recent3)


def test_growth_formula():
    g = compute_growth(series([10, 10, 10], 12, [15, 15, 15]), CFG)
    assert g.status == "확인" and g.g_raw == pytest.approx(0.5)


def test_growth_unconfirmed_missing_or_low_base():
    s = series([10, None, 10], 12, [15, 15, 15])
    assert compute_growth(s, CFG).status == "미확인"
    assert compute_growth(series([0.2, 0.3, 0.1], 5, [5, 5, 5]), CFG).status == "미확인"


def test_growth_flags():
    s = series([10, 10, 10], 10, [10, 10, 100])
    g = compute_growth(s, CFG)
    assert "spike" in g.flags and "seasonal" in g.flags


def test_growth_malformed_is_failure():
    assert compute_growth([], CFG).status == "조회 실패"
    assert compute_growth([1, 2, 3], CFG).status == "조회 실패"


# ---- 재시도 래퍼 (sleep 패치) ----
class Flaky:
    name = "flaky"

    def __init__(self, errors):
        self.errors, self.n = list(errors), 0

    def fetch(self, kw):
        self.n += 1
        if self.errors:
            raise self.errors.pop(0)
        return [1.0] * 15


def make(errors):
    sleeps, t = [], [0.0]
    def sl(x):
        sleeps.append(x); t[0] += x
    src = RetryingTrendSource(Flaky(errors), CFG, sleep=sl, clock=lambda: t[0])
    return src, sleeps


def test_retry_429_retry_after_honored():
    src, sleeps = make([HttpError(429, retry_after=7)])
    assert len(src.fetch("k")) == 15
    assert 7 in sleeps


def test_retry_429_default_backoff_and_max3():
    src, sleeps = make([HttpError(429)] * 4)
    with pytest.raises(TrendFetchError) as e:
        src.fetch("k")
    assert e.value.kind == "rate_limit" and src.inner.n == 4
    assert [s for s in sleeps if s >= 1] == [1, 2, 4]


def test_retry_5xx_and_timeout_max2():
    src, sleeps = make([HttpError(503), TimeoutError()])
    assert len(src.fetch("k")) == 15 and src.inner.n == 3
    src2, _ = make([HttpError(500)] * 3)
    with pytest.raises(TrendFetchError) as e:
        src2.fetch("k")
    assert e.value.kind == "server" and src2.inner.n == 3


def test_no_retry_on_client_error():
    src, _ = make([HttpError(400)])
    with pytest.raises(TrendFetchError) as e:
        src.fetch("k")
    assert e.value.kind == "client" and src.inner.n == 1


def test_min_interval_between_calls():
    src, sleeps = make([])
    src.fetch("a"); src.fetch("b")
    assert any(abs(s - CFG.min_interval_sec) < 1e-9 for s in sleeps)


def test_cache_prevents_duplicate_calls():
    mock = MockTrendSource({"a": [1.0] * 15}, failures={"f": TrendFetchError("server")})
    c = CachedTrendSource(mock)
    for _ in range(3):
        c.fetch("a")
        with pytest.raises(TrendFetchError):
            c.fetch("f")
    assert mock.calls.count("a") == 1 and mock.calls.count("f") == 1


def test_hub_is_stub():
    with pytest.raises(NotImplementedError):
        HubTrendSource().fetch("x")
