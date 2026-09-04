"""한국소비자원 참가격 — 외식비 시도별 평균가격.

왜 넣는가: 지금까지 주변에 비교할 매장이 없으면 Gemini가 짐작한 통상가
(`MenuItem.ai_typical_price`)로 절약률을 계산했다. 앱이 보여주는 "얼마 아꼈다"는
숫자의 근거가 AI 추측이었다는 뜻이다. 참가격은 정부(한국소비자원)가 매달 조사해
공표하는 통계라, 같은 자리를 실제 조사값으로 바꿀 수 있다.

한계를 분명히 해둔다:
- 품목이 8개뿐이다 (냉면·비빔밥·김치찌개백반·삼겹살·자장면·삼계탕·칼국수·김밥).
- 시도 단위 평균이다. "평택시 아무개 식당"이 아니라 "경기 평균"이다.
따라서 개별 매장 실측 비교를 절대 대체하지 않는다 — 우선순위는 항상
실측 > 정부 통계 > AI 추정이며, 사용자에게도 어느 기준으로 계산했는지 같이 보여준다.

엔드포인트: 참가격 오픈API의 정확한 주소·응답 필드명을 개발 환경에서 확인하지
못했다(price.go.kr 접근 차단). 그래서 착한가격업소와 같은 방어 패턴을 쓴다 —
URL은 코드에 박지 않고 `DINE_OUT_PRICE_API_URL` 환경변수로 받고(미설정이면 아무것도
지어내지 않고 건너뛴다), 필드명은 후보를 여러 개 인식하며, 한 건도 못 읽으면 실제
응답의 키 목록을 그대로 돌려줘서 무엇을 고쳐야 하는지 바로 알 수 있게 한다.
파일(CSV)을 직접 받아 넣는 경로도 같이 열어둔다.
"""

import csv
import io
import logging

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.domain.regional_price import RegionalPriceStat
from app.engine.menu_name import canonical_dish

logger = logging.getLogger(__name__)

_TIMEOUT = 20.0

# 시도 표기가 출처마다 갈린다("충남" / "충청남도" / "충청남도 "). 짧은 형태로 통일해서
# 저장하고, 조회할 때도 같은 함수를 통과시켜 기준을 하나로 맞춘다.
_REGION_ALIASES: dict[str, str] = {
    "서울특별시": "서울", "서울시": "서울",
    "부산광역시": "부산", "부산시": "부산",
    "대구광역시": "대구", "대구시": "대구",
    "인천광역시": "인천", "인천시": "인천",
    "광주광역시": "광주", "광주시": "광주",
    "대전광역시": "대전", "대전시": "대전",
    "울산광역시": "울산", "울산시": "울산",
    "세종특별자치시": "세종", "세종시": "세종",
    "경기도": "경기",
    "강원특별자치도": "강원", "강원도": "강원",
    "충청북도": "충북",
    "충청남도": "충남",
    "전북특별자치도": "전북", "전라북도": "전북",
    "전라남도": "전남",
    "경상북도": "경북",
    "경상남도": "경남",
    "제주특별자치도": "제주", "제주도": "제주",
}


def normalize_region(value: str | None) -> str | None:
    """시도명을 짧은 표기로 통일한다. 시도가 아니면 None."""
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text in _REGION_ALIASES:
        return _REGION_ALIASES[text]
    if text in set(_REGION_ALIASES.values()):
        return text
    return None


def region_from_address(address: str | None) -> str | None:
    """매장 주소의 맨 앞 토큰에서 시도를 뽑는다 ("충청남도 아산시 …" → "충남").

    주소가 시도로 시작하지 않거나 못 알아보면 None을 돌려주고, 호출부는 정부 통계
    비교를 그냥 건너뛴다 — 엉뚱한 지역 평균과 비교하느니 비교를 안 하는 게 낫다.
    """
    if not address:
        return None
    return normalize_region(address.strip().split()[0])


def _row_value(row: dict, *candidates: str):
    """공공데이터 컬럼명이 배포본마다 조금씩 달라서 후보를 순서대로 본다
    (착한가격업소 어댑터와 같은 방식)."""
    for key in candidates:
        value = row.get(key)
        if value not in (None, ""):
            return value
    stripped = {str(k).replace(" ", ""): v for k, v in row.items()}
    for key in candidates:
        value = stripped.get(key.replace(" ", ""))
        if value not in (None, ""):
            return value
    return None


def parse_price(value) -> float | None:
    """'12,538' / '12538원' / 12538.0 을 모두 다룬다. 외식 1인분 가격으로 말이 안 되는
    값(1천 원 미만·30만 원 초과)은 파싱 실패로 본다 — 단위가 다른 컬럼을 잘못 읽었을
    때 이상한 기준가가 조용히 들어가는 걸 막는다."""
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        price = float(value)
    else:
        digits = "".join(ch for ch in str(value) if ch.isdigit())
        if not digits:
            return None
        price = float(digits)
    return price if 1_000 <= price <= 300_000 else None


