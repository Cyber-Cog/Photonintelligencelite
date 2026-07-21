"""Timezone normalization: convert plant-local timestamps to UTC for analysis.

The plant's declared timezone (from plant metadata, §7.3) is preserved in job metadata for
report display, but every analysis timestamp is converted to UTC so interval detection,
resampling, and cross-equipment joins are unambiguous. See docs/PRD.md §3, §7.6.
"""
from __future__ import annotations

import pandas as pd


def normalize_timezone(df: pd.DataFrame, plant_timezone: str, timestamp_column: str = "timestamp_utc") -> pd.DataFrame:
    df = df.copy()
    ts = df[timestamp_column]
    if pd.api.types.is_datetime64_any_dtype(ts) and getattr(ts.dt, "tz", None) is not None:
        df[timestamp_column] = ts.dt.tz_convert("UTC")
        return df

    localized = ts.dt.tz_localize(plant_timezone, ambiguous="infer", nonexistent="shift_forward")
    df[timestamp_column] = localized.dt.tz_convert("UTC")
    return df
