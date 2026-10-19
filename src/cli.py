"""명령줄: run / approve import. 사용: python -m src.cli run --keywords ... """
import argparse
import json
import os
import sys
import uuid
from datetime import date, datetime

from src.approval import ApprovalStructureError, import_approvals
from src.common.config import Config, ConfigError, check_required_env, load_config, load_env_file
from src.common.csvio import read_csv
from src.common.db import init_db
from src.common.logging_setup import setup_logging
from src.common.notify import ConsoleNotifier, FileNotifier, MultiNotifier, Notifier
from src.discovery.trends import (CachedTrendSource, CsvTrendSource, DatalabTrendSource, RetryingTrendSource,
                                  TrendSource)
from src.discovery.keyword_finder import SearchAdClient, ShopSearchClient, discover
from src.discovery_report import conclusion, write_discovery_xlsx, write_keywords_csv
from src.pipeline import reasons_json, run_pipeline
from src.report_xlsx import SummaryConsistencyError, build_summary, write_workbook


def new_run_id() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:4]


def default_notifier(cfg: Config) -> Notifier:
    return MultiNotifier(ConsoleNotifier(), FileNotifier(os.path.join(cfg.output_dir, "notifications.log")))


def save_results(conn, run_id, rows):
    for r in rows:
        m, pr, g = r.market, r.profit, r.growth
        conn.execute(
            "INSERT INTO results (run_id,row_key,keyword,supplier,product_name,market_price,seller_count,sample_count,"
            "growth_rate,growth_status,growth_flags,trend_source,trend_fetched_at,cost,ship,customer_ship,t_min,t_sug,p,"
            "profit,margin,stress_profit,a_star,verdict,reasons,warnings,label,ai_missing) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (run_id, r.row_key, r.keyword, r.supplier, r.product_name,
             float(m.price) if m else None, m.seller_count if m else None, m.sample_count if m else None,
             g.g_raw if g else None, g.status if g else None, ",".join(g.flags) if g else "",
             r.trend_source, r.trend_fetched_at,
             float(r.cost) if r.cost is not None else None, float(r.ship) if r.ship is not None else None,
             float(r.ship) if r.ship is not None else None,
             pr.t_min if pr else None, pr.t_sug if pr else None, pr.p if pr else None,
             pr.profit if pr else None, pr.margin if pr else None, pr.stress_profit if pr else None,
             pr.a_star if pr else None, r.verdict, reasons_json(r),
             json.dumps(r.warnings, ensure_ascii=False), pr.label if pr else None,
             json.dumps(r.ai_missing, ensure_ascii=False) if r.ai_missing is not None else None))
    conn.commit()


