import time
from dataclasses import dataclass, field

from app.core.errors import PartnerCircuitOpenError


@dataclass
class CircuitBreaker:
    failure_threshold: int = 5
    reset_timeout_sec: float = 30.0
    _failures: int = field(default=0, init=False)
    _opened_at: float | None = field(default=None, init=False)

    def _half_open_ready(self) -> bool:
        return self._opened_at is not None and (time.monotonic() - self._opened_at) >= self.reset_timeout_sec

    def before_call(self) -> None:
        if self._opened_at is not None and not self._half_open_ready():
            raise PartnerCircuitOpenError()

    def record_success(self) -> None:
        self._failures = 0
        self._opened_at = None

    def record_failure(self) -> None:
        self._failures += 1
        if self._failures >= self.failure_threshold:
            self._opened_at = time.monotonic()
