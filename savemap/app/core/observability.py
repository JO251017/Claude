import logging

from app.core.config import settings


def configure_logging() -> None:
    """Render는 표준출력을 그대로 로그로 모으는데, logging.basicConfig가 어디에도
    없어서 루트 로거 설정이 uvicorn 실행 방식에 그대로 의존하고 있었다 — 포맷도
    일관되지 않고, 이 프로젝트 곳곳의 logger.warning(...)이 실제로 Render 로그에
    보이는지도 코드만 봐서는 알 수 없었다(2026-08-12 품질 점검). 시간·레벨·로거
    이름이 항상 붙는 포맷으로 통일한다. 이미 핸들러가 설정된 상태(예: 테스트에서
    여러 번 앱을 만드는 경우)면 아무 일도 안 한다 — basicConfig 기본 동작 그대로."""
    level = logging.DEBUG if settings.app_debug else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    _silence_http_client_url_logs()


def _silence_http_client_url_logs() -> None:
    """httpx는 요청마다 INFO로 "HTTP Request: POST <URL 전체>"를 남긴다. 그런데
    외부 API 중 상당수가 인증키를 쿼리 파라미터로만 받는다(공공데이터포털
    serviceKey, 기상청 serviceKey 등 — 헤더 인증을 아예 지원하지 않음). 그래서
    이 로그가 그대로 켜져 있으면 운영 로그를 볼 수 있는 사람 누구나 인증키를
    평문으로 가져갈 수 있다(2026-09-02 실제 Render 로그에서 Gemini 키가 그대로
    노출된 것을 확인).

    개별 호출부에서 키를 가리는 대신 여기서 한 번에 막는 이유: 앞으로 추가되는
    연동이 같은 실수를 반복해도 자동으로 안전한 쪽에 있게 하기 위해서다.
    WARNING 이상은 그대로 두므로 httpx가 실제로 문제를 보고할 때는 여전히
    보인다. 요청 단위 관측이 필요하면 URL을 직접 마스킹해서 남기는 미들웨어를
    따로 두는 게 맞지, 이 로거를 다시 INFO로 되돌리면 안 된다."""
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def configure_sentry() -> None:
    """SENTRY_DSN이 설정된 경우에만 초기화한다 — 미설정이면(기본값) 아무 일도 안 하고
    조용히 넘어간다. 지금까지 에러 트래킹이 전혀 없어서 장애가 나면 Render 로그를
    사람이 직접 뒤져야 했던 문제를 없애되, DSN 없이도 서비스는 그대로 동작해야
    하므로 강제 의존이 아니라 opt-in으로 둔다."""
    if not settings.sentry_dsn:
        return

    import sentry_sdk
    from sentry_sdk.integrations.fastapi import FastApiIntegration
    from sentry_sdk.integrations.logging import LoggingIntegration

    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.app_env,
        integrations=[
            FastApiIntegration(),
            # ERROR 레벨 이상 로그만 Sentry 이벤트로 보낸다 — 그 아래(info/warning)는
            # 원래대로 stdout 로그에만 남는다.
            LoggingIntegration(level=logging.INFO, event_level=logging.ERROR),
        ],
        # 성능 트레이싱은 무료 Sentry 쿼터를 빠르게 소진한다 — 지금은 에러만 잡는다.
        traces_sample_rate=0.0,
    )
