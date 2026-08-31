"""AI가 문장만 다듬고 숫자/사실은 새로 만들지 않았는지 확인하는 공용 검증
(AI 활용 확대 안건 D/C, 2026-08-31).

route_planner.generate_summary(summarize_route)는 프롬프트 지시만으로
"숫자는 준 것만 써라"를 지켜왔는데, 프롬프트 지시는 강제력이 없다 — 모델이
실수로 새 숫자를 만들어내도 걸러낼 방법이 없었다. 매장 카드 한 줄 소개(D)와
개인화 다이제스트(C)는 결과를 DB에 캐시해서 반복 노출하므로(1회성 응답이
아니라 오래 남는 문구), 이 둘에는 명시적인 사후 검증을 추가한다 — 프롬프트에
준 숫자 집합에 없는 숫자가 결과 문장에 하나라도 있으면 그 결과는 통째로
버리고(호출부가 결정론적 폴백을 쓰게) 저장하지 않는다.

숫자만 비교하고 문장 전체를 비교하지 않는 이유: AI가 "8,000원"을 "8천원"으로
바꿔 쓰는 것처럼 같은 사실을 다른 표기로 쓰는 건 허용해야 한다(그건 "표현"의
영역) — 오직 "그 자리에 없던 숫자가 새로 등장했는가"만 사실 위반이다."""

import re

_NUMBER_RE = re.compile(r"\d[\d,]*")


def extract_numbers(text: str) -> set[str]:
    """문자열에서 숫자만 뽑아 콤마를 뗀 순수 자릿수 문자열 집합으로 정규화한다
    ("8,000" → "8000") — 표기(콤마 유무)가 달라도 같은 숫자로 인식하기 위함."""
    return {match.replace(",", "") for match in _NUMBER_RE.findall(text)}


def has_unapproved_numbers(text: str, allowed_numbers: set[str]) -> bool:
    """text에 있는 숫자 중 allowed_numbers(프롬프트에 실제로 준 숫자, 콤마 없이
    정규화된 문자열)에 없는 게 하나라도 있으면 True. allowed_numbers가 비어있는데
    text에 숫자가 하나라도 있으면 당연히 전부 미승인이라 True."""
    return bool(extract_numbers(text) - allowed_numbers)
