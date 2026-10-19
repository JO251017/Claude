"""C1 시장 기준가: 키워드별 총지불액(price+shipping) 하위 K개 평균."""
from dataclasses import dataclass, field
from datetime import date
from fractions import Fraction

from src.common.csvio import parse_number


def parse_date(text) -> date | None:
    try:
        return date.fromisoformat(str(text).strip())
    except (ValueError, TypeError):
        return None


@dataclass
class MarketInfo:
    keyword: str
    price: Fraction                 # M
    seller_count: int               # 고유 seller 수(해당 키워드 전체 유효 행)
    sample_count: int               # M 계산에 쓴 표본 수
    warnings: list = field(default_factory=list)
    oldest_researched_at: date | None = None
    missing_date: bool = False
    skipped_rows: int = 0


def compute_markets(rows: list[dict], k: int) -> dict[str, MarketInfo]:
    by_kw: dict[str, list] = {}
    skipped: dict[str, int] = {}
    for r in rows:
        kw = r.get("keyword", "")
        if not kw:
            continue
        price, ship = parse_number(r.get("price")), parse_number(r.get("shipping"))
        if price is None or ship is None or price < 0 or ship < 0:
            skipped[kw] = skipped.get(kw, 0) + 1
            continue
        by_kw.setdefault(kw, []).append((price + ship, r.get("seller", ""), parse_date(r.get("researched_at"))))

    out: dict[str, MarketInfo] = {}
    for kw, items in by_kw.items():
        used = sorted(items, key=lambda t: t[0])[:k]
        warnings = []
        if len(used) < k:
            warnings.append(f"표본 부족({len(used)}개)")
        dates = [d for _, _, d in used if d is not None]
        missing = len(dates) < len(used)
        if missing:
            warnings.append("확인 필요: researched_at 없음")
        out[kw] = MarketInfo(
            keyword=kw, price=sum(t[0] for t in used) / len(used),
            seller_count=len({s for _, s, _ in items}), sample_count=len(used),
            warnings=warnings, oldest_researched_at=min(dates) if dates else None,
            missing_date=missing, skipped_rows=skipped.get(kw, 0),
        )
    return out
