"""Validation stage unit tests — blockers vs warnings. See docs/PRD.md §7.6."""
from __future__ import annotations

import pandas as pd

from analytics.preprocessing.validation import validate_raw_frame


def test_empty_dataframe_is_a_blocker():
    df = pd.DataFrame(columns=["Timestamp", "Value"])
    report = validate_raw_frame(df, "Timestamp", ["Timestamp", "Value"], ["Value"])
    assert report.has_blockers
    assert report.blockers[0].code == "empty_file"


def test_missing_required_column_is_a_blocker():
    df = pd.DataFrame({"Timestamp": ["2026-01-01 00:00:00"]})
    report = validate_raw_frame(df, "Timestamp", ["Timestamp", "Power"], ["Power"])
    assert report.has_blockers
    assert report.blockers[0].code == "missing_required_columns"


def test_non_numeric_and_negative_values_are_warnings_not_blockers():
    df = pd.DataFrame(
        {
            "Timestamp": pd.date_range("2026-01-01", periods=5, freq="5min"),
            "dc_current_a": [1.0, -2.0, "bad", 3.0, 4.0],
        }
    )
    report = validate_raw_frame(df, "Timestamp", ["Timestamp", "dc_current_a"], ["dc_current_a"])
    assert not report.has_blockers
    codes = {i.code for i in report.warnings}
    assert "non_numeric_values" in codes
    assert "negative_values_where_impossible" in codes


def test_duplicate_and_unsorted_timestamps_are_warnings():
    df = pd.DataFrame(
        {
            "Timestamp": ["2026-01-01 00:10:00", "2026-01-01 00:00:00", "2026-01-01 00:00:00"],
            "dc_current_a": [1.0, 2.0, 3.0],
        }
    )
    report = validate_raw_frame(df, "Timestamp", ["Timestamp", "dc_current_a"], ["dc_current_a"])
    assert not report.has_blockers
    codes = {i.code for i in report.warnings}
    assert "duplicate_timestamps" in codes
    assert "unsorted_timestamps" in codes
    dup = next(i for i in report.warnings if i.code == "duplicate_timestamps")
    assert "Same timestamp appears more than once" in dup.message
    assert dup.sample_values
    assert any("2026-01-01 00:00:00" in s for s in dup.sample_values)
    assert "continue anyway" in dup.remediation.lower() or "Download parsed Excel" in dup.remediation


def test_shared_timestamps_across_equipment_are_not_duplicates():
    """Long-format SCADA: same clock tick on many devices is normal — do not warn."""
    df = pd.DataFrame(
        {
            "Timestamp": ["2026-01-01 08:00:00"] * 3 + ["2026-01-01 08:15:00"] * 3,
            "Equipment ID": ["INV-01", "INV-02", "PLANT-WMS-01"] * 2,
            "dc_current_a": [1.0, 2.0, 3.0, 1.1, 2.1, 3.1],
        }
    )
    report = validate_raw_frame(
        df,
        "Timestamp",
        ["Timestamp", "Equipment ID", "dc_current_a"],
        ["dc_current_a"],
        equipment_id_column="Equipment ID",
    )
    assert not report.has_blockers
    assert "duplicate_timestamps" not in {i.code for i in report.warnings}


def test_true_equipment_timestamp_duplicates_warn_with_examples():
    df = pd.DataFrame(
        {
            "Timestamp": [
                "2026-01-01 08:00:00",
                "2026-01-01 08:00:00",
                "2026-01-01 08:15:00",
            ],
            "Equipment ID": ["INV-01", "INV-01", "INV-02"],
            "dc_current_a": [1.0, 1.5, 2.0],
        }
    )
    report = validate_raw_frame(
        df,
        "Timestamp",
        ["Timestamp", "Equipment ID", "dc_current_a"],
        ["dc_current_a"],
        equipment_id_column="Equipment ID",
    )
    assert not report.has_blockers
    dup = next(i for i in report.warnings if i.code == "duplicate_timestamps")
    assert "Same time appears more than once for the same equipment" in dup.message
    assert dup.affected_rows == 1
    assert "Equipment ID" in dup.affected_columns
    assert dup.sample_values
    assert any("INV-01" in s and "08:00:00" in s for s in dup.sample_values)
    assert "Download parsed Excel" in dup.remediation
    assert "first wins" in dup.remediation.lower() or "averaged" in dup.remediation.lower()
