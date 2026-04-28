import os

from app.workers.celery_app import celery_app
from app.workers import tasks  # noqa: F401

# Celery prefork is unstable on native Windows in many setups.
# Force a safe single-process worker pool for local Windows runs.
if os.name == "nt":
    celery_app.conf.worker_pool = "solo"
    celery_app.conf.worker_concurrency = 1

__all__ = ("celery_app",)
