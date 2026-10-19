"""C2 성장률 (M1 기획서 5.4). ratio 시계열은 메모리에서만 쓰고 DB·파일·로그에 저장하지 않는다(DEC-008)."""
import calendar
import json
import time
import urllib.request
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date
from fractions import Fraction

from src.common.config import Config
from src.common.csvio import parse_number, read_csv
from src.common.http_retry import RetryExhausted, Throttle, call_with_retry, open_json

TOTAL_MONTHS = 15      # 최근 15개 완결 월
RECENT_WINDOW = 3      # 최근 3개월 vs 1년 전 같은 3개월
YEAR_OFFSET = 12


class TrendFetchError(Exception):
    """조회 실패. kind: rate_limit | server | timeout | client | empty | malformed | other"""

    def __init__(self, kind: str, detail: str = ""):
        self.kind = kind
        super().__init__(detail or kind)


def complete_months(as_of: date, n: int = TOTAL_MONTHS) -> list[str]:
    """이번 달을 제외한 최근 n개 완결 월 'YYYY-MM' (오래된→최신)."""
    y, m = as_of.year, as_of.month
    out = []
    for _ in range(n):
        m -= 1
        if m == 0:
            y, m = y - 1, 12
        out.append(f"{y:04d}-{m:02d}")
    return out[::-1]


class TrendSource(ABC):
    name = "base"

    @abstractmethod
    def fetch(self, keyword: str) -> list:
        """15개 월별 ratio(float|None, 오래된→최신)를 돌려주거나 TrendFetchError를 던진다."""


class CsvTrendSource(TrendSource):
    name = "csv"

    def __init__(self, path: str, as_of: date):
        self._months = complete_months(as_of)
        self._data: dict[str, dict[str, float]] = {}
        for r in read_csv(path):
            val = parse_number(r.get("ratio"))
            if r.get("keyword") and r.get("month") and val is not None:
                self._data.setdefault(r["keyword"], {})[r["month"]] = float(val)

    def fetch(self, keyword):
        series = self._data.get(keyword, {})
        out = [series.get(m) for m in self._months]
        if all(x is None for x in out):
            raise TrendFetchError("empty", "빈 응답")
        return out


class MockTrendSource(TrendSource):
    """테스트용. data={keyword: [15개 ratio]}, failures={keyword: TrendFetchError|Exception}."""
    name = "mock"

    def __init__(self, data=None, failures=None):
        self.data, self.failures = data or {}, failures or {}
        self.calls: list[str] = []

    def fetch(self, keyword):
        self.calls.append(keyword)
        if keyword in self.failures:
            raise self.failures[keyword]
        if keyword not in self.data or not self.data[keyword]:
            raise TrendFetchError("empty", "빈 응답")
        return list(self.data[keyword])


class DatalabTrendSource(TrendSource):
    """네이버 데이터랩 쇼핑인사이트 키워드별 트렌드 API (docs/api/naver_datalab_shopping_keywords.md).
    키워드 1개당 1회 호출한다(여러 개를 묶으면 ratio 기준인 최댓값 100이 함께 묶인 키워드에 따라 달라짐).
    응답 원문·요청 헤더는 기록하지 않고, ratio는 메모리에서만 쓴다(DEC-008).
    반드시 RetryingTrendSource로 감싸 쓴다(HTTP 오류는 HttpError/TimeoutError로 올린다)."""
    name = "datalab"

    def __init__(self, cfg: Config, as_of: date, categories: dict, client_id: str, client_secret: str, urlopen=None):
        self._cfg = cfg
        self._months = complete_months(as_of)
        y, m = map(int, self._months[-1].split("-"))
        self._start = f"{self._months[0]}-01"
        self._end = f"{self._months[-1]}-{calendar.monthrange(y, m)[1]:02d}"
        self._categories = categories
        self._auth = (client_id, client_secret)
        self._urlopen = urlopen
        self.calls = 0

    def fetch(self, keyword):
        category = (self._categories.get(keyword) or "").strip()
        if not category:
            raise TrendFetchError("no_category", "분야 코드(category) 없음")
        if self.calls >= self._cfg.datalab_daily_limit:
            raise TrendFetchError("rate_limit", "하루 호출 한도 도달")
        self.calls += 1
        body = json.dumps({"startDate": self._start, "endDate": self._end, "timeUnit": "month",
                           "category": category, "keyword": [{"name": keyword, "param": [keyword]}]}).encode()
        req = urllib.request.Request(self._cfg.datalab_endpoint, data=body, method="POST", headers={
            "X-Naver-Client-Id": self._auth[0], "X-Naver-Client-Secret": self._auth[1],
            "Content-Type": "application/json"})
        try:
            results = open_json(req, self._cfg.datalab_timeout_sec, self._urlopen)["results"]
            by_month = {d["period"][:7]: float(d["ratio"]) for r in results for d in r.get("data", [])}
        except (ValueError, KeyError, TypeError):
            raise TrendFetchError("malformed", "응답 형식 오류") from None
        out = [by_month.get(m) for m in self._months]
        if all(x is None for x in out):
            raise TrendFetchError("empty", "빈 응답")
        return out


