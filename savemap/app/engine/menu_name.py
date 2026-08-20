"""메뉴명 정규화.

지역 실측 비교(`price_comparison._region_prices`)는 원래 메뉴명이 글자 하나까지
똑같아야만 같은 메뉴로 쳤다. 그런데 착한가격업소 메뉴명은 정부 파일의 `품목N`
필드를 그대로 저장하고, 사용자 제보는 사진에서 AI가 읽은 문자열을 그대로 저장한다 —
"김치찌개"와 "김치찌개 " , "아메리카노"와 "아메리카노(ICE)"가 서로 다른 메뉴로
취급돼서, 12,000건 넘는 실제 가격이 있어도 대부분 비교가 안 되고 AI 추정 통상가로
떨어지고 있었다(2026-08-20 확인).

정규화는 **보수적으로** 한다. 표기 차이만 없애고 음식 자체가 다른 것은 절대 합치지
않는다 — "바지락칼국수"를 "칼국수"로 뭉개면 값이 다른 메뉴끼리 비교하게 되고, 그건
없는 절약률을 만들어내는 것과 같다. 대분류로 묶는 건 `canonical_dish()`가 따로
담당하며, 그건 애초에 시도 단위 평균인 정부 통계(참가격 외식비)와 맞출 때만 쓴다.
"""

import re
import unicodedata

# 괄호류 안의 내용은 표기 부가정보로 본다: "아메리카노(ICE)", "제육볶음[특]", "냉면<물>"
_BRACKETED = re.compile(r"[（(\[{<][^）)\]}>]*[）)\]}>]")

# 이름 사이에 끼는 구분자·공백. 붙여쓰기/띄어쓰기 차이를 없앤다.
_SEPARATORS = re.compile(r"[\s·・･\-–—_/\\,.·*]+")

# 이름 끝에 붙는 양·크기 표기. "칼국수(대)"는 위에서 이미 떨어지고, 여기서는
# 괄호 없이 붙은 "칼국수대", "삼겹살1인분" 같은 걸 잡는다. 접미사로 나올 때만
# 떼어내고(앞이 비면 안 됨), 음식명 자체가 짧아지는 건 막는다.
_SIZE_SUFFIX = re.compile(
    r"(소자|중자|대자|특대|곱빼기|곱배기|한판|일인분|1인분|이인분|2인분|인분|1인|2인)$"
)


def normalize_menu_name(name: str) -> str:
    """비교용 정규화 이름. 같은 메뉴의 표기 차이만 없앤다.

    비어 있거나 정규화 결과가 비면 원본을 소문자·공백정리만 해서 돌려준다 —
    빈 문자열끼리 전부 같은 메뉴로 묶이는 사고를 막기 위해서다.
    """
    if not name:
        return ""

    # 전각/반각, 조합형 한글 등을 한 형태로 통일한다(NFKC). "ＡＢ" → "ab".
    text = unicodedata.normalize("NFKC", name).strip().lower()
    fallback = _SEPARATORS.sub(" ", text).strip()

    text = _BRACKETED.sub("", text)
    text = _SEPARATORS.sub("", text)

    # 크기 표기는 여러 개 붙을 수 있다("삼겹살1인분대"). 다 떼되, 떼고 나서
    # 이름이 사라지면 떼기 전 상태를 쓴다.
    while True:
        stripped = _SIZE_SUFFIX.sub("", text)
        if stripped == text or not stripped:
            break
        text = stripped

    return text or fallback


# 참가격(한국소비자원) 외식비 8개 품목. 정부 통계가 이 8개만 시도별 평균가로
# 조사하기 때문에, 대분류 매핑도 딱 이 범위에서만 한다 — 통계에 없는 품목까지
# 억지로 묶으면 비교 기준이 없는데 있는 것처럼 보이게 된다.
#
# 키워드는 "이 단어가 메뉴명에 들어 있으면 그 품목"이라는 뜻이다. 순서가 중요하다:
# "물냉면"은 냉면으로, "김치찌개백반"은 김치찌개백반으로 잡혀야 하므로 더 구체적인
# 쪽을 앞에 둔다.
_DISH_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("김치찌개백반", ("김치찌개백반", "김치찌개정식", "김치찌개")),
    ("삼겹살", ("삼겹살",)),
    ("삼계탕", ("삼계탕",)),
    ("자장면", ("자장면", "짜장면")),
    ("냉면", ("냉면",)),
    ("비빔밥", ("비빔밥",)),
    ("칼국수", ("칼국수",)),
    ("김밥", ("김밥",)),
)


def canonical_dish(name: str) -> str | None:
    """참가격 외식비 8개 품목 중 하나로 대분류한다. 해당 없으면 None.

    정부 통계는 "칼국수" 하나로 시도 평균을 내기 때문에 "바지락칼국수"도 여기서는
    칼국수로 본다 — 대신 이 매핑의 결과는 **정부 통계 비교에만** 쓰고, 매장 간
    실측 비교(`normalize_menu_name`)에는 절대 쓰지 않는다.
    """
    normalized = normalize_menu_name(name)
    if not normalized:
        return None
    for dish, keywords in _DISH_KEYWORDS:
        if any(keyword in normalized for keyword in keywords):
            return dish
    return None
