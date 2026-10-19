import asyncio
import json
import os
import sqlite3

import pytest

from conftest import ROOT
from src import service
from src.common.csvio import read_csv
from test_e2e import run_sample

CFG = os.path.join(ROOT, "config.yaml")


def test_evaluate_matches_manual_samples():
    for r in read_csv(os.path.join(ROOT, "tests", "fixtures", "profit_samples.csv")):
        out = service.evaluate_candidate(r["cost"], r["ship"], r["market"], r["customer_ship"] or None, CFG)
        assert out["profit"] == int(r["expected_profit"]) and out["verdict"] == r["expected_verdict"]
        json.dumps(out, ensure_ascii=False)                 # JSON 직렬화 가능


def test_evaluate_input_error():
    out = service.evaluate_candidate("abc", 1, 1000, config_path=CFG)
    assert out["input_error"] and out["verdict"] == "입력 오류" and out["profit"] is None


def test_run_summary_matches_cli_and_hides_naver(sample_env):
    cfg, res, _ = run_sample(sample_env)
    s = service.get_run_summary("RUN-E2E", sample_env["cfg_path"])
    f = res["facts"]
    assert s["conclusion"] == f["conclusion"]
    assert (s["counts"]["통과"], s["counts"]["보류"], s["counts"]["탈락"], s["counts"]["입력 오류"]) == \
           (f["pass"], f["hold"], f["reject"], f["input_error"])
    assert len(s["candidates"]) == f["n_cands"]
    dump = json.dumps({k: v for k, v in s.items() if k != "note"}, ensure_ascii=False)
    assert "성장률" not in dump and "플래그" not in dump
    conn = sqlite3.connect(cfg.db_path)
    growths = [g for (g,) in conn.execute("SELECT growth_rate FROM results WHERE growth_rate IS NOT NULL")]
    assert growths and all(repr(g) not in dump for g in growths)
    hidden = [c for c in s["candidates"] if service.HIDDEN_REASON in c["reasons"]]
    assert hidden                                          # 성장률 사유로 보류된 후보는 비공개 사유로 표시


def test_run_summary_unknown_run(sample_env):
    run_sample(sample_env)
    with pytest.raises(ValueError):
        service.get_run_summary("NOPE", sample_env["cfg_path"])


def test_mcp_server_tools(sample_env, monkeypatch):
    from src.mcp_server import server
    tools = asyncio.run(server.list_tools())
    assert {t.name for t in tools} == {"evaluate_candidate", "get_run_summary"}
    assert all(t.annotations.read_only_hint for t in tools)
    monkeypatch.setenv("PROFIT_CONFIG", CFG)
    res = asyncio.run(server.call_tool("evaluate_candidate", {"cost": 8000, "ship": 2500, "market": 19800}))
    assert not res.is_error and res.structured_content["profit"] == 6403
    run_sample(sample_env)
    monkeypatch.setenv("PROFIT_CONFIG", sample_env["cfg_path"])
    res2 = asyncio.run(server.call_tool("get_run_summary", {"run_id": "RUN-E2E"}))
    assert res2.structured_content["run_id"] == "RUN-E2E"
