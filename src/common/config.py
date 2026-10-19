"""설정 로더. 필수 키 누락·형식 오류 시 키 이름만 담아 ConfigError로 중단한다."""
import hashlib
import os
from dataclasses import dataclass
from fractions import Fraction

import yaml


class ConfigError(Exception):
    """keys에는 문제가 된 설정 키 이름만 담는다(값은 담지 않음)."""

    def __init__(self, keys):
        self.keys = list(keys)
        super().__init__("설정 오류 - 누락/형식 오류 키: " + ", ".join(self.keys))


def _frac(v) -> Fraction:
    return Fraction(str(v))


@dataclass(frozen=True)
class Config:
    fee_sales_pct: Fraction
    fee_payment_pct: Fraction
    ad_rate_pct: Fraction
    return_rate_pct: Fraction
    margin_min_pct: Fraction
    profit_min_won: Fraction
    discount_rate_pct: Fraction
    fee_on_shipping: str
    stress_ad_rate_pct: Fraction
    stress_return_rate_pct: Fraction
    stress_fee_add_pp: Fraction
    market_lowest_k: int
    growth_min_base: Fraction
    growth_floor_pct: Fraction | None
    seasonal_max_mean_ratio: Fraction
    spike_multiple: Fraction
    researched_at_days: int
    wholesale_date_days: int
    min_interval_sec: float
    retry_429_max: int
    retry_429_backoff_sec: tuple
    retry_transient_max: int
    retry_transient_backoff_sec: tuple
    hub_api_terms_ack: bool
    ai_affects_verdict: bool
    hub_required_env: tuple
    db_path: str
    output_dir: str
    log_dir: str
    config_hash: str

    @property
    def v(self) -> Fraction:
        return (self.fee_sales_pct + self.fee_payment_pct + self.ad_rate_pct + self.return_rate_pct) / 100

    @property
    def v_stress(self) -> Fraction:
        return (self.fee_sales_pct + self.fee_payment_pct + self.stress_fee_add_pp
                + self.stress_ad_rate_pct + self.stress_return_rate_pct) / 100

    @property
    def margin_min(self) -> Fraction:
        return self.margin_min_pct / 100

    @property
    def discount(self) -> Fraction:
        return self.discount_rate_pct / 100


def _num(d, path, bad, missing, nonneg=True):
    cur = d
    for p in path.split("."):
        if not isinstance(cur, dict) or p not in cur or cur[p] is None:
            missing.append(path)
            return None
        cur = cur[p]
    if isinstance(cur, bool) or not isinstance(cur, (int, float)) or (nonneg and cur < 0):
        bad.append(path)
        return None
    return _frac(cur)


def _list(d, path, bad, missing):
    cur = d
    for p in path.split("."):
        if not isinstance(cur, dict) or p not in cur:
            missing.append(path)
            return None
        cur = cur[p]
    if not isinstance(cur, list) or not cur or any(isinstance(x, bool) or not isinstance(x, (int, float)) or x < 0 for x in cur):
        bad.append(path)
        return None
    return tuple(cur)


