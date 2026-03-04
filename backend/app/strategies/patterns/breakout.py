"""Breakout detector — price breaking above/below a consolidation range."""
from dataclasses import dataclass
from decimal import Decimal
from typing import Sequence


@dataclass
class BreakoutResult:
    detected: bool
    direction: str      # "bullish" | "bearish" | "none"
    breakout_price: Decimal
    range_high: Decimal
    range_low: Decimal


def detect_breakout(
    highs: Sequence[Decimal],
    lows: Sequence[Decimal],
    closes: Sequence[Decimal],
    lookback: int = 20,
    min_range_bars: int = 5,
    breakout_index: int = -1,
) -> BreakoutResult:
    """
    Detect a breakout on the candle at `breakout_index`.

    Consolidation range is the highest high / lowest low over the prior
    `lookback` candles (excluding the breakout candle itself).

    A breakout requires the close to exceed the range boundary and the
    range to have held for at least `min_range_bars` without a close
    outside the range.
    """
    idx = breakout_index if breakout_index >= 0 else len(closes) + breakout_index
    if idx < lookback:
        return BreakoutResult(False, "none", Decimal("0"), Decimal("0"), Decimal("0"))

    range_highs = highs[idx - lookback: idx]
    range_lows = lows[idx - lookback: idx]
    range_closes = closes[idx - lookback: idx]

    range_high = max(range_highs)
    range_low = min(range_lows)

    # Verify consolidation: the last min_range_bars must all have closed within the range
    tight_window = range_closes[-min_range_bars:]
    if any(c > range_high or c < range_low for c in tight_window):
        return BreakoutResult(False, "none", closes[idx], range_high, range_low)

    close = closes[idx]

    if close > range_high:
        return BreakoutResult(True, "bullish", close, range_high, range_low)
    if close < range_low:
        return BreakoutResult(True, "bearish", close, range_high, range_low)

    return BreakoutResult(False, "none", close, range_high, range_low)
