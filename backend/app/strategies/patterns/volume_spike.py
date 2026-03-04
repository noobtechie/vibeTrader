"""Volume spike detector."""
from dataclasses import dataclass
from decimal import Decimal
from typing import Sequence


@dataclass
class VolumeSpikeResult:
    detected: bool
    spike_ratio: Decimal    # volume[index] / average_volume
    average_volume: Decimal
    candle_index: int


def detect_volume_spike(
    volumes: Sequence[int],
    min_spike_ratio: float = 2.0,
    lookback: int = 20,
    index: int = -1,
) -> VolumeSpikeResult:
    """
    Detect a volume spike at `index`.

    A spike is detected when volume[index] >= min_spike_ratio × average(volumes[lookback]).
    """
    idx = index if index >= 0 else len(volumes) + index
    if idx < 1:
        return VolumeSpikeResult(False, Decimal("0"), Decimal("0"), idx)

    start = max(0, idx - lookback)
    prior_vols = volumes[start:idx]
    if not prior_vols or sum(prior_vols) == 0:
        return VolumeSpikeResult(False, Decimal("0"), Decimal("0"), idx)

    avg_vol = Decimal(str(sum(prior_vols))) / len(prior_vols)
    current_vol = Decimal(str(volumes[idx]))
    ratio = current_vol / avg_vol if avg_vol else Decimal("0")

    if ratio >= Decimal(str(min_spike_ratio)):
        return VolumeSpikeResult(True, ratio.quantize(Decimal("0.01")), avg_vol, idx)
    return VolumeSpikeResult(False, ratio.quantize(Decimal("0.01")), avg_vol, idx)
