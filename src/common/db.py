"""SQLite 초기화: runs, results, approval_events + approved_candidates 뷰.
ratio 시계열은 저장하지 않는다(DEC-008): 파생값만 저장."""
import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL,
    config_hash TEXT,
    source_name TEXT,
    as_of TEXT,
    summary_line TEXT,
    xlsx_path TEXT
);
CREATE TABLE IF NOT EXISTS results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL REFERENCES runs(run_id),
    row_key TEXT NOT NULL,
    keyword TEXT NOT NULL,
    supplier TEXT,
    product_name TEXT,
    market_price REAL,
    seller_count INTEGER,
    sample_count INTEGER,
    growth_rate REAL,
    growth_status TEXT,
    growth_flags TEXT,
    trend_source TEXT,
    trend_fetched_at TEXT,
    cost REAL,
    ship REAL,
    customer_ship REAL,
    t_min INTEGER,
    t_sug INTEGER,
    p INTEGER,
    profit INTEGER,
    margin REAL,
    stress_profit INTEGER,
    a_star REAL,
    verdict TEXT NOT NULL,
    reasons TEXT,
    warnings TEXT,
    label TEXT,
    UNIQUE (run_id, row_key)
);
CREATE TABLE IF NOT EXISTS approval_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    scope TEXT NOT NULL,
    decision TEXT NOT NULL,
    memo TEXT,
    event_at TEXT NOT NULL,
    source_hash TEXT NOT NULL,
    UNIQUE (run_id, scope, source_hash)
);
DROP VIEW IF EXISTS approved_candidates;
CREATE VIEW approved_candidates AS
SELECT r.run_id, r.row_key, r.keyword, r.supplier, r.product_name,
       r.market_price, r.cost, r.ship, r.t_sug, r.profit, r.margin,
       r.stress_profit, r.a_star, r.verdict, ie.memo AS item_memo, ie.event_at AS approved_at
FROM results r
JOIN approval_events ie ON ie.id = (
        SELECT MAX(id) FROM approval_events
        WHERE run_id = r.run_id AND scope = 'item:' || r.row_key)
JOIN approval_events re ON re.id = (
        SELECT MAX(id) FROM approval_events
        WHERE run_id = r.run_id AND scope = 'run')
WHERE ie.decision = '승인' AND re.decision = '승인';
"""


def init_db(path: str) -> sqlite3.Connection:
    import os
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    conn.commit()
    return conn
