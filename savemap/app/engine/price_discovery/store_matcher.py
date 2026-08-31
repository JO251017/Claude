"""AI Price Discovery Engine — store_matcher 단계(지시서 28-8).

AI(price_extractor)가 이미 store_match(matched/confidence/reason)를 판단해뒀다
— 이 모듈은 그 값을 "채택/검토/거절" 정책으로 바꾸는 결정론적 규칙만 갖는다.
AI가 준 confidence 숫자를 그대로 신뢰도로 쓰지 않고(그건 confidence_engine.py의
역할), 여기서는 오직 "이 자료를 이 매장 것으로 채택할지" 임계값 판단에만
쓴다(28-14 원칙과 동일한 맥락 — AI 자신의 판단과 SaveMap의 신뢰도는 별개)."""

import enum

from app.core.config import settings
from app.integrations.gemini import PriceDiscoveryStoreMatch


class MatchDecision(str, enum.Enum):
    AUTO = "auto"  # confidence >= auto_threshold(기본 0.95) — 자동 채택
    REVIEW = "review"  # review_threshold <= confidence < auto_threshold — 검토 큐
    REJECT = "reject"  # 그 외, 또는 AI 자신이 matched=false라고 답함


def decide_match(store_match: PriceDiscoveryStoreMatch) -> MatchDecision:
    if not store_match.matched:
        return MatchDecision.REJECT
    if store_match.confidence >= settings.price_discovery_match_auto_threshold:
        return MatchDecision.AUTO
    if store_match.confidence >= settings.price_discovery_match_review_threshold:
        return MatchDecision.REVIEW
    return MatchDecision.REJECT
