"""키워드 x 도매처 단위 순이익 후보 계산 파이프라인 (순수 계산 + 트렌드 소스 호출)."""
import json
from dataclasses import dataclass, field
from datetime import date
from fractions import Fraction

from src.common.config import Config
from src.common.logging_setup import get_logger
from src.discovery.market import MarketInfo, compute_markets, parse_date
from src.discovery.trends import GrowthResult, TrendFetchError, TrendSource, compute_growth
from src.sourcing.profit import (LABEL, REASON_LABELS, VERDICT_RANK, ProfitResult, Reason, coerce_number,
                                 compute_profit)

# AI 노출 준비도 점검 항목: (costs.csv 칸, 표시명)
AI_CHECKS = (("spec_info", "스펙 정보"), ("model_name", "모델명·브랜드"),
             ("dispatch_days", "출고 소요일"), ("differentiator", "차별점"))
_YES = {"y", "yes", "o", "예", "있음"}
NO_COST_TEXT = "원가 미입력"
NO_MARKET_TEXT = "시세 미입력"
INPUT_ERROR = "입력 오류"


@dataclass
class ResultRow:
    keyword: str
    supplier: str
    row_key: str
    product_name: str = ""
    market: MarketInfo | None = None
    growth: GrowthResult | None = None
    trend_source: str = ""
    trend_fetched_at: str = ""
    cost: Fraction | None = None
    ship: Fraction | None = None
    profit: ProfitResult | None = None
    verdict: str = ""                                  # 통과/보류/탈락/입력 오류
    reasons: list = field(default_factory=list)        # list[Reason]
    warnings: list = field(default_factory=list)
    profit_text: str = ""                              # 순이익 대신 보일 문구(원가/시세 미입력)
    ai_missing: list | None = None                     # AI 노출 정보 중 빠진 항목(None=원가 행 없음)

    @property
    def growth_display(self):
        g = self.growth
        if g is None:
            return "조회 실패"
        return g.g_raw if g.status == "확인" else ("조회 실패" if g.status == "조회 실패" else "미확인")


@dataclass
class PipelineOutput:
    rows: list
    lookup_failures: dict          # keyword -> kind
    keywords: list


def _worse(a: str, b: str) -> str:
    return a if VERDICT_RANK[a] >= VERDICT_RANK[b] else b


def ai_missing_items(cr: dict) -> list[str]:
    """도매 행에서 AI 추천 근거가 될 정보 중 빠진 항목."""
    out = []
    for col, label in AI_CHECKS:
        v = (cr.get(col) or "").strip()
        if col == "spec_info":
            ok = v.lower() in _YES
        elif col == "dispatch_days":
            n = coerce_number(v)
            ok = n is not None and n >= 0
        else:
            ok = bool(v)
        if not ok:
            out.append(label)
    return out


def _age_days(d: date | None, as_of: date) -> int | None:
    return None if d is None else (as_of - d).days


def run_pipeline(cfg: Config, keywords: list[str], competitor_rows: list[dict], cost_rows: list[dict],
                 source: TrendSource, as_of: date, fetched_at: str) -> PipelineOutput:
    log = get_logger()
    markets = compute_markets(competitor_rows, cfg.market_lowest_k)
    costs_by_kw: dict[str, list] = {}
    for r in cost_rows:
        costs_by_kw.setdefault(r.get("keyword", ""), []).append(r)

    rows: list[ResultRow] = []
    failures: dict[str, str] = {}
    for kw in keywords:
        # --- 성장률 (키워드당 1회) ---
        try:
            growth = compute_growth(source.fetch(kw), cfg)
        except TrendFetchError as e:
            growth = GrowthResult("조회 실패", detail=str(e), error_kind=e.kind)
        except NotImplementedError:
            raise
        except Exception as e:  # 예외 종류만 기록(응답 원문 금지)
            growth = GrowthResult("조회 실패", detail=type(e).__name__, error_kind="other")
        if growth.status == "조회 실패":
            failures[kw] = growth.error_kind or "other"
            log.warning("조회 실패 keyword=%s kind=%s", kw, growth.error_kind or "other")

        market = markets.get(kw)
        cost_list = costs_by_kw.get(kw) or [None]
        seen_suppliers = set()
        for cr in cost_list:
            rows.append(_build_row(cfg, kw, cr, market, growth, source.name, fetched_at, as_of, seen_suppliers))
    return PipelineOutput(rows=rows, lookup_failures=failures, keywords=list(keywords))


