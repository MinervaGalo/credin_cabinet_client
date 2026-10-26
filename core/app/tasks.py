"""Запуск конвейера в Celery. При USE_CELERY=0 вместо него работают фоновые задачи FastAPI."""

from celery import Celery

from . import config
from .services import run_pipeline

celery_app = Celery("credit", broker=config.REDIS_URL, backend=config.REDIS_URL)
celery_app.conf.task_default_queue = "credit"


@celery_app.task(name="pipeline.run", autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def run_pipeline_task(application_id: int) -> None:
    run_pipeline(application_id)


def enqueue(application_id: int, background_tasks=None) -> None:
    if config.USE_CELERY:
        run_pipeline_task.delay(application_id)
    else:
        background_tasks.add_task(run_pipeline, application_id)
