"""모듈 0: 키워드 발굴.
씨앗 키워드 -> (검색광고 키워드도구) 연관 키워드·월간 검색수 -> (쇼핑 검색) 상품 수
-> 경쟁강도 = 상품 수 / 월간 검색수 (낮을수록 덜 붐빔). 가중치 점수 없이 사전식 정렬만 한다.
규격: docs/api/naver_searchad_keywordstool.md, docs/api/naver_search_shop.md"""
import base64
import hashlib
import hmac
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from fractions import Fraction

from src.common.config import Config
from src.common.http_retry import RetryExhausted, Throttle, call_with_retry, open_json
from src.common.logging_setup import get_logger

LOW_VOLUME = "<10"          # 키워드도구가 검색수 10 미만일 때 돌려주는 값(공식 명세)


class FetchError(Exception):
    def __init__(self, kind: str, detail: str = ""):
        self.kind = kind
        super().__init__(detail or kind)


def sign(timestamp: str, method: str, uri: str, secret_key: str) -> str:
    """검색광고 API 서명(공식 샘플 signaturehelper.py와 같은 방식)."""
    message = f"{timestamp}.{method}.{uri}"
    digest = hmac.new(secret_key.encode("utf-8"), message.encode("utf-8"), hashlib.sha256).digest()
    return base64.b64encode(digest).decode("ascii")


class SearchAdClient:
    URI = "/keywordstool"

    def __init__(self, cfg: Config, api_key: str, secret_key: str, customer_id: str, urlopen=None, clock=time.time):
        self._cfg, self._urlopen, self._clock = cfg, urlopen, clock
        self._auth = (api_key, secret_key, customer_id)

    def related(self, seed: str) -> list[dict]:
        api_key, secret, customer = self._auth
        ts = str(round(self._clock() * 1000))
        query = urllib.parse.urlencode({"hintKeywords": seed, "showDetail": 1})
        req = urllib.request.Request(f"{self._cfg.disc_searchad_base_url}{self.URI}?{query}", method="GET", headers={
            "X-Timestamp": ts, "X-API-KEY": api_key, "X-Customer": str(customer),
            "X-Signature": sign(ts, "GET", self.URI, secret),
            "Content-Type": "application/json; charset=UTF-8"})
        try:
            data = open_json(req, self._cfg.datalab_timeout_sec, self._urlopen)
        except ValueError:
            raise FetchError("malformed", "응답 형식 오류") from None
        items = data.get("keywordList") if isinstance(data, dict) else data
        if not isinstance(items, list):
            raise FetchError("malformed", "응답 형식 오류")
        return items


class ShopSearchClient:
    def __init__(self, cfg: Config, client_id: str, client_secret: str, urlopen=None):
        self._cfg, self._urlopen = cfg, urlopen
        self._auth = (client_id, client_secret)
        self.calls = 0

    def count(self, keyword: str) -> int:
        if self.calls >= self._cfg.disc_shop_daily_limit:
            raise FetchError("rate_limit", "쇼핑 검색 하루 호출 한도 도달")
        self.calls += 1
        query = urllib.parse.urlencode({"query": keyword, "display": 1})
        req = urllib.request.Request(f"{self._cfg.disc_shop_endpoint}?{query}", method="GET", headers={
            "X-Naver-Client-Id": self._auth[0], "X-Naver-Client-Secret": self._auth[1]})
        try:
            total = open_json(req, self._cfg.datalab_timeout_sec, self._urlopen)["total"]
            return int(total)
        except (ValueError, KeyError, TypeError):
            raise FetchError("malformed", "응답 형식 오류") from None


def _qc(v) -> tuple[int | None, bool]:
    """검색수 칸 -> (값, 10 미만 여부). '<10'은 0으로 채우지 않는다."""
    if isinstance(v, str) and v.strip() == LOW_VOLUME:
        return None, True
    try:
        return int(float(v)), False
    except (TypeError, ValueError):
        return None, False