def execute_run(cfg: Config, keywords_path, competitors_path, costs_path, source: TrendSource,
                as_of: date, notifier: Notifier, run_id: str | None = None, config_path: str = "config.yaml") -> dict:
    run_id = run_id or new_run_id()
    log = setup_logging(run_id, cfg.log_dir)
    os.makedirs(cfg.output_dir, exist_ok=True)
    conn = init_db(cfg.db_path)
    started = datetime.now().isoformat(timespec="seconds")
    conn.execute("INSERT INTO runs (run_id, started_at, status, config_hash, source_name, as_of) VALUES (?,?,?,?,?,?)",
                 (run_id, started, "running", cfg.config_hash, source.name, as_of.isoformat()))
    conn.commit()
    log.info("run 시작 source=%s as_of=%s", source.name, as_of)
    try:
        keywords = list(dict.fromkeys(r["keyword"] for r in read_csv(keywords_path) if r.get("keyword")))
        competitors = read_csv(competitors_path)
        costs = read_csv(costs_path)
        out = run_pipeline(cfg, keywords, competitors, costs, source, as_of, started)
        facts = build_summary(out.rows, len(keywords))
        xlsx = os.path.join(cfg.output_dir, f"candidates_{run_id}.xlsx")
        write_workbook(xlsx, out.rows, facts, {"run_id": run_id, "config_hash": cfg.config_hash,
                                               "source_name": source.name, "executed_at": started,
                                               "as_of": as_of.isoformat()})
        save_results(conn, run_id, out.rows)
        conn.execute("UPDATE runs SET status='done', finished_at=?, summary_line=?, xlsx_path=? WHERE run_id=?",
                     (datetime.now().isoformat(timespec="seconds"), facts["conclusion"], xlsx, run_id))
        conn.commit()
    except Exception as e:
        conn.execute("UPDATE runs SET status='failed' WHERE run_id=?", (run_id,)); conn.commit()
        log.error("run 실패: %s", type(e).__name__ if not isinstance(e, (NotImplementedError, SummaryConsistencyError)) else e)
        if isinstance(e, (NotImplementedError, SummaryConsistencyError)):
            notifier.notify(f"오류: {e}", "error", run_id)
        raise
    finally:
        conn.close()

    fails = out.lookup_failures
    if fails and len(fails) == len(keywords):
        notifier.notify("오류: 전체 키워드 성장률 조회 실패", "error", run_id)
    elif any(k == "rate_limit" for k in fails.values()):
        notifier.notify("오류: 호출 한도 초과(429) 발생 키워드 있음 - 조회 실패로 표시됨", "error", run_id)
    log.info("run 완료 %s", facts["conclusion"])
    notifier.notify(facts["conclusion"], "info", run_id)
    return {"run_id": run_id, "xlsx": xlsx, "facts": facts, "failures": fails}


def build_source(args, cfg: Config, as_of: date) -> TrendSource:
    if args.source == "csv":
        if not args.trends:
            raise ConfigError(["--trends"])
        return CachedTrendSource(CsvTrendSource(args.trends, as_of))
    # datalab: 공식 API. 약관 확인·키 존재(이름만 확인)를 실행 전에 검사한다.
    if not cfg.datalab_terms_ack:
        raise ConfigError(["datalab.api_terms_ack"])
    load_env_file(".env")
    check_required_env(cfg.datalab_required_env)
    cid, secret = (os.environ[n] for n in cfg.datalab_required_env[:2])
    categories = {r["keyword"]: r.get("category", "") for r in read_csv(args.keywords) if r.get("keyword")}
    return CachedTrendSource(RetryingTrendSource(DatalabTrendSource(cfg, as_of, categories, cid, secret), cfg))


