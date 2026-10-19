import logging
import os

import pytest

from src.common.config import ConfigError, check_required_env, load_config
from src.common.db import init_db
from src.common.logging_setup import setup_logging
from src.common.notify import ConsoleNotifier, EmailNotifier, FileNotifier, KakaoTalkNotifier

CFG = os.path.join(os.path.dirname(__file__), "..", "config.yaml")


def test_config_loads_and_v():
    c = load_config(CFG)
    assert float(c.v) == pytest.approx(0.1463)
    assert c.growth_floor_pct is None


def test_missing_key_reports_names_only(tmp_path):
    p = tmp_path / "c.yaml"
    p.write_text("fee_sales_pct: abc\n", encoding="utf-8")
    with pytest.raises(ConfigError) as e:
        load_config(str(p))
    assert "fee_sales_pct" in e.value.keys and "fee_payment_pct" in e.value.keys
    assert "abc" not in str(e.value)


def test_fee_on_shipping_other_value_is_error(tmp_path):
    text = open(CFG, encoding="utf-8").read().replace("fee_on_shipping: all", "fee_on_shipping: item_only")
    p = tmp_path / "c.yaml"
    p.write_text(text, encoding="utf-8")
    with pytest.raises(ConfigError) as e:
        load_config(str(p))
    assert e.value.keys == ["fee_on_shipping"]


def test_margin_makes_denominator_nonpositive(tmp_path):
    text = open(CFG, encoding="utf-8").read().replace("margin_min_pct: 15", "margin_min_pct: 90")
    p = tmp_path / "c.yaml"
    p.write_text(text, encoding="utf-8")
    with pytest.raises(ConfigError):
        load_config(str(p))


def test_required_env_names_only(monkeypatch):
    monkeypatch.delenv("X_TEST_KEY", raising=False)
    with pytest.raises(ConfigError) as e:
        check_required_env(["X_TEST_KEY"])
    assert e.value.keys == ["X_TEST_KEY"]


def test_logging_has_run_id_and_redacts(tmp_path):
    lg = setup_logging("RUN-1", str(tmp_path))
    lg.info("calling api_key=SUPERSECRET123 ok")
    for h in lg.handlers:
        h.flush()
    text = open(tmp_path / "run_RUN-1.log", encoding="utf-8").read()
    assert "RUN-1" in text and "SUPERSECRET123" not in text


def test_db_tables_and_view(tmp_path):
    conn = init_db(str(tmp_path / "t.db"))
    names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master")}
    assert {"runs", "results", "approval_events", "approved_candidates"} <= names


def test_notifiers(tmp_path, capsys):
    ConsoleNotifier().notify("hello", run_id="R")
    assert "[R]" in capsys.readouterr().out
    FileNotifier(str(tmp_path / "n.log")).notify("x token=ABC", level="error", run_id="R")
    assert "ABC" not in (tmp_path / "n.log").read_text(encoding="utf-8")
    with pytest.raises(NotImplementedError):
        KakaoTalkNotifier().notify("a")
    with pytest.raises(NotImplementedError):
        EmailNotifier().notify("a")
