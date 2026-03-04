"""
Market scanner — runs pattern detectors against a candle series and
returns a confidence-scored signal if a pattern is found.
"""
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from app.strategies.patterns.pin_bar import detect_pin_bar
from app.strategies.patterns.breakout import detect_breakout
from app.strategies.patterns.flags import detect_flag
from app.strategies.patterns.vwap_bounce import detect_vwap_bounce
from app.strategies.patterns.volume_spike import detect_volume_spike

VALID_PATTERNS = frozenset({"pin_bar", "breakout", "flag", "vwap_bounce", "volume_spike"})

# Allowed parameter keys per pattern (prevents unexpected kwarg injection)
PATTERN_PARAM_KEYS: dict[str, set[str]] = {
    "pin_bar": {"min_wick_ratio", "max_body_pct"},
    "breakout": {"lookback", "min_range_bars"},
    "flag": {"pole_bars", "flag_bars", "min_pole_gain_pct", "max_flag_retracement_pct"},
    "vwap_bounce": {"proximity_pct", "lookback"},
    "volume_spike": {"min_spike_ratio", "lookback"},
}


@dataclass
class ScanResult:
    detected: bool
    direction: str       # "bullish" | "bearish" | "none"
    confidence: float    # 0–100
    meta: dict           # pattern-specific details (ratio, pct, etc.)


def scan(
    pattern_name: str,
    candles: list[dict],
    pattern_params: dict | None = None,
) -> ScanResult:
    """
    Run a single pattern detector on the most recent candle of `candles`.

    `candles`: list of dicts with keys open/high/low/close/volume.
    Returns a ScanResult with detected=False if the pattern did not fire or there
    are insufficient candles.

    Raises ValueError for unknown pattern names or unknown pattern_params keys.
    """
    if pattern_name not in VALID_PATTERNS:
        raise ValueError(f"Unknown pattern: {pattern_name}")
    if not candles:
        return ScanResult(False, "none", 0.0, {})

    params = pattern_params or {}

    # Validate parameter keys against the allowlist
    allowed = PATTERN_PARAM_KEYS.get(pattern_name, set())
    unknown = set(params) - allowed
    if unknown:
        raise ValueError(
            f"Unknown params for '{pattern_name}': {sorted(unknown)}. "
            f"Allowed: {sorted(allowed)}"
        )

    opens = [Decimal(str(c["open"])) for c in candles]
    highs = [Decimal(str(c["high"])) for c in candles]
    lows = [Decimal(str(c["low"])) for c in candles]
    closes = [Decimal(str(c["close"])) for c in candles]
    volumes = [int(c.get("volume", 0)) for c in candles]

    try:
        if pattern_name == "pin_bar":
            r = detect_pin_bar(opens, highs, lows, closes, **params)
            if not r.detected:
                return ScanResult(False, "none", 0.0, {})
            # Confidence: wick/body ratio capped at 10× → 0-100%
            confidence = min(float(r.ratio) / 10.0 * 100, 100.0)
            return ScanResult(True, r.direction, round(confidence, 2),
                              {"wick_ratio": float(r.ratio)})

        if pattern_name == "breakout":
            r = detect_breakout(highs, lows, closes, **params)
            if not r.detected:
                return ScanResult(False, "none", 0.0, {})
            range_size = float(r.range_high - r.range_low)
            breakout_margin = abs(float(r.breakout_price) - (
                float(r.range_high) if r.direction == "bullish" else float(r.range_low)
            ))
            confidence = min(breakout_margin / (range_size or 1) * 200, 100.0)
            return ScanResult(True, r.direction, round(confidence, 2), {
                "range_high": float(r.range_high),
                "range_low": float(r.range_low),
                "breakout_price": float(r.breakout_price),
            })

        if pattern_name == "flag":
            r = detect_flag(highs, lows, closes, **params)
            if not r.detected:
                return ScanResult(False, "none", 0.0, {})
            pole_score = min(float(r.pole_gain_pct) / 10.0 * 60, 60.0)
            retrace_score = max(40.0 - float(r.flag_depth_pct) * 0.8, 0.0)
            confidence = min(pole_score + retrace_score, 100.0)
            return ScanResult(True, r.direction, round(confidence, 2), {
                "pole_gain_pct": float(r.pole_gain_pct),
                "flag_depth_pct": float(r.flag_depth_pct),
            })

        if pattern_name == "vwap_bounce":
            r = detect_vwap_bounce(highs, lows, closes, volumes, **params)
            if not r.detected:
                return ScanResult(False, "none", 0.0, {})
            # Confidence: proximity_pct is relative (e.g. 0.15 = 0.15% of VWAP)
            # Score decreases as proximity increases from 0; multiplier 200 gives full
            # discrimination across 0–0.3% range (floor at ~0.45%, well outside valid range)
            confidence = max(100.0 - float(r.touch_proximity_pct) * 200, 10.0)
            return ScanResult(True, r.direction, round(min(confidence, 100.0), 2), {
                "vwap": float(r.vwap),
                "touch_proximity_pct": float(r.touch_proximity_pct),
            })

        if pattern_name == "volume_spike":
            r = detect_volume_spike(volumes, **params)
            if not r.detected:
                return ScanResult(False, "none", 0.0, {})
            min_ratio = float(params.get("min_spike_ratio", 2.0))
            confidence = min((float(r.spike_ratio) - min_ratio) / min_ratio * 100, 100.0)
            # Direction based on candle body (close vs open of the signal candle)
            last_open = float(opens[-1])
            last_close = float(closes[-1])
            direction = "bullish" if last_close >= last_open else "bearish"
            return ScanResult(True, direction, round(max(confidence, 10.0), 2), {
                "spike_ratio": float(r.spike_ratio),
                "average_volume": float(r.average_volume),
            })

    except (IndexError, ZeroDivisionError, TypeError, InvalidOperation):
        pass

    return ScanResult(False, "none", 0.0, {})
