"""Column / signal detection: aliases, wide Excel headers, disconnected-string readiness."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
from openpyxl import Workbook

from analytics.common.aliasing import confidence_band, score_column
from analytics.common.complete_analysis_pack import OFFICIAL_COLUMN_TO_CANONICAL, SCADA_COLUMNS
from analytics.common.config_loader import load_aliases
from analytics.common.equipment_ids import derive_level, resolve_inverter_from_architecture
from analytics.common.prerequisites import evaluate_prerequisites
from analytics.core.context import ResolvedMapping
from analytics.preprocessing.standardize import standardize
from backend.app.services.excel_parser.orchestrator import _run_strategies
from backend.app.services.excel_parser.probe import load_sheet_matrix, probe_workbook
from backend.app.services.mapping_service import suggest_mapping


@pytest.fixture(autouse=True)
def _reload_aliases():
    load_aliases.cache_clear()
    yield
    load_aliases.cache_clear()


# ---------------------------------------------------------------------------
# Aliases → dc_current_a / scb_id
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "header",
    [
        "SMB Current",
        "SMB_Current",
        "smb current",
        "SMB Current (A)",
        "String Current",
        "String Current (A)",
        "Idc",
        "IDC",
        "DC Current (A)",
        "SCB Current",
        "Combiner Current",
        "MPPT Current",
        "i_dc",
        "I_DC",
        "input current",
    ],
)
def test_smb_and_dc_current_aliases_map_to_dc_current_a(header: str):
    c = score_column(header)
    assert c.canonical_field == "dc_current_a", f"{header!r} → {c.canonical_field}"
    assert c.confidence >= 0.90
    assert confidence_band(c.confidence) == "auto"


@pytest.mark.parametrize(
    "header",
    [
        "SMB01 Current",
        "SMB_12_Current",
        "SCB 3 Current (A)",
        "String 7 Current",
        "INV1 SMB2 Current",
        "Combiner Box 4 Idc",
    ],
)
def test_numbered_smb_current_pattern_maps(header: str):
    c = score_column(header)
    assert c.canonical_field == "dc_current_a"
    assert c.confidence >= 0.90


@pytest.mark.parametrize(
    "header",
    ["SMB ID", "SMB_ID", "smb", "Combiner Box ID", "SCB ID"],
)
def test_smb_id_aliases_map_to_scb_id(header: str):
    c = score_column(header)
    assert c.canonical_field == "scb_id"
    assert c.confidence >= 0.90


def test_exact_short_alias_i_maps_when_listed():
    """YAML lists 'i' → dc_current_a; exact match must not be blocked by len<=2 denylist."""
    c = score_column("i")
    assert c.canonical_field == "dc_current_a"
    assert c.confidence == 1.0


def test_suggest_mapping_surfaces_smb_current_with_high_confidence():
    cols = ["Timestamp", "Equipment ID", "SMB Current", "Irradiance (W/m2)"]
    suggestions = {s.column_name: s for s in suggest_mapping(cols)}
    smb = suggestions["SMB Current"]
    assert smb.canonical_field == "dc_current_a"
    assert smb.confidence == 1.0
    assert smb.band == "auto"


def test_complete_analysis_pack_columns_still_map():
    for official, canonical in OFFICIAL_COLUMN_TO_CANONICAL.items():
        c = score_column(official)
        assert c.canonical_field == canonical
        assert c.confidence == 1.0
    assert tuple(OFFICIAL_COLUMN_TO_CANONICAL.keys()) == SCADA_COLUMNS


# ---------------------------------------------------------------------------
# Equipment ID: SMB → scb device_type
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "eid,expected",
    [
        ("SMB-01", "scb"),
        ("SMB_12", "scb"),
        ("SCB-03", "scb"),
        ("INV-01-SMB-02", "scb"),
        ("INV-01-SCB-02", "scb"),
        ("INV-01", "inverter"),
        ("INV-01-SCB-01-STR-01", "string"),
        ("Combiner_05", "scb"),
    ],
)
def test_derive_level_recognizes_smb_as_scb(eid: str, expected: str):
    assert derive_level(eid) == expected


def test_architecture_resolves_standalone_smb_parent():
    arch = {"SMB-01": {"inverter_id": "INV-01", "strings_per_scb": 16}}
    assert resolve_inverter_from_architecture("SMB-01", arch) == "INV-01"
    assert resolve_inverter_from_architecture("smb-01", arch) == "INV-01"


def test_standardize_smb_current_becomes_scb_with_inverter_from_architecture():
    raw = pd.DataFrame(
        {
            "Timestamp": pd.to_datetime(["2026-03-15 10:00:00", "2026-03-15 10:15:00"]),
            "Equipment ID": ["SMB-01", "SMB-01"],
            "SMB Current": [42.5, 41.0],
            "Irradiance (W/m2)": [800.0, 810.0],
        }
    )
    mapping = ResolvedMapping(
        column_to_canonical={
            "Equipment ID": "device_id",
            "SMB Current": "dc_current_a",
            "Irradiance (W/m2)": "poa_w_m2",
        },
        confidence_by_column={},
    )
    arch = {"SMB-01": {"inverter_id": "INV-01", "strings_per_scb": 16}}
    result = standardize(raw, mapping, timestamp_column="Timestamp", architecture=arch)

    assert (result["device_type"] == "scb").all()
    assert (result["scb_id"] == "SMB-01").all()
    assert (result["inverter_id"] == "INV-01").all()
    assert result["dc_current_a"].notna().all()


def test_disconnected_string_readiness_true_with_smb_dc_current_and_arch():
    rows = evaluate_prerequisites(
        available_fields={"dc_current_a", "poa_w_m2"},
        has_architecture=True,
    )
    ds = next(r for r in rows if r["algorithm_id"] == "disconnected_strings")
    assert ds["will_run"] is True
    assert not ds["missing_fields"]


# ---------------------------------------------------------------------------
# Wide Excel: header completeness (probe must not drop columns)
# ---------------------------------------------------------------------------

def test_wide_excel_preserves_all_headers_after_probe(tmp_path: Path):
    """663-style width: every header must survive load + tidy path."""
    n_smb = 120
    headers = ["Timestamp", "Equipment ID"] + [f"SMB{i:03d} Current" for i in range(1, n_smb + 1)]
    # Long/tidy: one equipment col + one current col is more realistic, but this
    # fixture stresses column-count preservation for a wide SMB metric sheet.
    headers_wide = ["Timestamp"] + [f"SMB{i:03d}_Current" for i in range(1, n_smb + 1)]

    wb = Workbook()
    ws = wb.active
    ws.title = "SCADA"
    ws.append(headers_wide)
    ws.append(["2026-03-15 10:00:00"] + [10.0 + (i % 7) for i in range(n_smb)])
    ws.append(["2026-03-15 10:15:00"] + [11.0 + (i % 5) for i in range(n_smb)])
    xlsx = tmp_path / "wide_smb.xlsx"
    wb.save(xlsx)

    probes = probe_workbook(xlsx, sample_rows=30)
    assert probes
    assert probes[0].n_cols >= n_smb + 1

    name, matrix = load_sheet_matrix(xlsx)
    assert name == "SCADA"
    assert len(matrix[0]) >= n_smb + 1
    assert matrix[0][0] == "Timestamp"
    assert matrix[0][-1] == f"SMB{n_smb:03d}_Current"
    assert all(h for h in matrix[0]), "no blank headers in middle of declared width"

    result = _run_strategies(matrix, sheet_name=name)
    assert result is not None
    # Must preserve SMB columns (tidy), not collapse to a handful of INV tidy fields
    assert len(result.rows[0]) >= n_smb
    assert any("SMB" in str(c) for c in result.rows[0])


def test_tidy_smb_long_csv_maps_and_ready(tmp_path: Path):
    csv_path = tmp_path / "smb_long.csv"
    pd.DataFrame(
        {
            "Timestamp": ["2026-03-15 10:00:00", "2026-03-15 10:15:00"],
            "Equipment ID": ["SMB-01", "SMB-02"],
            "SMB Current": [40.0, 38.5],
            "Irradiance (W/m2)": [750.0, 760.0],
        }
    ).to_csv(csv_path, index=False)

    cols = list(pd.read_csv(csv_path, nrows=0).columns)
    suggestions = suggest_mapping(cols)
    by_name = {s.column_name: s for s in suggestions}
    assert by_name["SMB Current"].canonical_field == "dc_current_a"
    assert by_name["Timestamp"].canonical_field == "timestamp"
    assert by_name["Equipment ID"].canonical_field == "device_id"
