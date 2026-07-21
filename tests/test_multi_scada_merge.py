"""Tests for multi-file SCADA merge + standardization (user demo CSV shapes)."""
from __future__ import annotations

from pathlib import Path

import pytest

from analytics.common.aliasing import score_column
from analytics.core.context import ResolvedMapping
from analytics.preprocessing.standardize import standardize
from backend.app.services.merge_uploads import merge_csv_files

USER_FILES = [
    Path(r"C:\Users\ayush.r\Downloads\Weather_1min.csv"),
    Path(r"C:\Users\ayush.r\Downloads\Inverter_SCADA_1min.csv"),
    Path(r"C:\Users\ayush.r\Downloads\Plant_SCADA_1min.csv"),
]


@pytest.mark.skipif(not all(p.exists() for p in USER_FILES), reason="User demo CSVs not on disk")
def test_merge_joins_weather_onto_inverter_rows(tmp_path):
    dest = tmp_path / "merged.csv"
    n, names = merge_csv_files(USER_FILES, dest)
    assert n > 0
    assert len(names) == 3
    import pandas as pd

    df = pd.read_csv(dest, nrows=20)
    assert "Inverter" in df.columns
    assert "POA_Wm2" in df.columns
    assert "ACPower_MW" in df.columns
    # After join, inverter rows should have meteo filled
    inv_rows = df[df["Inverter"].notna()]
    assert inv_rows["POA_Wm2"].notna().any()


def test_pr_column_not_auto_mapped_to_power():
    c = score_column("PR")
    assert c.canonical_field is None


def test_acpower_mw_maps_with_confirm():
    c = score_column("ACPower_MW")
    assert c.canonical_field == "ac_power_kw"
    assert c.confidence >= 0.6


def test_duplicate_canonical_mapping_does_not_crash():
    import pandas as pd

    raw = pd.DataFrame(
        {
            "Timestamp": ["2026-06-01 10:00:00", "2026-06-01 10:01:00"],
            "Inverter": ["INV-1", "INV-1"],
            "ACPower_MW": [1.0, 1.1],
            "PlantAC_MW": [4.0, 4.2],
        }
    )
    mapping = ResolvedMapping(
        column_to_canonical={
            "Inverter": "inverter_id",
            "ACPower_MW": "ac_power_kw",
            "PlantAC_MW": "ac_power_kw",
        },
        confidence_by_column={},
    )
    out = standardize(raw, mapping, "Timestamp")
    assert len(out) == 2
    # Inverter row prefers ACPower_MW (1000 kW) over plant total
    assert out["ac_power_kw"].iloc[0] == pytest.approx(1000.0)
