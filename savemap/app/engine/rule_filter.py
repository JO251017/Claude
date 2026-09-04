from datetime import datetime, timezone

from app.domain.enums import Category, Layer, RouteActivity
from app.domain.offer import Offer
from app.domain.place import Place
from app.engine.activity_classifier import classify_activity

MVP_LAYERS = (Layer.CORE_BASE, Layer.REGULAR)


def rule_filter(
    rows: list[tuple[Offer, Place, float]],
    category: Category | None = None,
    now: datetime | None = None,
    mvp_only: bool = False,
    activities: list[RouteActivity] | None = None,
) -> list[tuple[Offer, Place, float]]:
    """activities: 비어있지 않으면 place.category_name에서 분류한 활동이 그 목록에
    속하는 행만 남긴다(AI 절약 플랜의 "무엇을 할까요?" 선택, 2026-08-13). 미분류
    (None) 매장은 목록에 넣지 않는다 — 활동을 지정했는데 뭔지 모르는 곳을 섞어
    보여주면 사용자가 고른 조건과 안 맞는 결과가 나온다. /search는 이 파라미터를
    넘기지 않아 기존 동작 그대로다.

    mvp_only=True였을 때(2026-08-13 이전 기본값) Layer.FLASH(마감임박 타임세일)가
    검색에서 통째로 빠졌다 — 사장님이 실제로 TTL 있는 타임세일을 등록해도 지도에
    영원히 안 떴다는 뜻. "지금 아니면 놓친다"는 재방문을 만드는 핵심 훅인데
    죽여뒀던 것(사용자 지시, 2026-08-18: "핵심 콘셉트 강화 — FLASH 긴급성
    되살리기"). FLASH는 ingestion/validate.py가 만료 시각 없이는 애초에 못
    들어오게 막아서(test_validate_requires_expiry_for_flash) 아래 expires_at
    체크만으로 안전하게 걸러진다 — 영원히 안 없어지는 "타임세일"이 생길 수 없다.
    mvp_only=True로 명시적으로 넘기는 호출부는 현재 없다(과거 스텁 옵션)."""
    now = now or datetime.now(timezone.utc)
    result: list[tuple[Offer, Place, float]] = []
    for offer, place, distance in rows:
        if mvp_only and offer.layer not in MVP_LAYERS:
            continue
        if category is not None and offer.category != category:
            continue
        if activities and classify_activity(place.category_name) not in activities:
            continue
        if offer.expires_at is not None and offer.expires_at < now:
            continue
        if offer.valid_from is not None and offer.valid_from > now:
            continue
        result.append((offer, place, distance))
    return result
