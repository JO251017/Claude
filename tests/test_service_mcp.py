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
    monkeypatch.setenv("PROFIT_CONFIG", CFG)
    res = asyncio.run(server.call_tool("evaluate_candidate", {"cost": 8000, "ship": 2500, "market": 19800}))
    assert not res.is_error and res.structured_content["profit"] == 6403
    run_sample(sample_env)
    monkeypatch.setenv("PROFIT_CONFIG", sample_env["cfg_path"])
    res2 = asyncio.run(server.call_tool("get_run_summary", {"run_id": "RUN-E2E"}))
    assert res2.structured_content["run_id"] == "RUN-E2E"


def test_input_hash_normalized_and_reproducible():
    a = service.evaluate_candidate(8000, 2500, 19800, config_path=CFG)
    b = service.evaluate_candidate("8000", "2500.0", 19800.0, config_path=CFG)
    c = service.evaluate_candidate(8001, 2500, 19800, config_path=CFG)
    assert a["input_hash"] == b["input_hash"] != c["input_hash"]
    assert a["config_hash"] == b["config_hash"] and a["profit"] == b["profit"]
    assert a["schema_version"] == service.SCHEMA_VERSION


def test_reason_codes_cover_all_labels():
    from src.sourcing.profit import REASON_LABELS
    for code, label in REASON_LABELS.items():
        assert service.reason_code(label + " (상세)") == ("INPUT_ERROR" if code == "INPUT_ERROR" else code)


def test_summary_machine_fields_and_human_approval(sample_env, tmp_path):
    from src.approval import import_approvals
    from src.common.db import init_db
    from test_e2e import _edit
    cfg, res, _ = run_sample(sample_env)
    s = service.get_run_summary("RUN-E2E", sample_env["cfg_path"])
    by = {c["keyword"]: c for c in s["candidates"]}
    assert by["가상 실리콘 뚜껑"]["stale"] and "STALE" in by["가상 실리콘 뚜껑"]["reason_codes"]
    assert by["가상 방수 파우치"]["reason_codes"] == ["HIDDEN"]          # 성장률 사유는 코드도 숨김
    assert by["가상 접이식 테이블"]["reason_codes"] == ["STRESS_NEG"]
    assert s["run_decision"] is None and not any(c["human_approved"] for c in s["candidates"])
    assert service.list_approved_candidates("RUN-E2E", sample_env["cfg_path"])["items"] == []

    conn = init_db(cfg.db_path)
    import_approvals(conn, _edit(res["xlsx"], str(tmp_path / "ok.xlsx"), items={2: "O", 3: "O"}))
    s2 = service.get_run_summary("RUN-E2E", sample_env["cfg_path"])
    assert s2["run_decision"] == "승인" and sum(c["human_approved"] for c in s2["candidates"]) == 2
    appr = service.list_approved_candidates("RUN-E2E", sample_env["cfg_path"])
    view = conn.execute("SELECT keyword FROM approved_candidates WHERE run_id='RUN-E2E'").fetchall()
    assert len(appr["items"]) == len(view) == 2 and appr["approved_by"] == "human"
    assert "growth" not in json.dumps(appr)


def test_mcp_has_only_read_only_tools():
    from src.mcp_server import server
    tools = asyncio.run(server.list_tools())
    assert {t.name for t in tools} == {"evaluate_candidate", "get_run_summary", "list_approved_candidates"}
    assert all(t.annotations.read_only_hint and not t.annotations.destructive_hint for t in tools)
