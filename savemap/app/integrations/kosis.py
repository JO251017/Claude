import logging
import time
from dataclasses import dataclass
from datetime import UTC, datetime

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


@dataclass
class CpiSnapshot:
    """소비자물가지수(2020=100) 스냅샷. yoy_pct는 전년 동월 같은 기간 값을 응답에서
    같이 찾았을 때만 채운다 — 못 찾으면 지어내지 않고 None으로 둔다."""

    index: float
    period: str  # "202607" 형태(연월)
    yoy_pct: float | None
    observed_at: datetime


# 날씨와 달리 위치별로 값이 다르지 않은 전국 단일 통계라 캐시 슬롯이 하나면 된다.
# 월 1회만 갱신되는 통계라 TTL을 넉넉히 잡는다(요청마다 KOSIS를 부를 이유가 없다).
_CACHE_TTL_SEC = 6 * 60 * 60
_cache: dict | None = None


def _row_value(row: dict, *candidates: str):
    """KOSIS 응답 필드명이 통계표/버전에 따라 조금씩 다를 수 있어 후보를 순서대로 본다
    (공공데이터 어댑터들과 같은 패턴, good_price.py 참고)."""
    for key in candidates:
        value = row.get(key)
        if value not in (None, ""):
            return value
    return None


def _parse_rows(rows: list[dict]) -> CpiSnapshot | None:
    parsed: dict[str, float] = {}
    for row in rows:
        period = _row_value(row, "PRD_DE", "PRD_DE1")
        value = _row_value(row, "DT")
        if period in (None, "") or value in (None, ""):
            continue
        try:
            parsed[str(period)] = float(value)
        except (TypeError, ValueError):
            continue
    if not parsed:
        return None

    latest_period = max(parsed)
    latest_value = parsed[latest_period]

    yoy_pct = None
    if len(latest_period) == 6:  # "YYYYMM"
        try:
            year_ago_period = f"{int(latest_period[:4]) - 1}{latest_period[4:]}"
        except ValueError:
            year_ago_period = None
        if year_ago_period in parsed and parsed[year_ago_period]:
            yoy_pct = (latest_value - parsed[year_ago_period]) / parsed[year_ago_period] * 100

    return CpiSnapshot(
        index=latest_value, period=latest_period, yoy_pct=yoy_pct, observed_at=datetime.now(UTC)
    )


async def get_latest_cpi() -> CpiSnapshot | None:
    """미설정, 조회 실패, 파싱 실패 등 어떤 이유로든 실패하면 None — 검색 흐름을
    막지 않는 부가 맥락 정보다."""
    if not settings.kosis_cpi_api_url:
        return None

    global _cache
    if _cache and time.time() - _cache["at"] < _CACHE_TTL_SEC:
        return _cache["snapshot"]

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(settings.kosis_cpi_api_url)
            resp.raise_for_status()
            body = resp.json()
        if not isinstance(body, list):
            # KOSIS는 파라미터 오류 시 리스트 대신 에러 객체({"err": ..., "errMsg": ...})를 준다.
            logger.warning("kosis unexpected response shape: %r", body)
            return None
        snapshot = _parse_rows(body)
    except Exception:
        logger.warning("kosis fetch/parse failed", exc_info=True)
        return None

    if snapshot is None:
        return None
    _cache = {"snapshot": snapshot, "at": time.time()}
    return snapshot
