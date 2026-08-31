"""AI Price Discovery Engine — confidence_engine 단계(지시서 28-14).

핵심 원칙: "AI가 반환한 confidence를 그대로 SaveMap 신뢰도로 사용하지 않는다."
이 모듈이 실제로 하는 일은 두 가지뿐이다.

1. price_extractor가 돌려준 source_type 문자열("official"/"web")을
   app.domain.enums.SourceType의 실제 값(S6_AI_DISCOVERY_OFFICIAL/WEB)으로
   매핑한다 — 이 값이 새로 만들어지는 MenuItem.source가 된다.
2. AI가 store_matcher 단계에서 준 confidence 숫자는 여기서 다시 쓰지 않는다 —
   그 값은 "이 자료를 이 매장 것으로 채택할지"(store_matcher.py)에만 쓰이고
   끝났다. 신뢰도(별점/등급)는 기존과 완전히 동일한 경로(app/engine/
   savings_report.py — 실제 방문/영수증 인증/추천 등 사람이 남긴 행동 신호로만
   계산)를 그대로 탄다. 이 저장소는 지금까지 어떤 소스(S1~S5)도 "발견 즉시
   높은 신뢰도"를 받지 않는다 — AI Price Discovery로 찾은 가격만 예외로 특별히
   더 낮은 초기 신뢰도를 주는 건 오히려 일관성을 깨는 것이라 이번 범위에서는
   하지 않는다. Offer.benchmark_source(region/gov/ai — "무엇과 비교했는지")는
   compare_menu_item이 이웃 매장 데이터로 그때그때 새로 계산하므로, 이 항목의
   출처(MenuItem.source)와는 애초에 다른 축이라 여기서 건드릴 게 없다.
   (추후 MenuItem.source 자체를 신뢰도 계산에 반영하는 건 이 저장소의 기존
   소스 5종 전부에 영향을 주는 더 큰 리팩터라 이번 Price Discovery 범위 밖으로
   남겨둔다 — AI Discovery만 특별 취급하지 않는다.)
"""

from app.domain.enums import SourceType

_SOURCE_TYPE_MAP: dict[str, SourceType] = {
    "official": SourceType.S6_AI_DISCOVERY_OFFICIAL,
    "web": SourceType.S6_AI_DISCOVERY_WEB,
}


def resolve_source_type(extracted_source_type: str) -> SourceType:
    return _SOURCE_TYPE_MAP.get(extracted_source_type, SourceType.S6_AI_DISCOVERY_WEB)
