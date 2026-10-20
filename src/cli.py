"""명령줄. 기본은 관리 엑셀(관리.xlsx) 하나로 입력·결과·승인을 처리한다.
  python -m src.cli init            관리.xlsx 만들기
  python -m src.cli discover        0단계 키워드 발굴
  python -m src.cli run             1단계 순이익 후보표
  python -m src.cli approve         승인 가져오기
  python -m src.cli check           API 연결 점검(키 값은 출력 안 함)
CSV 파일 경로(--keywords 등)를 주면 예전처럼 CSV로 동작한다."""
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
from src.discovery_report import conclusion, fill_discovery_results, write_discovery_xlsx, write_keywords_csv
from src.pipeline import reasons_json, run_pipeline
from src.report_xlsx import SummaryConsistencyError, build_summary, fill_result_sheets, write_workbook
from src import workbook as wbk


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


def _rows(src) -> list[dict]:
    """CSV 경로면 읽고, 이미 읽은 행 목록이면 그대로."""
    return read_csv(src) if isinstance(src, str) else list(src)


def execute_run(cfg: Config, keywords_src, competitors_src, costs_src, source: TrendSource,
                as_of: date, notifier: Notifier, run_id: str | None = None, workbook_path: str | None = None) -> dict:
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
        keywords = list(dict.fromkeys(r["keyword"] for r in _rows(keywords_src) if r.get("keyword")))
        competitors = _rows(competitors_src)
        costs = _rows(costs_src)
        out = run_pipeline(cfg, keywords, competitors, costs, source, as_of, started)
        facts = build_summary(out.rows, len(keywords))
        meta = {"run_id": run_id, "config_hash": cfg.config_hash, "source_name": source.name,
                "executed_at": started, "as_of": as_of.isoformat()}
        if workbook_path:                       # 관리 엑셀에 먼저 써서, 열려 있으면 기록 전에 멈춘다
            wb = wbk.open_workbook(workbook_path)
            fill_result_sheets(wb, out.rows, facts, meta)
            wbk.save_workbook(wb, workbook_path)
        xlsx = os.path.join(cfg.output_dir, f"candidates_{run_id}.xlsx")
        write_workbook(xlsx, out.rows, facts, meta)
        save_results(conn, run_id, out.rows)
        conn.execute("UPDATE runs SET status='done', finished_at=?, summary_line=?, xlsx_path=? WHERE run_id=?",
                     (datetime.now().isoformat(timespec="seconds"), facts["conclusion"], xlsx, run_id))
        conn.commit()
    except Exception as e:
        conn.execute("UPDATE runs SET status='failed' WHERE run_id=?", (run_id,)); conn.commit()
        known = (NotImplementedError, SummaryConsistencyError, wbk.WorkbookLockedError)
        log.error("run 실패: %s", e if isinstance(e, known) else type(e).__name__)
        if isinstance(e, known):
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


def build_source(source_name: str, cfg: Config, as_of: date, trend_src, keyword_rows: list[dict]) -> TrendSource:
    if source_name == "csv":
        if trend_src is None:
            raise ConfigError(["--trends"])
        return CachedTrendSource(CsvTrendSource(trend_src, as_of))
    # datalab: 공식 API. 약관 확인·키 존재(이름만 확인)를 실행 전에 검사한다.
    if not cfg.datalab_terms_ack:
        raise ConfigError(["datalab.api_terms_ack"])
    load_env_file(".env")
    check_required_env(cfg.datalab_required_env)
    cid, secret = (os.environ[n] for n in cfg.datalab_required_env[:2])
    categories = {r["keyword"]: r.get("category", "") for r in keyword_rows if r.get("keyword")}
    return CachedTrendSource(RetryingTrendSource(DatalabTrendSource(cfg, as_of, categories, cid, secret), cfg))


def execute_discover(cfg: Config, seeds_src, notifier: Notifier, run_id: str,
                     ad: SearchAdClient | None = None, shop: ShopSearchClient | None = None, sleep=None,
                     workbook_path: str | None = None) -> dict:
    """모듈 0. 키는 존재 여부만 확인하고 값은 기록하지 않는다."""
    import time as _time
    log = setup_logging(run_id, cfg.log_dir)
    seeds = [{"seed": r["seed"], "category": r.get("category", "")} for r in _rows(seeds_src) if r.get("seed")]
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
    if workbook_path:
        wb = wbk.open_workbook(workbook_path)
        idx = wb.sheetnames.index(wbk.SEEDS) + 1 if wbk.SEEDS in wb.sheetnames else None
        fill_discovery_results(wb, res, idx if wbk.DISCOVERY not in wb.sheetnames else None)
        wbk.save_workbook(wb, workbook_path)
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


