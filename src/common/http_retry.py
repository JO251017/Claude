"""재시도·호출 간격 제어. 외부 호출부(DatalabTrendSource 등)가 공통으로 쓴다."""
import json
import socket
import time
import urllib.error
import urllib.request


class HttpError(Exception):
    """HTTP 상태 오류. 응답 본문·헤더 원문은 보관하지 않고 상태코드와 Retry-After(초)만 둔다."""

    def __init__(self, status: int, retry_after: float | None = None, api_error: str = ""):
        self.status = status
        self.retry_after = retry_after
        self.api_error = api_error
        super().__init__(f"HTTP {status}")


class RetryExhausted(Exception):
    def __init__(self, kind: str, attempts: int, detail: str):
        self.kind = kind            # rate_limit | server | timeout | client
        self.attempts = attempts
        super().__init__(detail)


class Throttle:
    """호출 간 최소 간격 보장."""

    def __init__(self, min_interval: float, clock=time.monotonic, sleep=time.sleep):
        self.min_interval, self.clock, self.sleep = min_interval, clock, sleep
        self._last: float | None = None

    def wait(self) -> None:
        if self._last is not None:
            gap = self.clock() - self._last
            if gap < self.min_interval:
                self.sleep(self.min_interval - gap)
        self._last = self.clock()


def call_with_retry(fn, *, max_429, backoff_429, max_transient, backoff_transient,
                    throttle: Throttle | None = None, sleep=time.sleep):
    """429: Retry-After 준수(없으면 backoff_429), 최대 max_429회 재시도.
    5xx·타임아웃: 최대 max_transient회 재시도. 그 외 4xx는 재시도 없이 실패."""
    n429 = ntr = attempts = 0
    while True:
        attempts += 1
        if throttle:
            throttle.wait()
        try:
            return fn()
        except HttpError as e:
            if e.status == 429:
                if n429 >= max_429:
                    raise RetryExhausted("rate_limit", attempts, "HTTP 429 재시도 한도 초과") from None
                delay = e.retry_after if e.retry_after is not None else backoff_429[min(n429, len(backoff_429) - 1)]
                n429 += 1
            elif 500 <= e.status < 600:
                if ntr >= max_transient:
                    raise RetryExhausted("server", attempts, f"HTTP {e.status} 재시도 한도 초과") from None
                delay = backoff_transient[min(ntr, len(backoff_transient) - 1)]
                ntr += 1
            else:
                raise RetryExhausted("client", attempts, f"HTTP {e.status}") from None
        except TimeoutError:
            if ntr >= max_transient:
                raise RetryExhausted("timeout", attempts, "타임아웃 재시도 한도 초과") from None
            delay = backoff_transient[min(ntr, len(backoff_transient) - 1)]
            ntr += 1
        sleep(delay)


def _retry_after(headers) -> float | None:
    try:
        return float(headers.get("Retry-After")) if headers and headers.get("Retry-After") else None
    except (TypeError, ValueError):
        return None


def _api_error(e) -> str:
    """오류 응답에서 오류 코드·메시지 필드만 뽑아 짧게 돌려준다(키·헤더·그 밖의 본문은 버린다)."""
    try:
        d = json.loads(e.read())
    except Exception:
        return ""
    if not isinstance(d, dict):
        return ""
    parts = [str(d[k])[:80] for k in ("errorCode", "errorMessage", "code", "title", "message") if d.get(k)]
    return " / ".join(parts)[:200]


def open_json(req: urllib.request.Request, timeout: float, urlopen=None):
    """요청 1회. HTTP 오류는 HttpError, 네트워크 오류·타임아웃은 TimeoutError로 올린다(재시도 규칙용).
    응답 본문·헤더는 오류 메시지에 담지 않는다. 성공 시 JSON을 파싱해 돌려준다(형식 오류는 ValueError)."""
    opener = urlopen or urllib.request.urlopen
    try:
        with opener(req, timeout=timeout) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as e:
        raise HttpError(e.code, retry_after=_retry_after(e.headers), api_error=_api_error(e)) from None
    except (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError):
        raise TimeoutError("네트워크 오류 또는 타임아웃") from None
    return json.loads(raw)
