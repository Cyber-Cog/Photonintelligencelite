"""Resolve plant/WMS irradiance from canonical data.

After multi-file merge, weather POA is often joined onto inverter rows (device_type=inverter)
rather than living on separate plant/wms rows. Algorithms must accept either shape.
"""
from __future__ import annotations

import pandas as pd

from analytics.core.context import AnalysisContext


def extract_irradiance_frame(context: AnalysisContext) -> pd.DataFrame:
    """Return a timestamp-unique irradiance series with columns timestamp_utc, irr_val.

    Preference order:
      1. Rows tagged plant / wms with POA or GHI
      2. Any rows that carry POA or GHI (e.g. weather joined onto inverter SCADA)
    """
    irr = context.canonical.frame(columns=["timestamp_utc", "device_type", "poa_w_m2", "ghi_w_m2"])
    if irr.empty:
        return pd.DataFrame(columns=["timestamp_utc", "irr_val"])

    preferred = irr[irr["device_type"].isin(["plant", "wms"])]
    pool = preferred if not preferred.empty else irr

    series = pd.to_numeric(pool["poa_w_m2"].where(pool["poa_w_m2"].notna(), pool["ghi_w_m2"]), errors="coerce")
    out = pool.assign(irr_val=series).dropna(subset=["irr_val"])
    if out.empty:
        return pd.DataFrame(columns=["timestamp_utc", "irr_val"])

    out = out.sort_values("timestamp_utc").drop_duplicates("timestamp_utc", keep="first")
    return out[["timestamp_utc", "irr_val"]].reset_index(drop=True)