def _input_error(notifier, run_id, e) -> int:
    if isinstance(e, ConfigError):
        notifier.notify(str(e), "error", run_id)
    elif isinstance(e, FileNotFoundError):
        notifier.notify(f"오류: 입력 파일 없음 ({os.path.basename(str(e.filename))})", "error", run_id)
    else:
        notifier.notify(f"오류: {e}", "error", run_id)
    return 2


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m src.cli")
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--workbook", default="관리.xlsx", help="관리 엑셀 경로(기본 관리.xlsx)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    i = sub.add_parser("init", help="관리 엑셀 만들기")
    i.add_argument("--sample", action="store_true", help="가상 샘플 데이터를 채워서 만들기")
    i.add_argument("--force", action="store_true", help="이미 있으면 덮어쓰기")
    r = sub.add_parser("run", help="1단계 순이익 후보표")
    r.add_argument("--keywords"); r.add_argument("--competitors"); r.add_argument("--costs"); r.add_argument("--trends")
    r.add_argument("--source", choices=["csv", "datalab"], default="csv",
                   help="csv: 클릭추이 시트/trends.csv 사용 / datalab: 네이버 데이터랩 API로 직접 조회(.env에 키 필요)")
    r.add_argument("--as-of", help="성장률 기준일 YYYY-MM-DD (기본 오늘)")
    d = sub.add_parser("discover", help="0단계 키워드 발굴")
    d.add_argument("--seeds")
    sub.add_parser("check", help="공식 API 3종 연결 점검(각 1회 호출, 키 값은 출력 안 함)")
    a = sub.add_parser("approve", help="승인 가져오기")
    a.add_argument("action", nargs="?", choices=["import"], default="import")
    a.add_argument("xlsx", nargs="?")
    args = ap.parse_args(argv)

    run_id = new_run_id()
    try:
        cfg = load_config(args.config)
    except ConfigError as e:
        ConsoleNotifier().notify(str(e), "error", run_id)
        return 2
    notifier = default_notifier(cfg)
    has_wb = os.path.exists(args.workbook)

    if args.cmd == "init":
        if has_wb and not args.force:
            notifier.notify(f"{args.workbook}이(가) 이미 있습니다. 덮어쓰려면 --force", "error", run_id)
            return 2
        wbk.create_workbook(args.workbook, "data/sample" if args.sample else None)
        print(f"{args.workbook} 를 만들었습니다. 노란 탭에 입력한 뒤 실행하세요.")
        return 0

    if args.cmd == "check":
        from src.check import run_check
        load_env_file(".env")
        lines = run_check(cfg)
        for ln in lines:
            print(f"[{'정상' if ln.ok else '실패'}] {ln.name}: {ln.detail}")
        return 0 if all(ln.ok for ln in lines) else 2

    if args.cmd == "approve":
        path = args.xlsx or args.workbook
        setup_logging(run_id, cfg.log_dir)
        conn = init_db(cfg.db_path)
        try:
            rep = import_approvals(conn, path)
        except ApprovalStructureError as e:
            notifier.notify(f"승인 가져오기 중단: {e}", "error", run_id)
            return 3
        except FileNotFoundError:
            return _input_error(notifier, run_id, FileNotFoundError(2, "", path))
        finally:
            conn.close()
        print(f"승인 가져오기 완료 run_id={rep.run_id} 신규 {rep.inserted}건, 중복 {rep.duplicates}건, 행 오류 {len(rep.row_errors)}건")
        for msg in rep.row_errors:
            print("  - 건너뜀:", msg)
        return 0

    if args.cmd == "discover":
        use_wb = args.seeds is None and has_wb
        try:
            if use_wb:
                seeds = wbk.read_sheet(wbk.open_workbook(args.workbook), wbk.SEEDS)
                execute_discover(cfg, seeds, notifier, run_id, workbook_path=args.workbook)
            else:
                execute_discover(cfg, args.seeds or "data/input/seeds.csv", notifier, run_id)
        except (ConfigError, FileNotFoundError, wbk.WorkbookLockedError) as e:
            return _input_error(notifier, run_id, e)
        return 0

    try:
        as_of = date.fromisoformat(args.as_of) if args.as_of else date.today()
    except ValueError:
        notifier.notify("설정 오류 - 형식 오류 키: --as-of", "error", run_id)
        return 2
    use_wb = not any([args.keywords, args.competitors, args.costs, args.trends]) and has_wb
    try:
        if use_wb:
            wb = wbk.open_workbook(args.workbook)
            kw_rows = wbk.keywords_for_run(wb)
            comp, costs = wbk.read_sheet(wb, wbk.COMPETITORS), wbk.read_sheet(wb, wbk.COSTS)
            trend_src = wbk.read_sheet(wb, wbk.TRENDS)
        else:
            kw_rows = read_csv(args.keywords or "data/input/keywords.csv")
            comp = args.competitors or "data/input/competitors.csv"
            costs = args.costs or "data/input/costs.csv"
            trend_src = args.trends or "data/input/trends.csv"
        source = build_source(args.source, cfg, as_of, trend_src, kw_rows)
        execute_run(cfg, kw_rows, comp, costs, source, as_of, notifier, run_id,
                    workbook_path=args.workbook if use_wb else None)
    except (NotImplementedError, SummaryConsistencyError):
        return 4
    except wbk.WorkbookLockedError:
        return 5
    except (ConfigError, FileNotFoundError) as e:
        return _input_error(notifier, run_id, e)
    return 0


if __name__ == "__main__":
    sys.exit(main())
