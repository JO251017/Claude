"""AI Price Discovery Engine — price_validator 단계(지시서 28-10).

price_extractor(→ GeminiVisionClient.extract_price_discovery)가 이미 스키마
검증·출처 URL 검증·가격>0을 확인했다 — 이 모듈은 그다음 단계(결정론적 범위
검증 + 같은 배치 안 중복 제거)만 맡는다. 비정상적으로 크거나 작은 값은 버리지
않고 "검토 대상"으로 표시한다(지시서 원문: "비정상적으로 큰 값/작은 값은 검토
대상으로 보낸다")."""

import enum
from dataclasses import dataclass

from app.engine.menu_name import normalize_menu_name
from app.integrations.gemini import PriceDiscoveryPriceItem

# 한국 동네 식당/카페 메뉴 1인분 기준 상식적인 범위 밖이면(예: AI가 단위를
# 잘못 읽거나 세트/코스 가격을 개별 메뉴로 착각) 자동 승인하지 않고 검토로
# 보낸다. 절대적인 정답이 아니라 "이상치를 걸러내는" 보수적인 기준값이다.
MIN_REASONABLE_PRICE = 100
MAX_REASONABLE_PRICE = 300_000


class PriceVerdict(str, enum.Enum):
    VALID = "valid"
    NEEDS_REVIEW = "needs_review"


@dataclass
class ValidatedPrice:
    menu_name: str
    normalized_name: str
    price: float
    source_type: str
    source_url: str
    source_title: str | None
    observed_at: str | None
    evidence: str | None
    verdict: PriceVerdict


def validate_prices(items: list[PriceDiscoveryPriceItem]) -> list[ValidatedPrice]:
    """같은 배치 안에서 정규화 이름이 겹치는 항목은 먼저 나온 것만 남긴다(AI가
    같은 메뉴를 두 번 반환하는 경우 방지) — DB에 아직 아무 메뉴도 없는 매장만
    이 파이프라인의 후보이므로(candidate_selector), 기존 가격과의 충돌은
    이 단계에서 발생하지 않는다."""
    seen_normalized: set[str] = set()
    validated: list[ValidatedPrice] = []
    for item in items:
        normalized = normalize_menu_name(item.menu_name)
        if not normalized or normalized in seen_normalized:
            continue
        seen_normalized.add(normalized)

        verdict = (
            PriceVerdict.VALID
            if MIN_REASONABLE_PRICE <= item.price <= MAX_REASONABLE_PRICE
            else PriceVerdict.NEEDS_REVIEW
        )
        validated.append(
            ValidatedPrice(
                menu_name=item.menu_name,
                normalized_name=normalized,
                price=item.price,
                source_type=item.source_type,
                source_url=item.source_url,
                source_title=item.source_title,
                observed_at=item.observed_at,
                evidence=item.evidence,
                verdict=verdict,
            )
        )
    return validated