def _build_row(cfg, kw, cr, market, growth, source_name, fetched_at, as_of, seen) -> ResultRow:
    supplier = (cr.get("supplier") or "(미지정)") if cr else "-"
    row = ResultRow(keyword=kw, supplier=supplier, row_key=f"{kw}|{supplier}", market=market, growth=growth,
                    trend_source=source_name, trend_fetched_at=fetched_at,
                    product_name=(cr.get("product_name", "") if cr else ""))
    reasons: list[Reason] = []
    warnings: list[str] = []
    verdict = "통과"

    if cr is not None:
        if supplier in seen:
            row.row_key += "#dup"
            row.verdict = INPUT_ERROR
            row.reasons = [Reason("INPUT_ERROR", "입력 오류: 같은 키워드·도매처 중복 행")]
            return row
        seen.add(supplier)

    # --- 입력 검증 ---
    C = S = None
    if cr is not None:
        C, S = coerce_number(cr.get("cost")), coerce_number(cr.get("shipping"))
        row.cost, row.ship = C, S
        if C is None or C < 0 or S is None or S < 0:
            row.verdict = INPUT_ERROR
            row.reasons = [Reason("INPUT_ERROR", "입력 오류: C(도매 원가)/S(도매 배송비) 결측·음수·비숫자")]
            return row

    # --- 수익성 ---
    if market is None:
        verdict = _worse(verdict, "보류")
        reasons.append(Reason("NO_MARKET", NO_MARKET_TEXT))
        row.profit_text = NO_MARKET_TEXT
        if cr is None:
            reasons.append(Reason("NO_COST", NO_COST_TEXT))
    else:
        warnings += market.warnings
        if cr is None:
            verdict = _worse(verdict, "보류")
            reasons.append(Reason("NO_COST", NO_COST_TEXT))
            row.profit_text = NO_COST_TEXT
        else:
            pr = compute_profit(C, S, market.price, cfg)
            row.profit = pr
            if pr.input_error:
                row.verdict = INPUT_ERROR
                row.reasons = list(pr.reasons)
                return row
            verdict = _worse(verdict, pr.verdict)
            reasons += pr.reasons
            warnings += pr.warnings

    # --- 도매 입력 규칙 ---
    wholesale_date = None
    if cr is not None:
        rule = (cr.get("ship_fee_rule") or "").strip()
        if not rule:
            warnings.append("ship_fee_rule 확인 필요")
        elif rule == "수량당":
            warnings.append("다수량 주문 시 손해 가능")
        wholesale_date = parse_date(cr.get("wholesale_date"))
        if wholesale_date is None:
            warnings.append("확인 필요: wholesale_date 없음")

    # --- AI 노출 준비도 ---
    if cr is not None:
        row.ai_missing = ai_missing_items(cr)
        if row.ai_missing and cfg.ai_affects_verdict:
            verdict = _worse(verdict, "보류")
            reasons.append(Reason("AI_INFO_MISSING", f"{REASON_LABELS['AI_INFO_MISSING']} ({', '.join(row.ai_missing)})"))

    # --- 최신성 ---
    stale = []
    if market is not None:
        age = _age_days(market.oldest_researched_at, as_of)
        if age is not None and age > cfg.researched_at_days:
            stale.append(f"researched_at {age}일")
    age = _age_days(wholesale_date, as_of)
    if age is not None and age > cfg.wholesale_date_days:
        stale.append(f"wholesale_date {age}일")
    if stale:
        verdict = _worse(verdict, "보류")
        reasons.append(Reason("STALE", f"{REASON_LABELS['STALE']} ({', '.join(stale)})"))

    # --- 성장률 ---
    if growth.status == "조회 실패":
        verdict = _worse(verdict, "보류")
        reasons.append(Reason("GROWTH_FAIL", REASON_LABELS["GROWTH_FAIL"]))
    elif growth.status == "미확인":
        verdict = _worse(verdict, "보류")
        reasons.append(Reason("GROWTH_UNCONFIRMED", f"{REASON_LABELS['GROWTH_UNCONFIRMED']} ({growth.detail})"))
    elif cfg.growth_floor_pct is not None and Fraction(str(growth.g_raw)) * 100 < cfg.growth_floor_pct:
        verdict = _worse(verdict, "탈락")
        reasons.append(Reason("GROWTH_FLOOR", REASON_LABELS["GROWTH_FLOOR"]))
    for f in growth.flags:
        warnings.append(f"플래그(표시만): {f}")

    row.verdict, row.reasons, row.warnings = verdict, reasons, warnings
    return row


def sort_key(row: ResultRow):
    g = row.growth
    growth_k = (0, -g.g_raw) if g and g.status == "확인" else (1, 0)
    pe = row.profit.profit_exact if row.profit else None
    profit_k = (0, -pe) if pe is not None else (1, 0)
    return (VERDICT_RANK.get(row.verdict, 9), growth_k, profit_k)


def split_rows(rows: list[ResultRow]):
    cands = sorted([r for r in rows if r.verdict in ("통과", "보류")], key=sort_key)
    rejects = [r for r in rows if r.verdict in ("탈락", INPUT_ERROR)]
    rejects.sort(key=lambda r: (r.verdict == INPUT_ERROR,
                                r.profit.shortfall if (r.profit and r.profit.shortfall is not None) else 10**12,
                                r.keyword))
    return cands, rejects


def reasons_json(row: ResultRow) -> str:
    return json.dumps([r.text for r in row.reasons], ensure_ascii=False)
