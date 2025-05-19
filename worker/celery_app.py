import logging
import os

from celery import Celery
from celery.schedules import crontab

from app.logging_config import setup_logging

setup_logging()
logger = logging.getLogger(__name__)

celery = Celery(
    "summary_worker",
    broker=os.getenv("REDIS_URL", "redis://redis:6379/0"),
    backend=os.getenv("REDIS_URL", "redis://redis:6379/0"),
)

# Discover tasks from the worker package so all tasks are registered
celery.autodiscover_tasks(["worker"])
logger.info("Celery configured")
celery.conf.task_serializer = "json"
celery.conf.result_serializer = "json"
celery.conf.accept_content = ["json"]
celery.conf.beat_schedule = {
    "check-calendar": {
        "task": "worker.tasks.check_calendar",
        "schedule": crontab(minute="*/30"),
    },
    "process-idle-users": {
        "task": "worker.tasks.process_idle_users",
        "schedule": crontab(minute="*/5"),
    },
}
