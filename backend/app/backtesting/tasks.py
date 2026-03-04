"""Celery tasks for async backtest execution."""
from app.celery_app import celery_app
from app.backtesting.engine import CandleData, run_backtest, VALID_PATTERNS


@celery_app.task(name="app.backtesting.tasks.run_backtest_task", bind=True)
def run_backtest_task(self, candles_raw: list[dict], config: dict) -> dict:
    """
    Run a backtest asynchronously via Celery.

    candles_raw: list of dicts with open/high/low/close/volume keys.
    config: dict with pattern_name, pattern_params, stop_loss_pct, take_profit_pct, initial_capital.
    Returns the backtest output dict.
    """
    candles = [CandleData(**c) for c in candles_raw]
    return run_backtest(
        candles=candles,
        pattern_name=config["pattern_name"],
        pattern_params=config.get("pattern_params", {}),
        stop_loss_pct=config.get("stop_loss_pct", 2.0),
        take_profit_pct=config.get("take_profit_pct", 4.0),
        initial_capital=config.get("initial_capital", 10_000.0),
    )
