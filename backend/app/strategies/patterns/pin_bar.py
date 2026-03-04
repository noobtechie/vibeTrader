"""Pin bar (hammer / shooting star) detector."""
from dataclasses import dataclass
from decimal import Decimal
from typing import Sequence


@dataclass
class PinBarResult:
    detected: bool
    direction: str  # "bullish" | "bearish" | "none"
    ratio: Decimal  # wick-to-body ratio (higher = stronger signal)
    candle_index: int


def detect_pin_bar(
    opens: Sequence[Decimal],
    highs: Sequence[Decimal],
    lows: Sequence[Decimal],
    closes: Sequence[Decimal],
    min_wick_ratio: float = 2.0,
    max_body_pct: float = 0.35,
    index: int = -1,
) -> PinBarResult:
    """
    Detect a pin bar at `index` (default: last candle).

    A pin bar has:
    - A small body (≤ max_body_pct of total candle range)
    - A long wick (≥ min_wick_ratio × body size) on one side
    - A small opposing wick

    Returns direction="bullish" for a hammer (long lower wick),
    "bearish" for a shooting star (long upper wick).
    """
    idx = index if index >= 0 else len(opens) + index
    o, h, l, c = opens[idx], highs[idx], lows[idx], closes[idx]

    candle_range = h - l
    if candle_range == 0:
        return PinBarResult(False, "none", Decimal("0"), idx)

    body = abs(c - o)
    body_pct = body / candle_range

    upper_wick = h - max(o, c)
    lower_wick = min(o, c) - l

    if body == 0:
        return PinBarResult(False, "none", Decimal("0"), idx)

    upper_ratio = upper_wick / body
    lower_ratio = lower_wick / body

    # Small body relative to candle range
    if body_pct > Decimal(str(max_body_pct)):
        return PinBarResult(False, "none", Decimal("0"), idx)

    min_ratio = Decimal(str(min_wick_ratio))

    # Dominant wick must be at least min_ratio × body; opposing wick must not exceed the dominant wick
    if lower_ratio >= min_ratio and upper_wick <= lower_wick:
        return PinBarResult(True, "bullish", lower_ratio, idx)
    if upper_ratio >= min_ratio and lower_wick <= upper_wick:
        return PinBarResult(True, "bearish", upper_ratio, idx)

    return PinBarResult(False, "none", Decimal("0"), idx)
