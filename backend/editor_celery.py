# EDITOR MODULE — Isolated module, no dependencies on other project files

from celery import Celery
from editor_config import EDITOR_REDIS_URL

# Create Celery app instance for the editor module
editor_celery_app = Celery(
    "editor_celery",
    broker=EDITOR_REDIS_URL,
    backend=EDITOR_REDIS_URL
)

# Celery configuration
editor_celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    worker_concurrency=2,
    task_routes={
        "editor.*": {"queue": "editor"}
    }
)

# Import tasks so Celery can discover and register them
import editor_worker  # noqa: F401
