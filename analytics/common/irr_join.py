"""Join plant/WMS irradiance onto inverter timestamps when clocks differ slightly.

Ported (logic only) from PIC's backend/engine/irr_join.py. Raw exports often use the same
nominal cadence but different offsets (:00 vs :02); exact timestamp equality drops most
rows. This uses `merge_asof` with a tolerance window instead.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

IRR_ASOF_TOLERANCE_MIN = 12.0


def merge_irradiance_onto(
    df_left: pd.DataFrame,
    irr_series: pd.DataFrame,
    *,
    left_ts_col: str = "timestamp_utc",
    irr_ts_col: str = "timestamp_utc",
    irr_value_col: str = "irr_val",
    out_col: str = "irradiance",
    tolerance_min: float = IRR_ASOF_TOLERANCE_MIN,
) -> pd.DataFrame:
    if df_left.empty:
        return df_left

    left = df_left.copy()
    left["_idx"] = np.arange(len(left))
    left["_ts"] = pd.to_datetime(left[left_ts_col], utc=True).dt.tz_localize(None)

    if irr_series is None or irr_series.empty:
        left[out_col] = np.nan
        return left.drop(columns=["_idx", "_ts"])

    right = irr_series[[irr_ts_col, irr_value_col]].copy()
    right["_ts"] = pd.to_datetime(right[irr_ts_col], utc=True).dt.tz_localize(None)
    right = right.sort_values("_ts").drop_duplicates("_ts", keep="first")

    merged = pd.merge_asof(
        left.sort_values("_ts"),
        right[["_ts", irr_value_col]],
        on="_ts",
        direction="nearest",
        tolerance=pd.Timedelta(minutes=tolerance_min),
    )
    merged = merged.sort_values("_idx").rename(columns={irr_value_col: out_col})
    return merged.drop(columns=["_idx", "_ts"]).reset_index(drop=True)