@dataclass
class KeywordStat:
    keyword: str
    seeds: list = field(default_factory=list)
    category: str = ""
    pc: int | None = None
    mobile: int | None = None
    low_volume: bool = False
    comp_idx: str = ""
    product_count: int | None = None
    status: str = ""          # 확인 | 검색수 10 미만 | 상품 수 조회 실패 | 미조회(상한 초과) | 제외(검색수 기준 미달)

    @property
    def monthly(self) -> int | None:
        return None if self.pc is None or self.mobile is None else self.pc + self.mobile

    @property
    def competition(self) -> Fraction | None:
        if self.product_count is None or not self.monthly:
            return None
        return Fraction(self.product_count, self.monthly)


@dataclass
class DiscoveryResult:
    rows: list
    seed_failures: dict      # seed -> kind
    shop_calls: int = 0


def _retry(cfg: Config, fn, throttle: Throttle, sleep):
    return call_with_retry(fn, max_429=cfg.retry_429_max, backoff_429=cfg.retry_429_backoff_sec,
                           max_transient=cfg.retry_transient_max, backoff_transient=cfg.retry_transient_backoff_sec,
                           throttle=throttle, sleep=sleep)


def discover(cfg: Config, seeds: list[dict], ad: SearchAdClient, shop: ShopSearchClient,
             sleep=time.sleep, clock=time.monotonic) -> DiscoveryResult:
    log = get_logger()
    t_ad = Throttle(cfg.min_interval_sec, clock=clock, sleep=sleep)
    t_shop = Throttle(cfg.min_interval_sec, clock=clock, sleep=sleep)
    stats: dict[str, KeywordStat] = {}
    failures: dict[str, str] = {}

    for s in seeds:
        seed, category = s["seed"], s.get("category", "")
        try:
            items = _retry(cfg, lambda: ad.related(seed), t_ad, sleep)
        except (RetryExhausted, FetchError) as e:
            failures[seed] = getattr(e, "kind", "other")
            log.warning("연관 키워드 조회 실패 seed=%s kind=%s", seed, failures[seed])
            continue
        for it in items:
            kw = str(it.get("relKeyword") or "").strip()
            if not kw:
                continue
            st = stats.setdefault(kw, KeywordStat(keyword=kw, category=category))
            if seed not in st.seeds:
                st.seeds.append(seed)
            if st.pc is None and st.mobile is None and not st.low_volume:
                st.pc, low_pc = _qc(it.get("monthlyPcQcCnt"))
                st.mobile, low_mo = _qc(it.get("monthlyMobileQcCnt"))
                st.low_volume = low_pc or low_mo
                st.comp_idx = str(it.get("compIdx") or "")

    rows = list(stats.values())
    for st in rows:
        if st.monthly is None:
            st.status = "검색수 10 미만" if st.low_volume else "검색수 확인 불가"
        elif cfg.disc_min_monthly_search is not None and st.monthly < cfg.disc_min_monthly_search:
            st.status = "제외(검색수 기준 미달)"

    eligible = sorted([r for r in rows if not r.status], key=lambda r: -r.monthly)
    for i, st in enumerate(eligible):
        if i >= cfg.disc_max_candidates:
            st.status = "미조회(상한 초과)"
            continue
        try:
            st.product_count = _retry(cfg, lambda: shop.count(st.keyword), t_shop, sleep)
            st.status = "확인"
        except (RetryExhausted, FetchError) as e:
            st.status = "상품 수 조회 실패"
            log.warning("상품 수 조회 실패 keyword=%s kind=%s", st.keyword, getattr(e, "kind", "other"))

    rows.sort(key=lambda r: (r.status != "확인",
                             r.competition if r.competition is not None else Fraction(10 ** 12),
                             -(r.monthly or 0), r.keyword))
    return DiscoveryResult(rows=rows, seed_failures=failures, shop_calls=shop.calls)
