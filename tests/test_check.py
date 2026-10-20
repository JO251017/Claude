import json
import os
import urllib.error

from src.check import run_check
from src import cli
from src.common.config import load_config

ROOT = os.path.join(os.path.dirname(__file__), "..")
CFG = load_config(os.path.join(ROOT, "config.yaml"))
ENV = {"NAVER_CLIENT_ID": "ID-XYZ", "NAVER_CLIENT_SECRET": "SECRET-XYZ", "NAVER_AD_API_KEY": "AK-XYZ",
       "NAVER_AD_SECRET_KEY": "SK-XYZ", "NAVER_AD_CUSTOMER_ID": "123"}


class Resp:
    def __init__(self, p): self.p = p
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def read(self): return json.dumps(self.p).encode()


def good(req, timeout):
    if "datalab" in req.full_url:
        return Resp({"results": [{"data": [{"period": f"{y}-{m:02d}-01", "ratio": 50} for y in (2024, 2025, 2026) for m in range(1, 13)]}]})
    if "shop" in req.full_url:
        return Resp({"total": 5})
    return Resp({"keywordList": []})


def test_all_ok(monkeypatch):
    for k, v in ENV.items():
        monkeypatch.setenv(k, v)
    assert all(l.ok for l in run_check(CFG, urlopen=good))


def test_missing_env_names_only(monkeypatch):
    for k in ENV:
        monkeypatch.delenv(k, raising=False)
    out = run_check(CFG, urlopen=good)
    assert not any(l.ok for l in out)
    assert "NAVER_AD_API_KEY" in out[2].detail


def test_401_and_no_secret_leak(monkeypatch, capsys):
    for k, v in ENV.items():
        monkeypatch.setenv(k, v)

    def bad(req, timeout):
        raise urllib.error.HTTPError(req.full_url, 401, "x", {}, None)

    out = run_check(CFG, urlopen=bad)
    assert all(not l.ok and "키 값" in l.detail for l in out)
    text = " ".join(l.detail for l in out)
    assert not any(v in text for v in ENV.values())


def test_format_hints_flag_swaps_without_values(monkeypatch):
    from src.check import format_hints
    monkeypatch.setenv("NAVER_CLIENT_ID", "short")
    monkeypatch.setenv("NAVER_CLIENT_SECRET", "a-much-longer-value")
    monkeypatch.setenv("NAVER_AD_API_KEY", "AQAAAAxxxx")
    monkeypatch.setenv("NAVER_AD_SECRET_KEY", "0100xxxx ")
    monkeypatch.setenv("NAVER_AD_CUSTOMER_ID", "12a")
    text = " | ".join(format_hints(CFG))
    assert "바뀌었을" in text and "공백" in text and "숫자" in text
    assert "a-much-longer-value" not in text and "AQAAAAxxxx" not in text


def test_api_error_code_shown_without_keys(monkeypatch):
    import io
    for k, v in ENV.items():
        monkeypatch.setenv(k, v)

    def bad(req, timeout):
        raise urllib.error.HTTPError(req.full_url, 401, "x", {}, io.BytesIO(
            json.dumps({"errorCode": "024", "errorMessage": "Authentication failed"}).encode()))

    out = run_check(CFG, urlopen=bad)
    assert "024" in out[0].detail and "Authentication failed" in out[0].detail
    assert not any(v in l.detail for l in out for v in ENV.values())
