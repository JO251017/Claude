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

    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_service_key: str = ""
    supabase_storage_bucket: str = "reports"

    search_default_radius_km: float = 3.0
    search_max_radius_km: float = 10.0
    rank_savings_weight: float = 0.7
    rank_trust_weight: float = 0.3


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
