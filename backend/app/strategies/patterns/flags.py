"""Bull/bear flag pattern detector."""
from dataclasses import dataclass
from decimal import Decimal
from typing import Sequence


@dataclass
class FlagResult:
    detected: bool
    direction: str      # "bullish" | "bearish" | "none"
    pole_gain_pct: Decimal
    flag_depth_pct: Decimal


def detect_flag(
    highs: Sequence[Decimal],
    lows: Sequence[Decimal],
    closes: Sequence[Decimal],
    pole_bars: int = 5,
    flag_bars: int = 10,
    min_pole_gain_pct: float = 3.0,
    max_flag_retracement_pct: float = 50.0,
    index: int = -1,
) -> FlagResult:
    """
    Detect a bull or bear flag ending at `index`.

    A bull flag has:
    1. A strong upward pole (closes rise >= min_pole_gain_pct over pole_bars)
    2. A shallow counter-trend consolidation (flag_bars) retracing <= max_flag_retracement_pct
       of the pole.

    A bear flag is the mirror image.
    """
    idx = index if index >= 0 else len(closes) + index
    total_needed = pole_bars + flag_bars
    if idx < total_needed:
        return FlagResult(False, "none", Decimal("0"), Decimal("0"))

    pole_start = idx - total_needed
    pole_end = idx - flag_bars
    flag_end = idx

    pole_open = closes[pole_start]
    pole_close = closes[pole_end]

    if pole_open == 0:
        return FlagResult(False, "none", Decimal("0"), Decimal("0"))

    pole_gain_pct = (pole_close - pole_open) / pole_open * 100

    # Check bull flag
    if pole_gain_pct >= Decimal(str(min_pole_gain_pct)):
        pole_size = pole_close - pole_open
        # Exclude the pole's final candle (pole_end) from the flag window
        flag_low = min(lows[pole_end + 1:flag_end + 1])
        flag_retracement = (pole_close - flag_low) / pole_size * 100 if pole_size else Decimal("0")
        if flag_retracement <= Decimal(str(max_flag_retracement_pct)):
            return FlagResult(
                True, "bullish",
                pole_gain_pct.quantize(Decimal("0.01")),
                flag_retracement.quantize(Decimal("0.01")),
            )

    # Check bear flag
    if -pole_gain_pct >= Decimal(str(min_pole_gain_pct)):
        pole_size = abs(pole_close - pole_open)
        # Exclude the pole's final candle (pole_end) from the flag window
        flag_high = max(highs[pole_end + 1:flag_end + 1])
        flag_retracement = (flag_high - pole_close) / pole_size * 100 if pole_size else Decimal("0")
        if flag_retracement <= Decimal(str(max_flag_retracement_pct)):
            return FlagResult(
                True, "bearish",
                (-pole_gain_pct).quantize(Decimal("0.01")),
                flag_retracement.quantize(Decimal("0.01")),
            )

    return FlagResult(False, "none", Decimal("0"), Decimal("0"))