class RetryingTrendSource(TrendSource):
    """재시도(429 Retry-After, 5xx·타임아웃)와 호출 간 최소 간격을 적용하는 래퍼."""

    def __init__(self, inner: TrendSource, cfg: Config, sleep=time.sleep, clock=time.monotonic):
        self.inner, self.cfg, self.sleep = inner, cfg, sleep
        self.name = inner.name
        self.throttle = Throttle(cfg.min_interval_sec, clock=clock, sleep=sleep)

    def fetch(self, keyword):
        c = self.cfg
        try:
            return call_with_retry(
                lambda: self.inner.fetch(keyword),
                max_429=c.retry_429_max, backoff_429=c.retry_429_backoff_sec,
                max_transient=c.retry_transient_max, backoff_transient=c.retry_transient_backoff_sec,
                throttle=self.throttle, sleep=self.sleep)
        except RetryExhausted as e:
            raise TrendFetchError(e.kind, str(e)) from None


class CachedTrendSource(TrendSource):
    """같은 실행 안에서 같은 키워드를 두 번 호출하지 않도록 메모리에서만 재사용(성공·실패 모두)."""

    def __init__(self, inner: TrendSource):
        self.inner = inner
        self.name = inner.name
        self._cache: dict[str, tuple] = {}

    def fetch(self, keyword):
        if keyword not in self._cache:
            try:
                self._cache[keyword] = ("ok", self.inner.fetch(keyword))
            except TrendFetchError as e:
                self._cache[keyword] = ("err", e)
        status, val = self._cache[keyword]
        if status == "err":
            raise val
        return val


@dataclass
class GrowthResult:
    status: str                      # 확인 | 미확인 | 조회 실패
    g_raw: float | None = None
    flags: list = field(default_factory=list)   # seasonal / spike (표시만)
    detail: str = ""
    error_kind: str = ""


def _mean(xs):
    return sum(xs) / len(xs)


def compute_growth(series, cfg: Config) -> GrowthResult:
    if not series or len(series) != TOTAL_MONTHS:
        return GrowthResult("조회 실패", detail="빈 응답 또는 형식 오류", error_kind="malformed")
    s = [None if x is None else Fraction(str(x)) for x in series]

    flags = []
    last12 = [x for x in s[TOTAL_MONTHS - YEAR_OFFSET:] if x is not None]
    if last12 and _mean(last12) > 0 and max(last12) / _mean(last12) >= cfg.seasonal_max_mean_ratio:
        flags.append("seasonal")
    prev12 = [x for x in s[TOTAL_MONTHS - YEAR_OFFSET - 1:-1] if x is not None]
    if s[-1] is not None and prev12 and _mean(prev12) > 0 and s[-1] >= cfg.spike_multiple * _mean(prev12):
        flags.append("spike")

    recent = s[-RECENT_WINDOW:]
    base = s[:RECENT_WINDOW]            # 1년 전 같은 3개월
    if any(x is None for x in recent + base):
        return GrowthResult("미확인", flags=flags, detail="필요한 6개 월 중 결측")
    base_mean = _mean(base)
    if base_mean < cfg.growth_min_base:
        return GrowthResult("미확인", flags=flags, detail="1년 전 평균이 기준 미만")
    return GrowthResult("확인", g_raw=float(_mean(recent) / base_mean - 1), flags=flags)
