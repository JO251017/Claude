from urllib.parse import quote

from app.api.schemas.search import SavingsReportItem, SearchResultItem, SignatureMenuItem
from app.domain.enums import BusinessStatus
from app.domain.menu_item import MenuItem
from app.engine.ranker import RankedOffer
from app.engine.savings_report import build_savings_report


def build_search_result_item(
    r: RankedOffer,
    menu_items_by_place: dict[int, list[MenuItem]],
    status_by_place: dict[int, BusinessStatus] | None = None,
) -> SearchResultItem:
    """RankedOffer 한 건을 API 응답 모양(SearchResultItem)으로 조립한다 — /search와
    /route/suggest가 정확히 같은 모양의 결과를 내야(프론트가 같은 상세 화면을 그대로
    재사용하므로) 이 조립 로직도 한 곳에만 둔다. 원래 app/api/v1/search.py의 for
    루프 본문에 있던 코드를 그대로 옮긴 것."""
    c = r.candidate
    place_items = menu_items_by_place.get(c.place_id, [])
    if c.menu_item_id is not None:
        # 절약률을 계산한 바로 그 메뉴만 대표로 보여준다 — 예전엔 못 찾으면(메뉴
        # 삭제 등으로 링크가 끊기면) "가장 먼저 등록된 메뉴"로 조용히 폴백해서,
        # 카드에 뜬 대표메뉴 가격과 실제 절약률 계산 근거가 다를 수 있었다. 링크가
        # 끊긴 경우 엉뚱한 메뉴를 대표로 세우느니 대표메뉴 없이 보여준다(지어내지 않기).
        signature = next((item for item in place_items if item.id == c.menu_item_id), None)
    else:
        # 메뉴에서 파생되지 않은 오퍼(사장님 직접 등록 할인 등)만 이 폴백을 쓴다.
        signature = place_items[0] if place_items else None
    report = build_savings_report(
        savings_rate=r.breakdown.savings_rate,
        discover_count=c.discover_count,
        dining_count=c.dining_count,
        recommend_count=c.recommend_count,
        verification_count=c.verification_count,
        last_verified_at=c.last_verified_at,
        benchmark_source=c.benchmark_source,
        benchmark_sample_count=c.benchmark_sample_count,
    )
    status = (status_by_place or {}).get(c.place_id)
    return SearchResultItem(
        offer_id=c.offer_id,
        place_id=c.place_id,
        place_name=c.place_name,
        category_name=c.place_category_name,
        business_status=status.value if status else None,
        report=SavingsReportItem(
            score=report.score,
            grade=report.grade,
            confidence_tier=report.confidence_tier,
            confidence_stars=report.confidence_stars,
            confidence_label=report.confidence_label,
            freshness_tier=report.freshness_tier,
            freshness_label=report.freshness_label,
            days_since_verified=report.days_since_verified,
            reasons=report.reasons,
            one_line=report.one_line,
        ),
        signature_menu=(
            SignatureMenuItem(name=signature.name, price=float(signature.price))
            if signature
            else None
        ),
        recommend_count=c.recommend_count,
        kakao_url=(
            f"https://place.map.kakao.com/{c.place_kakao_id}"
            if c.place_kakao_id
            else f"https://map.kakao.com/link/search/{quote(c.place_name)}"
        ),
        address=c.place_address,
        phone=c.place_phone,
        category=c.category,
        layer=c.layer,
        distance_m=round(c.distance_m, 1),
        lat=c.lat,
        lng=c.lng,
        base_price=r.breakdown.base_price,
        final_price=r.breakdown.final_price,
        total_savings=r.breakdown.total_savings,
        savings_rate=r.breakdown.savings_rate,
        savings_source=c.benchmark_source,
        expires_at=c.expires_at,
        trust_score=c.trust_score,
        verification_count=c.verification_count,
        last_verified_at=c.last_verified_at,
        discover_count=c.discover_count,
        dining_count=c.dining_count,
        score=round(r.score, 4),
        accepts_local_currency=c.accepts_local_currency,
    )
