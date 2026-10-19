"""로그·알림 문자열에서 키·토큰·헤더 값을 가리는 최소 필터."""
import re

_PATTERNS = [
    re.compile(r"(?i)(authorization|x-naver-[\w-]+|client[-_ ]?secret|client[-_ ]?id|api[-_ ]?key|token|secret)(\s*[=:]\s*)(\S+)"),
]


def redact(text: str) -> str:
    out = str(text)
    for pat in _PATTERNS:
        out = pat.sub(lambda m: f"{m.group(1)}{m.group(2)}***", out)
    return out
