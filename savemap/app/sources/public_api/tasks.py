from app.core.celery_app import celery_app


@celery_app.task(name="sources.public_api.sync_all")
def sync_all() -> dict:
    raise NotImplementedError(
        "각 공공 API 어댑터 구현 후: collect→validate→dedupe→upsert 배치 실행"
    )
