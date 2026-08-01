"""Regression: interval normalize must keep icr_id; parquet reads tolerate missing cols."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

from analytics.core.context import CANONICAL_COLUMNS, CanonicalDataAccess
from analytics.preprocessing.interval_normalize import normalize_interval
from backend.app.services.explorer_service import list_equipment, list_signals


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


def _write_partition_without_icr(tmp_path: Path) -> Path:
    """Canonical layout matching real jobs that never stored icr_id."""
    df = pd.DataFrame(
        {
            "timestamp_utc": pd.to_datetime(
                ["2026-03-02 07:00:00", "2026-03-02 07:01:00", "2026-03-02 07:00:00"],
                utc=True,
            ),
            "device_id": ["INV-01", "INV-01", "INV-02"],
            "device_type": ["inverter", "inverter", "inverter"],
            "inverter_id": ["INV-01", "INV-01", "INV-02"],
            "ac_power_kw": [3.5, 3.4, 1.2],
            "dc_power_kw": [3.0, 3.1, 1.0],
            "dc_current_a": [8.0, 8.1, 2.0],
            "ghi_w_m2": [400.0, 410.0, 400.0],
        }
    )
    out_dir = tmp_path / "canonical"
    out_dir.mkdir()
    df.to_parquet(out_dir, engine="pyarrow", partition_cols=["device_type"], index=False)
    files = list(out_dir.rglob("*.parquet"))
    assert files
    assert "icr_id" not in pq.ParquetFile(files[0]).schema_arrow.names
    return out_dir


def test_canonical_access_tolerates_missing_icr_column(tmp_path: Path):
    """Older partitions without icr_id must not raise FieldRef errors."""
    out_dir = _write_partition_without_icr(tmp_path)
    access = CanonicalDataAccess.from_partitions(out_dir)
    loaded = access.frame(columns=CANONICAL_COLUMNS)
    assert "icr_id" in loaded.columns
    assert "ac_power_kw" in loaded.columns
    assert float(loaded["ac_power_kw"].iloc[0]) == 3.5


def test_explorer_catalog_without_icr_id(tmp_path: Path):
    """Signal Explorer equipment + signals must load when parquet has no icr_id."""
    out_dir = _write_partition_without_icr(tmp_path)
    raw = tmp_path / "missing.csv"
    eq = list_equipment(out_dir, raw, "inverter")
    sig = list_signals(out_dir, raw, "inverter")
    assert eq == ["INV-01", "INV-02"]
    ids = {s["id"] for s in sig}
    assert "ac_power_kw" in ids
    assert "dc_power_kw" in ids
    assert "dc_current_a" in ids
    assert "icr_id" not in ids
    # Must not surface meteo on inverter tab
    assert "ghi_w_m2" not in ids


def test_map_metric_leaf_only_dc_current():
    from backend.app.services.excel_parser.headers import map_metric

    assert map_metric("", "DC_CURRENT") == "DC Current (A)"
    assert map_metric("", "DC Current (A)") == "DC Current (A)"
    assert map_metric("", "DC_POWER") == "DC Power (kW)"
    assert map_metric("", "AC_ACTIVE_POWER_kW") == "AC Power (kW)"
