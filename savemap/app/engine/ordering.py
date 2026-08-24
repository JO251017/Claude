"""후보 정렬 기준 — 검색(/v1/search)과 AI 절약 플랜(/v1/route/suggest) 둘 다
같은 몇 가지 정렬 기준(가격/신뢰도/최신성/거리)을 쓴다. 원래 route_planner.py에만
있었는데(_preference_sort_key), 검색에도 같은 정렬 옵션을 열면서(2026-08-22) 한
곳으로 뺐다 — route_planner의 동작은 순수 이동이라 바뀌지 않는다.

문자열 키로 받는 이유: RoutePreference와 SearchSort 두 enum이 서로 다른 맥락에서
쓰이지만(전자는 AI 절약 플랜 전용, 후자는 검색 전용 — "추천순" 같은 각자만의 값이
있어서 하나로 합치면 안 된다) 겹치는 값(cheapest/verified/recent/distance)의
문자열은 같도록 맞춰뒀다. 어느 쪽 enum이든 .value를 그대로 넘기면 된다."""

from datetime import datetime, timezone

# 값이 없는 항목(trust_score 미검증=0.5, last_verified_at=None)을 정렬상 임의로
# 좋은 자리로 보내지 않는다 — "모른다"는 신호를 그대로 정렬 끝으로 민다.
_EPOCH = datetime.min.replace(tzinfo=timezone.utc)


def sort_key_for(name: str):
    if name == "cheapest":
        return lambda r: r.breakdown.final_price
    if name == "verified":
        return lambda r: (-r.candidate.trust_score, -r.candidate.verification_count)
    if name == "recent":
        return lambda r: -(r.candidate.last_verified_at or _EPOCH).timestamp()
    if name == "distance":
        return lambda r: r.candidate.distance_m
    raise ValueError(f"알 수 없는 정렬 기준: {name}")
