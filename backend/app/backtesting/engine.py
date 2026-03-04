"""Core backtest engine — iterates candles, applies a pattern detector, simulates trades."""
import math
import statistics
from dataclasses import dataclass, field, asdict
from decimal import Decimal

from app.strategies.patterns.pin_bar import detect_pin_bar
from app.strategies.patterns.breakout import detect_breakout
from app.strategies.patterns.flags import detect_flag
from app.strategies.patterns.vwap_bounce import detect_vwap_bounce
from app.strategies.patterns.volume_spike import detect_volume_spike

VALID_PATTERNS = frozenset({"pin_bar", "breakout", "flag", "vwap_bounce", "volume_spike"})

# Allowed keyword arguments per pattern (used by both engine and router for validation)
PATTERN_PARAM_KEYS: dict[str, set[str]] = {
    "pin_bar": {"min_wick_ratio", "max_body_pct"},
    "breakout": {"lookback", "min_range_bars"},
    "flag": {"pole_bars", "flag_bars", "min_pole_gain_pct", "max_flag_retracement_pct"},
    "vwap_bounce": {"proximity_pct", "lookback"},
    "volume_spike": {"min_spike_ratio", "lookback"},
}

MAX_CANDLES = 2000


@dataclass
class CandleData:
    open: float
    high: float
    low: float
    close: float
    volume: int = 0


@dataclass
class BacktestTrade:
    entry_index: int
    exit_index: int
    entry_price: float
    exit_price: float
    direction: str       # "long" | "short"
    exit_reason: str     # "stop_loss" | "take_profit" | "end_of_data"
    pnl_pct: float       # percentage return on this trade
    pnl: float           # absolute PnL (equity units)


@dataclass
class BacktestMetrics:
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    breakeven_trades: int = 0
    win_rate: float = 0.0
    total_pnl: float = 0.0
    avg_pnl: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    profit_factor: float | None = None  # None when gross_loss == 0 (all-winners or no trades)
    max_drawdown_pct: float = 0.0
    sharpe_ratio: float | None = None   # Raw mean/std of per-trade % returns (not annualised)
    final_equity: float = 0.0


def _detect_signal(
    pattern_name: str,
    opens: list,
    highs: list,
    lows: list,
    closes: list,
    volumes: list,
    params: dict,
    idx: int,
) -> tuple[bool, str]:
    """Dispatch to the appropriate pattern detector. Returns (detected, direction)."""
    if pattern_name == "pin_bar":
        r = detect_pin_bar(opens, highs, lows, closes, **params, index=idx)
        return r.detected, r.direction
    if pattern_name == "breakout":
        r = detect_breakout(highs, lows, closes, **params, breakout_index=idx)
        return r.detected, r.direction
    if pattern_name == "flag":
        r = detect_flag(highs, lows, closes, **params, index=idx)
        return r.detected, r.direction
    if pattern_name == "vwap_bounce":
        r = detect_vwap_bounce(highs, lows, closes, volumes, **params, index=idx)
        return r.detected, r.direction
    if pattern_name == "volume_spike":
        r = detect_volume_spike(volumes, **params, index=idx)
        # Volume spikes are direction-neutral; treat as bullish (long) signal
        return r.detected, "bullish" if r.detected else "none"
    raise ValueError(f"Unknown pattern: {pattern_name}")


