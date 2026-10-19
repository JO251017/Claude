"""실행 로그: 모든 줄에 run_id 포함. 키·토큰·헤더·응답 원문은 기록하지 않는다."""
import logging
import os

from .redact import redact

LOGGER_NAME = "mvp"


class _RunIdFilter(logging.Filter):
    def __init__(self, run_id: str):
        super().__init__()
        self.run_id = run_id

    def filter(self, record: logging.LogRecord) -> bool:
        record.run_id = self.run_id
        record.msg = redact(record.getMessage())
        record.args = ()
        return True


def setup_logging(run_id: str, log_dir: str | None = None, console: bool = False) -> logging.Logger:
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    for h in list(logger.handlers):
        logger.removeHandler(h)
        h.close()
    fmt = logging.Formatter("%(asctime)s [%(run_id)s] %(levelname)s %(message)s")
    handlers: list[logging.Handler] = []
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)
        handlers.append(logging.FileHandler(os.path.join(log_dir, f"run_{run_id}.log"), encoding="utf-8"))
    if console:
        handlers.append(logging.StreamHandler())
    for h in handlers:
        h.setFormatter(fmt)
        h.addFilter(_RunIdFilter(run_id))
        logger.addHandler(h)
    return logger


def get_logger() -> logging.Logger:
    return logging.getLogger(LOGGER_NAME)
