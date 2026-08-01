"""ICR mapping + hierarchy level labeling regressions."""
from __future__ import annotations

import pandas as pd

from analytics.common.aliasing import score_column
from analytics.common.mapping_levels import (
    annotate_mapping_levels,
    column_hierarchy_from_mapping,
    infer_hierarchy_level,
)
from analytics.core.context import CANONICAL_COLUMNS, ResolvedMapping
from analytics.preprocessing.standardize import standardize
from backend.app.schemas import ColumnMappingSuggestion
from backend.app.services.mapping_service import mapping_payload, suggest_mapping


def test_icr_id_never_maps_to_timestamp():
    """Regression: Setup select used to show Timestamp when icr_id option was missing;
    backend must still resolve ICR ID → icr_id, never timestamp.
    """
    for header in ("ICR ID", "ICR_ID", "icr id", "ICR", "ICR 1", "PCS Room ID"):
        c = score_column(header)
        assert c.canonical_field == "icr_id", f"{header!r} -> {c.canonical_field!r}"
        assert c.canonical_field != "timestamp"


def test_suggest_mapping_labels_icr_and_equipment_metrics():
    cols = ["Timestamp", "ICR ID", "Equipment ID", "DC Power (kW)", "DC Current"]
    sug = suggest_mapping(cols, pack_match=False)
    by = {s.column_name: s for s in sug}
    assert by["ICR ID"].canonical_field == "icr_id"
    assert by["ICR ID"].hierarchy_level == "icr"
    assert by["Equipment ID"].canonical_field == "device_id"
    assert by["DC Power (kW)"].canonical_field == "dc_power_kw"
    assert by["DC Power (kW)"].hierarchy_level == "equipment"
    assert by["DC Power (kW)"].hierarchy_level_label == "Equipment (row)"


def test_scb_companions_label_dc_current_as_scb():
    level, label = infer_hierarchy_level(
        "dc_current_a",
        companion_fields={"timestamp", "scb_id", "dc_current_a"},
    )
    assert level == "scb"
    assert label == "SCB / SMB"


def test_mapping_payload_stores_hierarchy_without_breaking_column_map():
    payload = mapping_payload(
        {
            "Timestamp": "timestamp",
            "ICR ID": "icr_id",
            "Equipment ID": "device_id",
            "DC Power (kW)": "dc_power_kw",
        },
        timestamp_col="Timestamp",
    )
    assert payload["column_to_canonical"]["ICR ID"] == "icr_id"
    assert payload["column_hierarchy_levels"]["ICR ID"] == "icr"
    assert payload["column_hierarchy_levels"]["DC Power (kW)"] == "equipment"
    assert payload["timestamp_column"] == "Timestamp"


def test_standardize_keeps_icr_id_and_backfills_from_equipment():
    raw = pd.DataFrame(
        {
            "Timestamp": pd.to_datetime(["2026-01-01 10:00:00", "2026-01-01 10:05:00"]),
            "ICR ID": ["ICR1", None],
            "Equipment ID": ["ICR1-INV-01", "ICR2-INV-03"],
            "AC Power (kW)": [100.0, 200.0],
        }
    )
    mapping = ResolvedMapping(
        column_to_canonical={
            "ICR ID": "icr_id",
            "Equipment ID": "device_id",
            "AC Power (kW)": "ac_power_kw",
        },
        confidence_by_column={},
    )
    result = standardize(raw, mapping, timestamp_column="Timestamp")
    assert "icr_id" in CANONICAL_COLUMNS
    assert list(result.columns) == CANONICAL_COLUMNS
    assert result.iloc[0]["icr_id"] == "ICR1"
    assert result.iloc[1]["icr_id"] == "ICR2"
    assert result.iloc[0]["device_type"] == "inverter"


def test_annotate_mapping_levels_on_suggestions():
    sug = [
        ColumnMappingSuggestion(
            column_name="ICR ID", canonical_field="icr_id", confidence=1.0, band="auto"
        ),
        ColumnMappingSuggestion(
            column_name="DC Power (kW)", canonical_field="dc_power_kw", confidence=1.0, band="auto"
        ),
        ColumnMappingSuggestion(
            column_name="Equipment ID", canonical_field="device_id", confidence=1.0, band="auto"
        ),
    ]
    annotate_mapping_levels(sug)
    assert sug[0].hierarchy_level == "icr"
    assert sug[1].hierarchy_level == "equipment"
    levels = column_hierarchy_from_mapping(
        {"ICR ID": "icr_id", "DC Power (kW)": "dc_power_kw", "Equipment ID": "device_id"}
    )
    assert levels["ICR ID"] == "icr"


def test_mapping_metric_without_companion_has_no_multi_badge():
    """Do not claim Multi-level when no equipment identity is mapped."""
    level, label = infer_hierarchy_level("dc_current_a", companion_fields={"timestamp", "dc_current_a"})
    assert level is None
    assert label is None
    levels = column_hierarchy_from_mapping({"Timestamp": "timestamp", "DC Current": "dc_current_a"})
    assert "DC Current" not in levels


def test_wide_header_metric_labeled_inverter_without_companion_column():
    level, label = infer_hierarchy_level(
        "dc_current_a",
        column_name="ESSP_20MW ICR1 Inverter 1 DC Current (A)",
        companion_fields={"timestamp", "dc_current_a"},
    )
    assert level == "inverter"
    assert label == "Inverter"