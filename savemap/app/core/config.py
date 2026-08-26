from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "local"
    app_debug: bool = True

    supabase_db_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/savemap"
    supabase_jwt_secret: str = "change-me"

    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"

    kakao_rest_api_key: str = ""
    data_go_kr_key: str = ""
    tour_api_key: str = ""
    opinet_api_key: str = ""
    gemini_api_key: str = ""
    # 행정안전부 착한가격업소 odcloud 오픈API 요청 URL (활용신청 승인 후 포털에서 복사).
    # 파일데이터 회차마다 UDDI가 바뀌어서 코드에 박지 않고 환경변수로 받는다.
    good_price_api_url: str = ""
    # 한국소비자원 참가격 외식비(시도별 평균가) 오픈API 요청 URL. 착한가격업소와 같은
    # 이유로 코드에 박지 않고 환경변수로 받는다 — 미설정이면 정부 통계 기준 없이
    # 기존 동작(실측 → AI 추정)을 그대로 유지한다.
    dine_out_price_api_url: str = ""
    # 전국지역화폐가맹점표준데이터(data.go.kr/data/15100062) 오픈API 요청 URL. 지자체가
    # 매달 갱신하는 지역화폐/지역사랑상품권 가맹점 명단 — 같은 이유로 코드에 박지 않고
    # 환경변수로 받는다. 미설정이면 기존 매장의 결제수단 검증 배지를 그대로 비워둔다
    # (자기신고만 남고 검증은 안 붙는다, 지어내지 않기).
    local_currency_api_url: str = ""

    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_service_key: str = ""
    supabase_storage_bucket: str = "reports"

    admin_sync_key: str = ""

    # 지금까지 CORS 미들웨어가 아예 없었다 — 지금은 프론트가 이 API와 같은 도메인에서
    # 서빙돼서 안 드러났지만(app/main.py가 frontend/를 "/"에 마운트), 모바일 앱
    # webview나 다른 도메인 프론트가 이 API를 부르면 브라우저가 바로 막는다.
    # 콤마로 구분된 허용 origin 목록(예: "https://app.example.com,https://m.example.com") —
    # 비워두면(기본값) CORS 미들웨어 자체를 안 붙여서 지금 동작 그대로 유지한다.
    cors_allowed_origins: str = ""

    # 지금까지 에러 트래킹(Sentry 등)이 전혀 없어서, 장애가 나면 Render 로그를
    # 사람이 직접 뒤져야 했다. DSN을 넣어야만 켜지는 opt-in — 지금 당장은 값이
    # 없으니(기본값) 아무 일도 안 하고, 나중에 DSN만 넣으면 바로 활성화된다.
    sentry_dsn: str = ""

    search_default_radius_km: float = 3.0
    search_max_radius_km: float = 10.0
    # /search 응답에 실제로 담아 보낼 최대 매장 수 — 이게 없으면 착한가격업소 같은
    # 소스가 밀집된 도심 반경에서 결과가 수백~수천 건까지 튀면서, 결과마다 도는
    # trust_map/discover_count 등 추가 쿼리까지 같이 불어나 느려지는 실제 문제가
    # 있었다(2026-08-12, 전국 착한가격업소 12,137건 적재 이후 확인).
    search_max_results: int = 60
    # DB에서 한 번에 끌어올 원본 offer×place 행 수 상한(정렬/중복제거 전 단계) — 이게
    # 없으면 매장 하나가 오퍼 여러 개를 가진 경우 등으로 DB 자체가 무제한으로 행을
    # 반환할 수 있다. search_max_results보다 넉넉하게 잡아서, 정렬 후 상위
    # search_max_results개를 추릴 표본이 부족해지지 않게 한다.
    search_row_fetch_limit: int = 500
    # 절약률 55% + 신뢰도 25% + 거리 20% 가중합으로 랭킹 점수를 매긴다. 예전엔 거리가
    # 전혀 안 들어가서(0.7/0.3 둘뿐), 검증 데이터가 적은 콜드스타트에선 거의 모든
    # 후보가 동점(0.15)이 돼 정렬이 "우연히" 거리순으로 남는 상태였다(2026-08-22
    # 확인). rank_distance_half_m은 거리 점수가 0.5가 되는 지점(쌍곡 감쇠) — 이
    # 값을 키우면 먼 매장도 덜 불리해진다.
    rank_savings_weight: float = 0.55
    rank_trust_weight: float = 0.25
    rank_distance_weight: float = 0.20
    rank_distance_half_m: float = 500.0

    # AI 절약 플랜(/v1/route/suggest) — 예산 입력값 검증 범위와 코스에 담을 최대
    # 스톱 수. 최대 스톱 수는 기획서 예시(무료주차→무료체험→할인카페→마감할인식당,
    # 4곳) 규모를 그대로 따른다.
    route_min_budget: float = 1000.0
    route_max_budget: float = 500_000.0
    route_max_stops: int = 4


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