def execute_discover(cfg: Config, seeds_path: str, notifier: Notifier, run_id: str,
                     ad: SearchAdClient | None = None, shop: ShopSearchClient | None = None, sleep=None) -> dict:
    """모듈 0. 키는 존재 여부만 확인하고 값은 기록하지 않는다."""
    import time as _time
    log = setup_logging(run_id, cfg.log_dir)
    seeds = [{"seed": r["seed"], "category": r.get("category", "")} for r in read_csv(seeds_path) if r.get("seed")]
    seeds = list({s["seed"]: s for s in seeds}.values())
    if ad is None or shop is None:
        if not cfg.disc_terms_ack:
            raise ConfigError(["discovery.api_terms_ack"])
        load_env_file(".env")
        check_required_env(list(cfg.disc_searchad_env) + list(cfg.datalab_required_env[:2]))
        ak, sk, cid = (os.environ[n] for n in cfg.disc_searchad_env)
        ad = SearchAdClient(cfg, ak, sk, cid)
        shop = ShopSearchClient(cfg, *(os.environ[n] for n in cfg.datalab_required_env[:2]))
    log.info("discover 시작 seeds=%d", len(seeds))
    res = discover(cfg, seeds, ad, shop, sleep=sleep or _time.sleep)
    os.makedirs(cfg.output_dir, exist_ok=True)
    csv_path = os.path.join(cfg.output_dir, f"discovered_keywords_{run_id}.csv")
    xlsx_path = os.path.join(cfg.output_dir, f"discovery_{run_id}.xlsx")
    n_ok = write_keywords_csv(csv_path, res)
    write_discovery_xlsx(xlsx_path, res, {"run_id": run_id, "executed_at": datetime.now().isoformat(timespec="seconds"),
                                          "n_seeds": len(seeds)}, os.path.basename(csv_path))
    line = conclusion(res)
    log.info("discover 완료 %s", line)
    if seeds and len(res.seed_failures) == len(seeds):
        notifier.notify("오류: 모든 씨앗 키워드의 연관 키워드 조회 실패", "error", run_id)
    notifier.notify(line, "info", run_id)
    return {"xlsx": xlsx_path, "csv": csv_path, "n_ok": n_ok, "result": res}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m src.cli")
    ap.add_argument("--config", default="config.yaml")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--keywords", default="data/input/keywords.csv")
    r.add_argument("--competitors", default="data/input/competitors.csv")
    r.add_argument("--costs", default="data/input/costs.csv")
    r.add_argument("--trends", default="data/input/trends.csv")
    r.add_argument("--source", choices=["csv", "datalab"], default="csv",
                   help="csv: trends.csv 사용 / datalab: 네이버 데이터랩 API로 직접 조회(.env에 키 필요)")
    r.add_argument("--as-of", help="성장률 기준일 YYYY-MM-DD (기본 오늘)")
    d = sub.add_parser("discover", help="모듈 0: 씨앗 키워드로 연관 키워드 발굴")
    d.add_argument("--seeds", default="data/input/seeds.csv")
    a = sub.add_parser("approve")
    a.add_argument("action", choices=["import"])
    a.add_argument("xlsx")
    args = ap.parse_args(argv)

    run_id = new_run_id()
    try:
        cfg = load_config(args.config)
    except ConfigError as e:
        ConsoleNotifier().notify(str(e), "error", run_id)
        return 2
    notifier = default_notifier(cfg)

    if args.cmd == "approve":
        setup_logging(run_id, cfg.log_dir)
        conn = init_db(cfg.db_path)
        try:
            rep = import_approvals(conn, args.xlsx)
        except ApprovalStructureError as e:
            notifier.notify(f"승인 가져오기 중단: {e}", "error", run_id)
            return 3
        finally:
            conn.close()
        print(f"승인 가져오기 완료 run_id={rep.run_id} 신규 {rep.inserted}건, 중복 {rep.duplicates}건, 행 오류 {len(rep.row_errors)}건")
        for msg in rep.row_errors:
            print("  - 건너뜀:", msg)
        return 0

    if args.cmd == "discover":
        try:
            execute_discover(cfg, args.seeds, notifier, run_id)
        except ConfigError as e:
            notifier.notify(str(e), "error", run_id)
            return 2
        except FileNotFoundError as e:
            notifier.notify(f"오류: 입력 파일 없음 ({os.path.basename(str(e.filename))})", "error", run_id)
            return 2
        return 0

    try:
        as_of = date.fromisoformat(args.as_of) if args.as_of else date.today()
    except ValueError:
        notifier.notify("설정 오류 - 형식 오류 키: --as-of", "error", run_id)
        return 2
    try:
        source = build_source(args, cfg, as_of)
    except ConfigError as e:
        notifier.notify(str(e), "error", run_id)
        return 2
    except FileNotFoundError as e:
        notifier.notify(f"오류: 입력 파일 없음 ({os.path.basename(str(e.filename))})", "error", run_id)
        return 2
    try:
        execute_run(cfg, args.keywords, args.competitors, args.costs, source, as_of, notifier, run_id)
    except (NotImplementedError, SummaryConsistencyError):
        return 4
    except FileNotFoundError as e:
        notifier.notify(f"오류: 입력 파일 없음 ({os.path.basename(str(e.filename))})", "error", run_id)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
