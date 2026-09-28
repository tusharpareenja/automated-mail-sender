import os

from celery import Celery

celery_app = Celery(
    "mail_campaign",
    broker=os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/1"),
    backend=os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/2"),
    include=["app.workers.email_tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_reject_on_worker_lost=True,
    beat_schedule={
        "dispatch-running-campaigns": {
            "task": "app.workers.email_tasks.dispatch_running_campaigns",
            "schedule": 10.0,
        }
    },
)
