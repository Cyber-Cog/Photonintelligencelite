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


def test_merge_same_schema_smb_equipment_csvs_concat(tmp_path: Path):
    """13 SMB melted CSVs must concat — not hit DataFrame-truthiness crash or collapse rows."""
    import pandas as pd

    parts: list[Path] = []
    for i in range(1, 4):
        rows = []
        for t in ("2026-02-01 10:00:00", "2026-02-01 11:00:00"):
            for ch in range(1, 4):
                rows.append(
                    {
                        "Timestamp": t,
                        "Equipment ID": f"SMB-{i:02d}-STR-{ch:02d}",
                        "DC Current (A)": 1.0 * ch,
                        "DC Voltage (V)": 800.0,
                    }
                )
        p = tmp_path / f"part_{i}.csv"
        pd.DataFrame(rows).to_csv(p, index=False)
        parts.append(p)

    dest = tmp_path / "input.csv"
    n, names = merge_csv_files(parts, dest, tmp_path / "manifest.json")
    assert len(names) == 3
    # 3 files × 2 timestamps × 3 strings
    assert n == 18
    df = pd.read_csv(dest)
    assert "Equipment ID" in df.columns
    assert df["Equipment ID"].nunique() == 9


def test_merge_other_same_schema_without_equipment_id_still_concats(tmp_path: Path):
    """Pre-melt wide SMB CSVs classified as 'other' must concat, not ambiguous-or crash."""
    import pandas as pd

    parts: list[Path] = []
    for i in range(3):
        p = tmp_path / f"smb_{i}.csv"
        pd.DataFrame(
            {
                "Date & Time": ["2026-02-01 10:00:00", "2026-02-01 11:00:00"],
                "Voltage (V)": [800.0, 810.0],
                "I1": [1.0, 1.1],
                "I2": [2.0, 2.1],
            }
        ).to_csv(p, index=False)
        parts.append(p)

    dest = tmp_path / "input.csv"
    n, names = merge_csv_files(parts, dest)
    assert len(names) == 3
    assert n == 6  # must not collapse to 2 via timestamp-only dedupe across files
