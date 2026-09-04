from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "savemap",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=[
        "app.sources.public_api.tasks",
        "app.sources.partner_api.tasks",
    ],
)

celery_app.conf.beat_schedule = {
    "public-api-monthly-sync": {
        "task": "sources.public_api.sync_all",
        "schedule": 60 * 60 * 24 * 30,
    },
    "partner-api-weekly-sync": {
        "task": "sources.partner_api.sync_all",
        "schedule": 60 * 60 * 24 * 7,
    },
}
celery_app.conf.timezone = "Asia/Seoul"
