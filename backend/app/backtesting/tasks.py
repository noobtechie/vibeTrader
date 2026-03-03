from app.celery_app import celery_app


@celery_app.task(name="app.backtesting.tasks.run_backtest", bind=True)
def run_backtest(self, backtest_id: str, user_id: str, strategy_config: dict):
    """Run a backtest for a strategy. Implemented in Phase 5."""
    pass
