from app.core.celery_app import celery_app


@celery_app.task(name="sources.partner_api.sync_all")
def sync_all() -> dict:
    raise NotImplementedError(
        "파트너 API 클라이언트 구현 후: OAuth2→RateLimit→서킷브레이커→파생지표 upsert 배치"
    )
