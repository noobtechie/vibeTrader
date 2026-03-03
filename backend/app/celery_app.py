from celery import Celery
from app.config import settings

celery_app = Celery(
    "trading",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=[
        "app.backtesting.tasks",
        "app.automation.tasks",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    # Route tasks to specific queues
    task_routes={
        "app.backtesting.tasks.*": {"queue": "backtesting"},
        "app.automation.tasks.scan_strategies": {"queue": "scanning"},
        "app.automation.tasks.execute_signal": {"queue": "automation"},
    },
    # Periodic tasks (beat)
    beat_schedule={
        "scan-strategies-every-minute": {
            "task": "app.automation.tasks.scan_strategies",
            "schedule": 60.0,  # Every 60 seconds
        },
    },
)
