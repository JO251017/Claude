from unittest.mock import patch

from app.core.config import settings
from app.core.observability import configure_logging, configure_sentry


def test_configure_logging_does_not_raise():
    # basicConfig가 여러 번 불려도(테스트가 매번 create_app()을 다시 부르는 경우 등)
    # 에러 없이 넘어가야 한다.
    configure_logging()
    configure_logging()


def test_configure_sentry_noop_when_dsn_not_set(monkeypatch):
    monkeypatch.setattr(settings, "sentry_dsn", "")
    with patch("sentry_sdk.init") as mock_init:
        configure_sentry()
    mock_init.assert_not_called()


def test_configure_sentry_initializes_when_dsn_set(monkeypatch):
    monkeypatch.setattr(settings, "sentry_dsn", "https://fake@sentry.example.com/1")
    monkeypatch.setattr(settings, "app_env", "production")
    with patch("sentry_sdk.init") as mock_init:
        configure_sentry()
    mock_init.assert_called_once()
    _, kwargs = mock_init.call_args
    assert kwargs["dsn"] == "https://fake@sentry.example.com/1"
    assert kwargs["environment"] == "production"
    assert kwargs["traces_sample_rate"] == 0.0


def test_create_app_calls_both_configure_functions():
    from app.main import create_app

    with patch("app.main.configure_logging") as mock_logging, patch(
        "app.main.configure_sentry"
    ) as mock_sentry:
        create_app()
    mock_logging.assert_called_once()
    mock_sentry.assert_called_once()
