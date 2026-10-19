"""CSV 읽기. 첫 줄이 '#'로 시작하는 주석(예: '# 가상 데이터')은 건너뛴다."""
import csv
import io
from fractions import Fraction


def read_csv(path: str) -> list[dict]:
    with open(path, encoding="utf-8-sig", newline="") as f:
        lines = [ln for ln in f.read().splitlines() if not ln.lstrip().startswith("#")]
    reader = csv.DictReader(io.StringIO("\n".join(lines)))
    return [{(k or "").strip(): (v or "").strip() for k, v in row.items()} for row in reader]


def parse_number(text) -> Fraction | None:
    """숫자가 아니거나 비어 있으면 None. 0으로 채우지 않는다."""
    if text is None:
        return None
    s = str(text).strip()
    if not s:
        return None
    try:
        val = Fraction(s)
    except (ValueError, ZeroDivisionError):
        return None
    return val
