import logging
import math
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

KMA_BASE_URL = "https://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getUltraSrtNcst"

# 기상청 격자(nx, ny) ↔ 위경도 변환 상수(LCC DFS 2.0, 기상청 공식 변환식 그대로) —
# 좌표를 지어내는 게 아니라 API가 요구하는 좌표계로 그대로 옮기는 수학 변환일 뿐이다.
_RE = 6371.00877
_GRID = 5.0
_SLAT1 = 30.0
_SLAT2 = 60.0
_OLON = 126.0
_OLAT = 38.0
_XO = 43
_YO = 136
_DEGRAD = math.pi / 180.0

# 비/눈으로 볼 강수형태(PTY) 코드 — 기상청 코드값 그대로(지어낸 분류 아님).
_PTY_RAIN = {1, 4, 5, 6}  # 비/소나기/빗방울/빗방울눈날림
_PTY_SNOW = {2, 3, 6, 7}  # 비/눈, 눈, 빗방울눈날림, 눈날림 — 6은 비/눈 둘 다 걸침

_HOT_TEMP_C = 28.0
_COLD_TEMP_C = 3.0

# (nx, ny) 단위 캐시 — 기상청 초단기실황은 매시 정시 생성·40분부터 제공이라
# 요청마다 부를 필요가 없다. discovery.py의 _kakao_cache와 같은 패턴(모듈 전역
# dict + TTL + 개수 상한 prune).
_CACHE_TTL_SEC = 20 * 60
_CACHE_MAX = 200
_weather_cache: dict[tuple[int, int], dict] = {}


@dataclass
class WeatherSnapshot:
    condition: str  # "rain" | "snow" | "clear"
    temp_c: float | None
    observed_at: datetime
    is_hot: bool = False
    is_cold: bool = False


def _latlng_to_grid(lat: float, lng: float) -> tuple[int, int]:
    re = _RE / _GRID
    slat1 = _SLAT1 * _DEGRAD
    slat2 = _SLAT2 * _DEGRAD
    olon = _OLON * _DEGRAD
    olat = _OLAT * _DEGRAD

    sn = math.tan(math.pi * 0.25 + slat2 * 0.5) / math.tan(math.pi * 0.25 + slat1 * 0.5)
    sn = math.log(math.cos(slat1) / math.cos(slat2)) / math.log(sn)
    sf = math.tan(math.pi * 0.25 + slat1 * 0.5)
    sf = math.pow(sf, sn) * math.cos(slat1) / sn
    ro = math.tan(math.pi * 0.25 + olat * 0.5)
    ro = re * sf / math.pow(ro, sn)

    ra = math.tan(math.pi * 0.25 + lat * _DEGRAD * 0.5)
    ra = re * sf / math.pow(ra, sn)
    theta = lng * _DEGRAD - olon
    if theta > math.pi:
        theta -= 2.0 * math.pi
    if theta < -math.pi:
        theta += 2.0 * math.pi
    theta *= sn

    x = ra * math.sin(theta) + _XO + 0.5
    y = ro - ra * math.cos(theta) + _YO + 0.5
    return int(x), int(y)


def _base_datetime_kst(now_utc: datetime) -> tuple[str, str]:
    """초단기실황은 매시 정시 관측값을 만들고 40분부터 제공한다. 아직 이번 시각
    값이 안 올라왔을 수 있는 여유(00~39분)엔 직전 시각을 요청한다."""
    kst = now_utc + timedelta(hours=9)
    if kst.minute < 40:
        kst -= timedelta(hours=1)
    return kst.strftime("%Y%m%d"), kst.strftime("%H00")


def _prune_cache() -> None:
    now = time.time()
    for key in [k for k, v in _weather_cache.items() if now - v["at"] > _CACHE_TTL_SEC]:
        del _weather_cache[key]
    while len(_weather_cache) > _CACHE_MAX:
        oldest_key = min(_weather_cache, key=lambda k: _weather_cache[k]["at"])
        del _weather_cache[oldest_key]


def _parse_snapshot(items: list[dict], observed_at: datetime) -> WeatherSnapshot:
    values = {item.get("category"): item.get("obsrValue") for item in items}
    pty_raw = values.get("PTY")
    temp_raw = values.get("T1H")
    try:
        pty = int(pty_raw) if pty_raw not in (None, "") else 0
    except (TypeError, ValueError):
        pty = 0
    try:
        temp_c = float(temp_raw) if temp_raw not in (None, "") else None
    except (TypeError, ValueError):
        temp_c = None

    if pty in _PTY_SNOW:
        condition = "snow"
    elif pty in _PTY_RAIN:
        condition = "rain"
    else:
        condition = "clear"

    return WeatherSnapshot(
        condition=condition,
        temp_c=temp_c,
        observed_at=observed_at,
        is_hot=temp_c is not None and temp_c >= _HOT_TEMP_C,
        is_cold=temp_c is not None and temp_c <= _COLD_TEMP_C,
    )


async def get_current_weather(lat: float, lng: float) -> WeatherSnapshot | None:
    """현재 날씨를 가져온다. 키 미설정, 조회 실패, 응답 파싱 실패 등 어떤 이유로든
    실패하면 None을 준다 — 검색/랭킹 흐름을 절대 막지 않는 부가 기능이다."""
    # 기상청 API도 data.go.kr 소속이라, 착한가격업소/지역화폐 어댑터가 이미 쓰는
    # 공용 인증키(DATA_GO_KR_KEY)로 그대로 조회된다(제품별 "활용신청" 승인만
    # 별도로 필요) — dine_out_price.py/local_currency.py와 같은 폴백 패턴.
    # 전용 키(WEATHER_API_KEY)를 따로 넣으면 그게 우선한다.
    service_key = settings.weather_api_key or settings.data_go_kr_key
    if not service_key:
        return None

    nx, ny = _latlng_to_grid(lat, lng)
    cached = _weather_cache.get((nx, ny))
    if cached and time.time() - cached["at"] < _CACHE_TTL_SEC:
        return cached["snapshot"]

    base_date, base_time = _base_datetime_kst(datetime.now(UTC))
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                KMA_BASE_URL,
                params={
                    "serviceKey": service_key,
                    "pageNo": 1,
                    "numOfRows": 10,
                    "dataType": "JSON",
                    "base_date": base_date,
                    "base_time": base_time,
                    "nx": nx,
                    "ny": ny,
                },
            )
            resp.raise_for_status()
            body = resp.json()
        items = body["response"]["body"]["items"]["item"]
    except Exception:
        logger.warning("weather fetch/parse failed", exc_info=True)
        return None

    snapshot = _parse_snapshot(items, observed_at=datetime.now(UTC))
    _weather_cache[(nx, ny)] = {"snapshot": snapshot, "at": time.time()}
    _prune_cache()
    return snapshot
