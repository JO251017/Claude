"""연결 점검: 공식 API 3종에 각 1회만 호출해 키·권한이 맞는지 확인한다.
키 값·응답 본문은 출력하거나 기록하지 않고 '정상/실패와 원인 분류'만 돌려준다."""
import os
from dataclasses import dataclass
from datetime import date

from src.common.config import Config
from src.common.http_retry import HttpError
from src.discovery.keyword_finder import FetchError, SearchAdClient, ShopSearchClient
from src.discovery.trends import DatalabTrendSource, TrendFetchError

PROBE_KEYWORD = "원피스"
PROBE_CATEGORY = "50000000"  # 패션의류

_HINTS = {
    401: "키 값이 맞지 않습니다(복사 오류·공백·재발급 여부 확인)",
    403: "권한이 없습니다(사용 API 선택·서비스 환경·계정 상태 확인)",
    404: "주소를 찾지 못했습니다(config.yaml의 주소 확인)",
    429: "호출 한도에 걸렸습니다(잠시 뒤 다시)",
}


@dataclass
class CheckLine:
    name: str
    ok: bool
    detail: str


def _missing(names) -> list[str]:
    return [n for n in names if not os.environ.get(n)]


def _classify(e: Exception) -> str:
    if isinstance(e, HttpError):
        return _HINTS.get(e.status, f"HTTP {e.status}")
    if isinstance(e, TimeoutError):
        return "네트워크 오류 또는 타임아웃(인터넷 연결 확인)"
    if isinstance(e, (FetchError, TrendFetchError)):
        return {"malformed": "응답 형식이 예상과 다릅니다", "rate_limit": "호출 한도", "empty": "빈 응답"}.get(
            e.kind, e.kind)
    return type(e).__name__


def _probe(name: str, env: tuple, fn) -> CheckLine:
    miss = _missing(env)
    if miss:
        return CheckLine(name, False, ".env에 없음: " + ", ".join(miss))
    try:
        fn()
    except Exception as e:  # 원인 분류만 남기고 본문·키는 다루지 않는다
        return CheckLine(name, False, _classify(e))
    return CheckLine(name, True, "정상")


def run_check(cfg: Config, as_of: date | None = None, urlopen=None) -> list[CheckLine]:
    as_of = as_of or date.today()
    env_open = tuple(cfg.datalab_required_env[:2])

    def datalab():
        src = DatalabTrendSource(cfg, as_of, {PROBE_KEYWORD: PROBE_CATEGORY}, os.environ[env_open[0]],
                                 os.environ[env_open[1]], urlopen=urlopen)
        src.fetch(PROBE_KEYWORD)

    def shop():
        ShopSearchClient(cfg, os.environ[env_open[0]], os.environ[env_open[1]], urlopen=urlopen).count(PROBE_KEYWORD)

    def searchad():
        k, s, c = (os.environ[n] for n in cfg.disc_searchad_env[:3])
        SearchAdClient(cfg, k, s, c, urlopen=urlopen).related(PROBE_KEYWORD)

    return [
        _probe("데이터랩(쇼핑인사이트)", env_open, datalab),
        _probe("쇼핑 검색", env_open, shop),
        _probe("검색광고 키워드도구", tuple(cfg.disc_searchad_env[:3]), searchad),
    ]


def format_hints(cfg: Config) -> list[str]:
    """값 자체는 보이지 않고, 흔한 입력 실수(공백·자리 바뀜·길이)만 알려 준다."""
    g = os.environ.get
    out = []
    for n in list(cfg.datalab_required_env[:2]) + list(cfg.disc_searchad_env[:3]):
        v = g(n)
        if v is None:
            continue
        if v != v.strip() or " " in v or '"' in v or "'" in v:
            out.append(f"{n}: 공백이나 따옴표가 섞여 있습니다")
    cid, sec = (g(n, "") for n in cfg.datalab_required_env[:2])
    if cid and sec and len(cid) < len(sec):
        out.append("NAVER_CLIENT_ID가 SECRET보다 짧습니다. 둘이 바뀌었을 수 있습니다(ID 약 20자, SECRET 약 10자)")
    ak, sk, cu = (g(n, "") for n in cfg.disc_searchad_env[:3])
    if ak and not ak.startswith("0100"):
        out.append("NAVER_AD_API_KEY(엑세스라이선스)가 보통 '0100'으로 시작하는데 다릅니다. 비밀키와 바뀌었을 수 있습니다")
    if sk and sk.startswith("0100"):
        out.append("NAVER_AD_SECRET_KEY(비밀키)에 엑세스라이선스가 들어간 것 같습니다")
    if cu and not cu.isdigit():
        out.append("NAVER_AD_CUSTOMER_ID는 숫자만이어야 합니다")
    return out
