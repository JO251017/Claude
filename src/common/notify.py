"""알림 인터페이스. 콘솔·파일만 구현, 카카오톡·이메일은 스텁."""
import os
from abc import ABC, abstractmethod

from .redact import redact


class Notifier(ABC):
    @abstractmethod
    def notify(self, message: str, level: str = "info", run_id: str | None = None) -> None: ...


def _line(message: str, level: str, run_id: str | None) -> str:
    return f"[{run_id or '-'}] [{level}] {redact(message)}"


class ConsoleNotifier(Notifier):
    def notify(self, message, level="info", run_id=None):
        print(_line(message, level, run_id))


class FileNotifier(Notifier):
    def __init__(self, path: str):
        self.path = path
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)

    def notify(self, message, level="info", run_id=None):
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(_line(message, level, run_id) + "\n")


class KakaoTalkNotifier(Notifier):
    def notify(self, message, level="info", run_id=None):
        raise NotImplementedError("카카오톡 알림은 MVP 범위 밖(스텁)")


class EmailNotifier(Notifier):
    def notify(self, message, level="info", run_id=None):
        raise NotImplementedError("이메일 알림은 MVP 범위 밖(스텁)")


class MultiNotifier(Notifier):
    def __init__(self, *notifiers: Notifier):
        self.notifiers = notifiers

    def notify(self, message, level="info", run_id=None):
        for n in self.notifiers:
            n.notify(message, level, run_id)
