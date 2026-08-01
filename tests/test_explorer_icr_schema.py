"""Regression: interval normalize must keep icr_id; parquet reads tolerate missing cols."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

from analytics.core.context import CANONICAL_COLUMNS, CanonicalDataAccess
from analytics.preprocessing.interval_normalize import normalize_interval


def test_normalize_interval_preserves_icr_id():
    ts = pd.date_range("2026-03-02 07:00", periods=4, freq="1min", tz="UTC")
    df = pd.DataFrame(
        {
            "timestamp_utc": list(ts) + list(ts),
            "device_id": ["ICR1-INV-01"] * 4 + ["ICR1-INV-02"] * 4,
            "device_type": ["inverter"] * 8,
            "inverter_id": ["ICR1-INV-01"] * 4 + ["ICR1-INV-02"] * 4,
            "scb_id": pd.NA,
            "string_id": pd.NA,
            "icr_id": ["ICR1"] * 8,
            "ac_power_kw": [1.0, 2.0, 3.0, 4.0, 1.5, 2.5, 3.5, 4.5],
            "dc_power_kw": [1.1, 2.1, 3.1, 4.1, 1.6, 2.6, 3.6, 4.6],
            "dc_current_a": pd.NA,
        }
    )
    out, _ = normalize_interval(df)
    assert "icr_id" in out.columns
    assert set(out["icr_id"].dropna().astype(str)) == {"ICR1"}


def test_canonical_access_tolerates_missing_icr_column(tmp_path: Path):
    """Older partitions without icr_id must not raise FieldRef errors."""
    df = pd.DataFrame(
        {
            "timestamp_utc": pd.to_datetime(["2026-03-02 07:00:00"], utc=True),
            "device_id": ["ICR1-INV-01"],
            "device_type": ["inverter"],
            "inverter_id": ["ICR1-INV-01"],
            "ac_power_kw": [3.5],
            "dc_power_kw": [3.0],
        }
    )
    out_dir = tmp_path / "canonical"
    out_dir.mkdir()
    df.to_parquet(out_dir, engine="pyarrow", partition_cols=["device_type"], index=False)
    files = list(out_dir.rglob("*.parquet"))
    assert files
    assert "icr_id" not in pq.ParquetFile(files[0]).schema_arrow.names

    access = CanonicalDataAccess.from_partitions(out_dir)
    loaded = access.frame(columns=CANONICAL_COLUMNS)
    assert "icr_id" in loaded.columns
    assert "ac_power_kw" in loaded.columns
    assert float(loaded["ac_power_kw"].iloc[0]) == 3.5


def test_map_metric_leaf_only_dc_current():
    from backend.app.services.excel_parser.headers import map_metric

    assert map_metric("", "DC_CURRENT") == "DC Current (A)"
    assert map_metric("", "DC Current (A)") == "DC Current (A)"
    assert map_metric("", "DC_POWER") == "DC Power (kW)"
    assert map_metric("", "AC_ACTIVE_POWER_kW") == "AC Power (kW)"
