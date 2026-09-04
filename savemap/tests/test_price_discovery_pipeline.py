from app.domain.enums import SourceType
from app.engine.price_discovery.confidence_engine import resolve_source_type
from app.engine.price_discovery.price_validator import PriceVerdict, validate_prices
from app.engine.price_discovery.store_matcher import MatchDecision, decide_match
from app.integrations.gemini import PriceDiscoveryPriceItem, PriceDiscoveryStoreMatch

# --- store_matcher: 지시서 28-8 임계값 ---


def _match(matched: bool, confidence: float) -> PriceDiscoveryStoreMatch:
    return PriceDiscoveryStoreMatch(matched=matched, confidence=confidence, reason="")


def test_high_confidence_match_is_auto():
    assert decide_match(_match(True, 0.97)) == MatchDecision.AUTO


def test_mid_confidence_match_goes_to_review():
    assert decide_match(_match(True, 0.85)) == MatchDecision.REVIEW


def test_low_confidence_match_is_rejected():
    assert decide_match(_match(True, 0.5)) == MatchDecision.REJECT


def test_ai_says_not_matched_is_always_rejected_even_with_high_confidence():
    # AI 신뢰도 조작 방지 — confidence 0.99라도 matched=false면 절대 자동 매칭 안 함
    # (동일 이름 다른 지점 같은 경우).
    assert decide_match(_match(False, 0.99)) == MatchDecision.REJECT


def test_threshold_boundaries_are_inclusive():
    assert decide_match(_match(True, 0.95)) == MatchDecision.AUTO
    assert decide_match(_match(True, 0.80)) == MatchDecision.REVIEW
    assert decide_match(_match(True, 0.7999)) == MatchDecision.REJECT


# --- price_validator: 범위 검증 + 배치 내 중복 제거 ---


def _item(name: str, price: float, source_type: str = "official") -> PriceDiscoveryPriceItem:
    return PriceDiscoveryPriceItem(
        menu_name=name,
        price=price,
        source_type=source_type,
        source_url="https://example.com",
        source_title=None,
        observed_at=None,
        evidence=None,
    )


def test_reasonable_price_is_valid():
    result = validate_prices([_item("김치찌개", 8000)])
    assert len(result) == 1
    assert result[0].verdict == PriceVerdict.VALID


def test_absurdly_high_price_needs_review_not_dropped():
    # 비정상적으로 큰 값은 버리지 않고 검토 대상으로 보낸다(지시서 원문).
    result = validate_prices([_item("코스요리", 5_000_000)])
    assert len(result) == 1
    assert result[0].verdict == PriceVerdict.NEEDS_REVIEW


def test_absurdly_low_price_needs_review():
    result = validate_prices([_item("김치찌개", 10)])
    assert result[0].verdict == PriceVerdict.NEEDS_REVIEW


def test_duplicate_normalized_name_in_same_batch_is_deduped():
    # AI가 같은 메뉴를 표기만 다르게 두 번 반환한 경우 — 첫 번째만 남는다.
    result = validate_prices([_item("아메리카노(ICE)", 3500), _item("아메리카노", 4000)])
    assert len(result) == 1
    assert result[0].price == 3500


def test_empty_menu_name_after_normalization_is_dropped():
    result = validate_prices([_item("   ", 5000)])
    assert result == []


# --- confidence_engine: source_type 매핑, AI confidence는 절대 재사용 안 함 ---


def test_official_maps_to_ai_discovery_official_source():
    assert resolve_source_type("official") == SourceType.S6_AI_DISCOVERY_OFFICIAL


def test_web_maps_to_ai_discovery_web_source():
    assert resolve_source_type("web") == SourceType.S6_AI_DISCOVERY_WEB


def test_unknown_source_type_falls_back_to_web_not_official():
    # 알 수 없는 값이면 더 낮은(제한적인) 쪽으로 안전하게 떨어진다 — 모르는 값을
    # "공식"으로 잘못 격상시키지 않는다.
    assert resolve_source_type("something-unexpected") == SourceType.S6_AI_DISCOVERY_WEB