def run_backtest(
    candles: list[CandleData],
    pattern_name: str,
    pattern_params: dict | None = None,
    stop_loss_pct: float = 2.0,
    take_profit_pct: float = 4.0,
    initial_capital: float = 10_000.0,
) -> dict:
    """
    Run a candle-by-candle backtest of a single pattern.

    Entry: close of the signal candle (float arithmetic throughout the simulation loop;
           Decimal is used only internally by the pattern detectors for precision).
    Exit: stop_loss (pessimistic priority when both hit same candle) or take_profit.
    Position size: 100% of current equity per trade (compounding, percentage-based).
    No re-entry on the same candle as an exit (deferred to the following candle).

    Returns a dict with keys: metrics, equity_curve, trades.
    """
    if pattern_name not in VALID_PATTERNS:
        raise ValueError(f"Unknown pattern: {pattern_name}")
    if len(candles) > MAX_CANDLES:
        raise ValueError(f"Too many candles: {len(candles)} > {MAX_CANDLES}")
    if not candles:
        return _empty_result(initial_capital)

    params = pattern_params or {}

    # Decimal price lists for the pattern detectors (they require Decimal internally)
    opens = [Decimal(str(c.open)) for c in candles]
    highs = [Decimal(str(c.high)) for c in candles]
    lows = [Decimal(str(c.low)) for c in candles]
    closes = [Decimal(str(c.close)) for c in candles]
    volumes = [c.volume for c in candles]

    equity = initial_capital
    trades: list[BacktestTrade] = []
    equity_curve: list[dict] = [{"index": 0, "equity": round(equity, 2)}]

    position: dict | None = None

    for i, candle in enumerate(candles):
        just_exited = False

        # ── Exit check ────────────────────────────────────────────────────────
        if position is not None:
            direction = position["direction"]
            stop = position["stop"]
            target = position["target"]
            entry_price = position["entry_price"]
            exit_price: float | None = None
            exit_reason: str | None = None

            if direction == "long":
                # Pessimistic: stop takes priority when both levels hit same candle
                if candle.low <= stop:
                    exit_price, exit_reason = stop, "stop_loss"
                elif candle.high >= target:
                    exit_price, exit_reason = target, "take_profit"
            else:  # short
                if candle.high >= stop:
                    exit_price, exit_reason = stop, "stop_loss"
                elif candle.low <= target:
                    exit_price, exit_reason = target, "take_profit"

            if exit_price is not None:
                sign = 1.0 if direction == "long" else -1.0
                pnl_pct = (exit_price - entry_price) / entry_price * sign
                pnl = equity * pnl_pct
                equity += pnl
                trades.append(BacktestTrade(
                    entry_index=position["entry_index"],
                    exit_index=i,
                    entry_price=entry_price,
                    exit_price=exit_price,
                    direction=direction,
                    exit_reason=exit_reason,
                    pnl_pct=round(pnl_pct * 100, 4),
                    pnl=round(pnl, 2),
                ))
                position = None
                just_exited = True  # Do not re-enter on the same candle

        # ── Entry check (only when flat, and not the candle we just exited on) ─
        if position is None and not just_exited:
            try:
                detected, direction = _detect_signal(
                    pattern_name, opens, highs, lows, closes, volumes, params, i
                )
            except (IndexError, ZeroDivisionError):
                # Expected when not enough prior candles; skip detection
                detected, direction = False, "none"

            if detected and direction in ("bullish", "bearish"):
                trade_dir = "long" if direction == "bullish" else "short"
                # Simulation loop uses float arithmetic (fast, sufficient precision for backtesting)
                entry_price = candle.close
                sl = stop_loss_pct / 100
                tp = take_profit_pct / 100
                if trade_dir == "long":
                    stop_lvl = entry_price * (1 - sl)
                    target_lvl = entry_price * (1 + tp)
                else:
                    stop_lvl = entry_price * (1 + sl)
                    target_lvl = entry_price * (1 - tp)
                position = {
                    "direction": trade_dir,
                    "entry_price": entry_price,
                    "stop": stop_lvl,
                    "target": target_lvl,
                    "entry_index": i,
                }

        equity_curve.append({"index": i + 1, "equity": round(equity, 2)})

    # ── Close any still-open position at end-of-data ──────────────────────────
    if position is not None:
        last = candles[-1]
        entry_price = position["entry_price"]
        exit_price = last.close
        direction = position["direction"]
        sign = 1.0 if direction == "long" else -1.0
        pnl_pct = (exit_price - entry_price) / entry_price * sign
        pnl = equity * pnl_pct
        equity += pnl
        trades.append(BacktestTrade(
            entry_index=position["entry_index"],
            exit_index=len(candles) - 1,
            entry_price=entry_price,
            exit_price=exit_price,
            direction=direction,
            exit_reason="end_of_data",
            pnl_pct=round(pnl_pct * 100, 4),
            pnl=round(pnl, 2),
        ))
        equity_curve[-1] = {"index": len(candles), "equity": round(equity, 2)}

    metrics = _compute_metrics(trades, initial_capital, equity_curve)
    return {
        "metrics": asdict(metrics),
        "equity_curve": equity_curve,
        "trades": [asdict(t) for t in trades],
    }


def _compute_metrics(
    trades: list[BacktestTrade],
    initial_capital: float,
    equity_curve: list[dict],
) -> BacktestMetrics:
    if not trades:
        return BacktestMetrics(final_equity=initial_capital)

    pnls = [t.pnl for t in trades]
    winners = [p for p in pnls if p > 0]
    losers = [p for p in pnls if p < 0]
    breakevencount = len(pnls) - len(winners) - len(losers)
    total = len(trades)

    gross_profit = sum(winners) if winners else 0.0
    gross_loss = abs(sum(losers)) if losers else 0.0
    # profit_factor: None when no losers (mathematically infinite or undefined)
    profit_factor = round(gross_profit / gross_loss, 4) if gross_loss > 0 else None

    # Max drawdown from equity curve
    peak = initial_capital
    max_dd = 0.0
    for point in equity_curve:
        eq = point["equity"]
        if eq > peak:
            peak = eq
        if peak > 0:
            dd = (peak - eq) / peak
            if dd > max_dd:
                max_dd = dd

    # Raw Sharpe analog: mean / std of per-trade % returns.
    # Not annualised — for an annualised figure, compute from time-bucketed equity returns.
    returns = [t.pnl_pct for t in trades]
    sharpe = None
    if len(returns) >= 2:
        mean_r = statistics.mean(returns)
        std_r = statistics.stdev(returns)
        if std_r > 0:
            sharpe = round(mean_r / std_r, 4)

    final_equity = equity_curve[-1]["equity"] if equity_curve else initial_capital

    return BacktestMetrics(
        total_trades=total,
        winning_trades=len(winners),
        losing_trades=len(losers),
        breakeven_trades=breakevencount,
        win_rate=round(len(winners) / total, 4),
        total_pnl=round(sum(pnls), 2),
        avg_pnl=round(sum(pnls) / total, 2),
        avg_win=round(sum(winners) / len(winners), 2) if winners else 0.0,
        avg_loss=round(sum(losers) / len(losers), 2) if losers else 0.0,
        profit_factor=profit_factor,
        max_drawdown_pct=round(max_dd * 100, 4),
        sharpe_ratio=sharpe,
        final_equity=round(final_equity, 2),
    )


def _empty_result(initial_capital: float) -> dict:
    return {
        "metrics": asdict(BacktestMetrics(final_equity=initial_capital)),
        "equity_curve": [{"index": 0, "equity": initial_capital}],
        "trades": [],
    }
