from app.domain.enums import RouteActivity

# Place.category_name은 공공데이터(업종명/업태구분명)와 카카오 로컬 API가 준 실제
# 업종 문자열을 그대로 저장한 자유 텍스트다(app/domain/place.py 주석 참고, 예:
# "일반음식점 > 한식", "휴게음식점 > 제과점영업", 카카오 "음식점 > 카페 > 커피전문점").
# 여기서 "무엇을 할 것인지"(Activity)를 새 컬럼 없이 키워드로 뽑아낸다 — 이미
# spatial_query.EXCLUDED_CATEGORY_KEYWORDS(미용실/이용업 제외)에서 쓰던 것과 같은
# 패턴이다: 존재하지 않는 데이터를 만들지 않고, 이미 있는 실제 문자열을 해석만 한다.
#
# 순서가 중요하다 — 예를 들어 "카페 > 디저트카페"처럼 두 키워드가 같이 들어있는
# 문자열은 먼저 매치되는 활동으로 분류된다. dining을 가장 먼저 검사해서 "식당"류가
# 실수로 카페/디저트로 새지 않게 한다.
ACTIVITY_KEYWORDS: dict[RouteActivity, tuple[str, ...]] = {
    RouteActivity.DINING: (
        "일반음식점",
        "한식",
        "중식",
        "일식",
        "양식",
        "분식",
        "고기",
        "국밥",
        "찌개",
        "국수",
        "냉면",
        "돈까스",
        "뷔페",
        "구이",
        "탕",
        "찜",
        "식당",
        "백반",
    ),
    RouteActivity.CAFE: ("카페", "커피", "다방"),
    RouteActivity.DESSERT: ("제과", "베이커리", "디저트", "빙수", "아이스크림", "도넛", "와플", "케이크"),
}

ACTIVITY_LABELS: dict[RouteActivity, str] = {
    RouteActivity.DINING: "식사",
    RouteActivity.CAFE: "커피",
    RouteActivity.DESSERT: "디저트",
}


def classify_activity(category_name: str | None) -> RouteActivity | None:
    """category_name 문자열에서 활동을 추정한다. 매칭되는 키워드가 없으면 None —
    "휴게음식점"만 있고 세부 업태가 없는 경우처럼 실제로 알 수 없는 경우를 억지로
    카페든 디저트든 하나로 지어내지 않고 정직하게 미분류로 둔다."""
    if not category_name:
        return None
    for activity, keywords in ACTIVITY_KEYWORDS.items():
        if any(kw in category_name for kw in keywords):
            return activity
    return None
