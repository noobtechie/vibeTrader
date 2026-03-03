from app.celery_app import celery_app


@celery_app.task(name="app.automation.tasks.scan_strategies", bind=True)
def scan_strategies(self):
    """Periodic task: scan watchlists against active strategy rules."""
    # Implemented in Phase 6
    pass


@celery_app.task(name="app.automation.tasks.execute_signal", bind=True)
def execute_signal(self, signal_id: str, user_id: str):
    """Execute a confirmed trade signal."""
    # Implemented in Phase 6
    pass
