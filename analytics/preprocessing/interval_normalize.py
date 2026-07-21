"""Sampling interval detection and normalization.

Detection logic is ported from PIC's ds_detection._detect_resolution_minutes (median of
small positive consecutive gaps), generalized to run per-device and then reconciled across
devices so a single consistent interval is used for every downstream PR/CUF/loss calculation.
See docs/PRD.md §7.6 ("Sampling interval normalization").
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from analytics.preprocessing.standardize import NUMERIC_CANONICAL_FIELDS

IRREGULAR_SPREAD_RATIO = 3.0
"""If max/min per-device dominant interval exceeds this, flag as a blocking irregularity."""


@dataclass
class IntervalNormalizationResult:
    detected_interval_minutes: float
    resampled: bool
    is_irregular: bool
    per_device_intervals_minutes: dict[str, float] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


def _dominant_interval_minutes(ts: pd.Series) -> float:
    ts_sorted = ts.drop_duplicates().sort_values()
    if len(ts_sorted) < 2:
        return float("nan")
    diffs_min = ts_sorted.diff().dropna().dt.total_seconds() / 60.0
    valid = diffs_min[(diffs_min > 0) & (diffs_min <= 60)]
    return float(valid.median()) if not valid.empty else float("nan")


def detect_dominant_interval_minutes(df: pd.DataFrame, timestamp_column: str = "timestamp_utc") -> tuple[float, dict[str, float]]:
    per_device: dict[str, float] = {}
    for device_id, group in df.groupby("device_id", sort=False):
        interval = _dominant_interval_minutes(group[timestamp_column])
        if np.isfinite(interval):
            per_device[str(device_id)] = interval

    if not per_device:
        return 1.0, per_device

    weights = df.groupby("device_id", sort=False).size()
    weighted = [(v, weights.get(k, 1)) for k, v in per_device.items()]
    total_weight = sum(w for _, w in weighted)
    dominant = sum(v * w for v, w in weighted) / total_weight if total_weight else np.median(list(per_device.values()))
    return round(float(dominant), 4), per_device


def normalize_interval(
    df: pd.DataFrame,
    timestamp_column: str = "timestamp_utc",
    target_interval_minutes: float | None = None,
) -> tuple[pd.DataFrame, IntervalNormalizationResult]:
    dominant, per_device = detect_dominant_interval_minutes(df, timestamp_column)
    target = target_interval_minutes or dominant

    is_irregular = False
    notes: list[str] = []
    if per_device:
        spread = max(per_device.values()) / max(min(per_device.values()), 1e-6)
        if spread > IRREGULAR_SPREAD_RATIO:
            is_irregular = True
            notes.append(
                f"Detected sampling intervals ranging from {min(per_device.values()):.1f} to "
                f"{max(per_device.values()):.1f} minutes across equipment — this dataset mixes "
                "resolutions and results should be reviewed carefully."
            )

    resample_rule = f"{max(round(target), 1)}min"
    numeric_cols = [c for c in NUMERIC_CANONICAL_FIELDS if c in df.columns]
    id_cols = [c for c in ("device_id", "device_type", "inverter_id", "scb_id", "string_id") if c in df.columns]

    resampled_parts: list[pd.DataFrame] = []
    for device_id, group in df.groupby("device_id", sort=False):
        g = group.set_index(timestamp_column).sort_index()
        resampled = g[numeric_cols].resample(resample_rule).mean()
        for col in id_cols:
            resampled[col] = g[col].iloc[0] if len(g) else None
        resampled = resampled.reset_index()
        resampled_parts.append(resampled)

    out = pd.concat(resampled_parts, ignore_index=True) if resampled_parts else df.copy()
    out = out.dropna(subset=numeric_cols, how="all")

    result = IntervalNormalizationResult(
        detected_interval_minutes=dominant,
        resampled=True,
        is_irregular=is_irregular,
        per_device_intervals_minutes=per_device,
        notes=notes,
    )
    return out.reset_index(drop=True), result
