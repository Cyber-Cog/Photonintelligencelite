"""Standardization + alias-detection unit tests. See docs/PRD.md §7.4, §10."""
from __future__ import annotations

import pandas as pd

from analytics.common.aliasing import confidence_band, score_column
from analytics.core.context import CANONICAL_COLUMNS, ResolvedMapping
from analytics.preprocessing.standardize import standardize


def test_score_column_exact_alias_is_high_confidence():
    candidate = score_column("Timestamp")
    assert candidate.canonical_field == "timestamp"
    assert candidate.confidence == 1.0
    assert confidence_band(candidate.confidence) == "auto"


def test_score_column_fuzzy_alias_lands_in_expected_band():
    candidate = score_column("P(kW)")
    assert candidate.canonical_field == "ac_power_kw"
    assert candidate.confidence >= 0.55


def test_score_column_unknown_header_is_manual():
    candidate = score_column("Zzqx Random Header 123")
    assert candidate.canonical_field is None
    assert confidence_band(candidate.confidence) == "manual"


def test_standardize_derives_equipment_hierarchy():
    raw = pd.DataFrame(
        {
            "Timestamp": pd.to_datetime(["2026-01-01 10:00:00", "2026-01-01 10:05:00"]),
            "Equipment ID": ["INV-01-SCB-01-STR-01", "INV-01"],
            "DC Current (A)": [8.5, None],
            "AC Power (kW)": [None, 1200.0],
        }
    )
    mapping = ResolvedMapping(
        column_to_canonical={"Equipment ID": "device_id", "DC Current (A)": "dc_current_a", "AC Power (kW)": "ac_power_kw"},
        confidence_by_column={},
    )
    result = standardize(raw, mapping, timestamp_column="Timestamp")

    assert list(result.columns) == CANONICAL_COLUMNS
    string_row = result[result["device_id"] == "INV-01-SCB-01-STR-01"].iloc[0]
    assert string_row["device_type"] == "string"
    assert string_row["scb_id"] == "INV-01-SCB-01"
    assert string_row["inverter_id"] == "INV-01"

    inv_row = result[result["device_id"] == "INV-01"].iloc[0]
    assert inv_row["device_type"] == "inverter"
