"""공통 서비스 계층: CLI·MCP·GPT 어댑터가 함께 쓰는 JSON 입출력 함수.
코어(profit, pipeline)는 수정하지 않고 호출만 한다.
DEC-008: 네이버 파생값(성장률·플래그·조회 상태)은 AI 응답에서 제외한다."""
import json
import os
import sqlite3

from src.common.config import load_config
from src.sourcing.profit import compute_profit

NAVER_EXCLUDED_NOTE = "DEC-008: 네이버 파생값(성장률·플래그·조회 상태)은 응답에서 제외됨. 판정은 이를 반영한 결과임."
HIDDEN_REASON = "비공개 사유(네이버 파생값)"
_NAVER_REASON_PREFIX = "성장률"
_NAVER_WARNING_PREFIX = "플래그"


def _config_path(config_path: str | None) -> str:
    return config_path or os.environ.get("PROFIT_CONFIG", "config.yaml")


def evaluate_candidate(cost, ship, market, customer_ship=None, config_path: str | None = None) -> dict:
    """단일 후보 수익성 평가. 네이버 데이터를 쓰지 않는다."""
    cfg = load_config(_config_path(config_path))
    r = compute_profit(cost, ship, market, cfg, customer_ship=customer_ship)
    return {
        "input_error": r.input_error,
        "verdict": r.verdict or "입력 오류",
        "reasons": [{"code": x.code, "text": x.text} for x in r.reasons],
        "warnings": list(r.warnings),
        "t_min": r.t_min, "t_sug": r.t_sug, "p": r.p,
        "profit": r.profit, "margin": r.margin, "stress_profit": r.stress_profit,
        "a_star": r.a_star, "shortfall": r.shortfall,
        "label": r.label, "tax_note": r.tax_note,
        "config_hash": cfg.config_hash,
    }


def _strip_naver(reasons: list[str], warnings: list[str]) -> tuple[list[str], list[str]]:
    kept = [x for x in reasons if not x.startswith(_NAVER_REASON_PREFIX)]
    if len(kept) < len(reasons):
        kept.append(HIDDEN_REASON)
    return kept, [w for w in warnings if not w.startswith(_NAVER_WARNING_PREFIX)]


def get_run_summary(run_id: str, config_path: str | None = None) -> dict:
    """실행 요약 + 통과·보류 후보 목록. 네이버 파생값은 제외."""
    cfg = load_config(_config_path(config_path))
    if not os.path.exists(cfg.db_path):
        raise ValueError("DB 없음: 먼저 run을 실행하세요")
    conn = sqlite3.connect(cfg.db_path)
    conn.row_factory = sqlite3.Row
    try:
        run = conn.execute("SELECT run_id, status, as_of, summary_line, config_hash FROM runs WHERE run_id=?",
                           (run_id,)).fetchone()
        if run is None:
            raise ValueError(f"알 수 없는 run_id: {run_id}")
        rows = conn.execute(
            "SELECT keyword, supplier, market_price, cost, ship, profit, margin, stress_profit, a_star, verdict, "
            "reasons, warnings FROM results WHERE run_id=? ORDER BY id", (run_id,)).fetchall()
    finally:
        conn.close()

    counts = {"통과": 0, "보류": 0, "탈락": 0, "입력 오류": 0}
    candidates = []
    for r in rows:
        counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1
        if r["verdict"] not in ("통과", "보류"):
            continue
        reasons, warnings = _strip_naver(json.loads(r["reasons"] or "[]"), json.loads(r["warnings"] or "[]"))
        candidates.append({
            "keyword": r["keyword"], "supplier": r["supplier"], "verdict": r["verdict"],
            "market_price": r["market_price"], "cost": r["cost"], "ship": r["ship"],
            "profit": r["profit"], "margin": r["margin"], "stress_profit": r["stress_profit"],
            "a_star": r["a_star"], "reasons": reasons, "warnings": warnings,
        })
    return {
        "run_id": run["run_id"], "status": run["status"], "as_of": run["as_of"],
        "conclusion": run["summary_line"], "config_hash": run["config_hash"],
        "counts": {"input": len(rows), **counts},
        "candidates": candidates,
        "note": NAVER_EXCLUDED_NOTE,
    }