def parse_row(row: dict) -> dict | None:
    """한 행 → {dish, region, price, survey_period}. 셋 중 하나라도 못 읽으면 None."""
    raw_dish = _row_value(row, "품목명", "품목", "상품명", "조사품목", "itemName", "goodName")
    dish = canonical_dish(str(raw_dish)) if raw_dish else None
    if not dish:
        return None

    region = normalize_region(
        _row_value(row, "지역명", "지역", "시도", "시도명", "areaName", "sidoName")
    )
    if not region:
        return None

    price = parse_price(_row_value(row, "평균가격", "가격", "평균가", "price", "avgPrice"))
    if price is None:
        return None

    period = _row_value(row, "조사년월", "조사월", "기준년월", "yearMonth", "surveyMonth")
    return {
        "dish": dish,
        "region": region,
        "price": price,
        "survey_period": str(period).strip()[:16] if period else None,
    }


def parse_csv_bytes(content: bytes) -> list[dict]:
    """참가격에서 내려받은 CSV를 dict 행 목록으로. 공공기관 파일은 cp949가 흔하다."""
    text = None
    for encoding in ("utf-8-sig", "cp949", "utf-8"):
        try:
            text = content.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        raise ValueError("CSV 인코딩을 해석할 수 없습니다 (utf-8/cp949 지원)")
    return [dict(row) for row in csv.DictReader(io.StringIO(text))]


def _extract_rows(payload) -> list[dict]:
    """응답 본문에서 행 목록을 찾아낸다. 공공데이터포털 배포본이 odcloud 형식
    ({"data": [...]})일 수도, apis.data.go.kr 표준 봉투일 수도 있어 둘 다 훑는다."""
    if isinstance(payload, list):
        return [r for r in payload if isinstance(r, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("data", "items", "row", "list"):
        value = payload.get(key)
        if isinstance(value, list):
            return [r for r in value if isinstance(r, dict)]
        if isinstance(value, dict):
            return [value]
    body = payload.get("response", {}).get("body", {}) if payload.get("response") else {}
    items = body.get("items") if isinstance(body, dict) else None
    if isinstance(items, dict):
        items = items.get("item")
    if isinstance(items, list):
        return [r for r in items if isinstance(r, dict)]
    if isinstance(items, dict):
        return [items]
    return []


async def _fetch_rows() -> list[dict]:
    url = settings.dine_out_price_api_url
    if not url:
        return []
    params = {"returnType": "JSON", "perPage": 1000, "page": 1}
    if settings.data_go_kr_key and "serviceKey" not in url:
        params["serviceKey"] = settings.data_go_kr_key
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        return _extract_rows(resp.json())


async def store_rows(session: AsyncSession, raw_rows: list[dict]) -> dict:
    """파싱된 행을 (품목, 시도) 단위로 upsert 한다. 같은 조합이 여러 번 오면
    마지막 값으로 덮어쓴다 — 통계는 최신 조사분만 있으면 된다."""
    parsed = [p for p in (parse_row(r) for r in raw_rows) if p is not None]

    if not parsed:
        # 한 건도 못 읽었으면 필드명 추측이 틀렸다는 뜻이다. 실제 키 목록을 그대로
        # 돌려줘서 무엇을 고쳐야 하는지 바로 보이게 한다(착한가격업소에서 같은 문제로
        # 0건만 나오던 이력이 있어 같은 안전장치를 둔다).
        return {
            "raw_rows": len(raw_rows),
            "usable_rows": 0,
            "created": 0,
            "updated": 0,
            "sample_raw_keys": sorted(raw_rows[0].keys())[:40] if raw_rows else [],
        }

    created = updated = 0
    for item in parsed:
        existing = (
            await session.execute(
                select(RegionalPriceStat).where(
                    RegionalPriceStat.dish == item["dish"],
                    RegionalPriceStat.region == item["region"],
                )
            )
        ).scalar_one_or_none()
        if existing is None:
            session.add(RegionalPriceStat(**item))
            created += 1
        else:
            existing.price = item["price"]
            existing.survey_period = item["survey_period"]
            updated += 1
    await session.commit()

    return {
        "raw_rows": len(raw_rows),
        "usable_rows": len(parsed),
        "created": created,
        "updated": updated,
        "dishes": sorted({p["dish"] for p in parsed}),
        "regions": sorted({p["region"] for p in parsed}),
    }


async def sync_dine_out_prices(session: AsyncSession) -> dict:
    """참가격 외식비 통계를 받아 저장한다. URL 미설정이면 아무것도 하지 않는다."""
    if not settings.dine_out_price_api_url:
        return {
            "skipped": True,
            "reason": "DINE_OUT_PRICE_API_URL이 설정되지 않았습니다. "
            "설정 전까지는 정부 통계 기준 없이 기존 동작(실측 → AI 추정)을 유지합니다.",
        }
    try:
        raw_rows = await _fetch_rows()
    except httpx.HTTPError as exc:
        logger.warning("참가격 외식비 조회 실패: %s", exc)
        return {"skipped": True, "reason": f"조회 실패: {exc.__class__.__name__}: {exc}"}
    return await store_rows(session, raw_rows)


async def get_regional_price(
    session: AsyncSession, dish: str, region: str
) -> RegionalPriceStat | None:
    return (
        await session.execute(
            select(RegionalPriceStat).where(
                RegionalPriceStat.dish == dish, RegionalPriceStat.region == region
            )
        )
    ).scalar_one_or_none()