def load_config(path: str) -> Config:
    try:
        with open(path, "rb") as f:
            raw_bytes = f.read()
        data = yaml.safe_load(raw_bytes) or {}
    except (OSError, yaml.YAMLError):
        raise ConfigError([os.path.basename(path)])
    if not isinstance(data, dict):
        raise ConfigError([os.path.basename(path)])

    bad: list[str] = []
    missing: list[str] = []
    n = lambda p, **kw: _num(data, p, bad, missing, **kw)  # noqa: E731

    fee_sales = n("fee_sales_pct"); fee_pay = n("fee_payment_pct")
    ad = n("ad_rate_pct"); ret = n("return_rate_pct")
    margin = n("margin_min_pct"); pmin = n("profit_min_won"); disc = n("discount_rate_pct")
    s_ad = n("stress.ad_rate_pct"); s_ret = n("stress.return_rate_pct"); s_fee = n("stress.fee_add_pp")
    k = n("market_lowest_k"); gmin = n("growth_min_base")
    seas = n("seasonal_max_mean_ratio"); spike = n("spike_multiple")
    d_res = n("freshness.researched_at_days"); d_wh = n("freshness.wholesale_date_days")
    interval = n("trend.min_interval_sec")
    r429 = n("trend.retry_429_max"); rtr = n("trend.retry_transient_max")
    b429 = _list(data, "trend.retry_429_backoff_sec", bad, missing)
    btr = _list(data, "trend.retry_transient_backoff_sec", bad, missing)

    fos = data.get("fee_on_shipping")
    if fos is None:
        missing.append("fee_on_shipping")
    elif fos != "all":
        bad.append("fee_on_shipping")

    floor = data.get("growth_floor_pct")
    if floor is not None and (isinstance(floor, bool) or not isinstance(floor, (int, float))):
        bad.append("growth_floor_pct")

    ai_aff = (data.get("ai_readiness") or {}).get("affects_verdict")
    if not isinstance(ai_aff, bool):
        (missing if ai_aff is None else bad).append("ai_readiness.affects_verdict")

    ack = (data.get("hub") or {}).get("api_terms_ack")
    if not isinstance(ack, bool):
        (missing if ack is None else bad).append("hub.api_terms_ack")
    req_env = (data.get("hub") or {}).get("required_env")
    if not isinstance(req_env, list) or not all(isinstance(x, str) and x for x in req_env):
        (missing if req_env is None else bad).append("hub.required_env")

    paths = data.get("paths") or {}
    for key in ("db_path", "output_dir", "log_dir"):
        if not isinstance(paths.get(key), str) or not paths.get(key):
            (missing if paths.get(key) is None else bad).append(f"paths.{key}")

    if k is not None and (k < 1 or k.denominator != 1):
        bad.append("market_lowest_k")
    if disc is not None and disc >= 100:
        bad.append("discount_rate_pct")

    if missing or bad:
        raise ConfigError(sorted(set(missing + bad), key=(missing + bad).index))

    v = (fee_sales + fee_pay + ad + ret) / 100
    if 1 - v - margin / 100 <= 0:
        raise ConfigError(["margin_min_pct(1-v-margin<=0)"])

    return Config(
        fee_sales_pct=fee_sales, fee_payment_pct=fee_pay, ad_rate_pct=ad, return_rate_pct=ret,
        margin_min_pct=margin, profit_min_won=pmin, discount_rate_pct=disc, fee_on_shipping=fos,
        stress_ad_rate_pct=s_ad, stress_return_rate_pct=s_ret, stress_fee_add_pp=s_fee,
        market_lowest_k=int(k), growth_min_base=gmin,
        growth_floor_pct=_frac(floor) if floor is not None else None,
        seasonal_max_mean_ratio=seas, spike_multiple=spike,
        researched_at_days=int(d_res), wholesale_date_days=int(d_wh),
        min_interval_sec=float(interval), retry_429_max=int(r429),
        retry_429_backoff_sec=b429, retry_transient_max=int(rtr), retry_transient_backoff_sec=btr,
        hub_api_terms_ack=ack, ai_affects_verdict=ai_aff, hub_required_env=tuple(req_env),
        db_path=paths["db_path"], output_dir=paths["output_dir"], log_dir=paths["log_dir"],
        config_hash=hashlib.sha256(raw_bytes).hexdigest(),
    )


def load_env_file(path: str) -> None:
    """.env의 KEY=VALUE를 os.environ에 주입(이미 있으면 유지). 값은 어디에도 기록·출력하지 않는다."""
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, val = line.partition("=")
            k = k.strip()
            if k and k not in os.environ and val.strip():
                os.environ[k] = val.strip().strip('"').strip("'")


def check_required_env(names) -> None:
    """존재 여부만 확인한다. 누락된 키 '이름'만 ConfigError에 담는다."""
    missing = [n for n in names if not os.environ.get(n)]
    if missing:
        raise ConfigError(missing)
