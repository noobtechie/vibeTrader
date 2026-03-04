"""VWAP bounce detector."""
from dataclasses import dataclass
from decimal import Decimal
from typing import Sequence


@dataclass
class VWAPBounceResult:
    detected: bool
    direction: str      # "bullish" (bounce up from VWAP) | "bearish" | "none"
    vwap: Decimal
    touch_proximity_pct: Decimal  # how close the low/high got to VWAP


def compute_vwap(
    highs: Sequence[Decimal],
    lows: Sequence[Decimal],
    closes: Sequence[Decimal],
    volumes: Sequence[int],
) -> Decimal:
    """Standard VWAP = sum(typical_price * volume) / sum(volume)."""
    total_vol = sum(volumes)
    if total_vol == 0:
        return Decimal("0")
    typical_prices = [(h + l + c) / 3 for h, l, c in zip(highs, lows, closes)]
    return sum(tp * v for tp, v in zip(typical_prices, volumes)) / total_vol


def detect_vwap_bounce(
    highs: Sequence[Decimal],
    lows: Sequence[Decimal],
    closes: Sequence[Decimal],
    volumes: Sequence[int],
    proximity_pct: float = 0.003,  # 0.3% of VWAP price
    lookback: int = 20,
    index: int = -1,
) -> VWAPBounceResult:
    """
    Detect a VWAP bounce on the candle at `index`.

    A bullish bounce: the low touched within `proximity_pct` of VWAP and the
    candle closed above VWAP.
    A bearish bounce: the high touched within `proximity_pct` of VWAP and the
    candle closed below VWAP.
    """
    idx = index if index >= 0 else len(closes) + index
    start = max(0, idx - lookback + 1)

    vwap = compute_vwap(
        highs[start: idx + 1],
        lows[start: idx + 1],
        closes[start: idx + 1],
        volumes[start: idx + 1],
    )
    if vwap == 0:
        return VWAPBounceResult(False, "none", Decimal("0"), Decimal("0"))

    threshold = vwap * Decimal(str(proximity_pct))
    low = lows[idx]
    high = highs[idx]
    close = closes[idx]

    low_proximity = abs(low - vwap)
    high_proximity = abs(high - vwap)

    if low_proximity <= threshold and close > vwap:
        return VWAPBounceResult(
            True, "bullish", vwap,
            (low_proximity / vwap * 100).quantize(Decimal("0.0001")),
        )
    if high_proximity <= threshold and close < vwap:
        return VWAPBounceResult(
            True, "bearish", vwap,
            (high_proximity / vwap * 100).quantize(Decimal("0.0001")),
        )

    return VWAPBounceResult(False, "none", vwap, Decimal("0"))
