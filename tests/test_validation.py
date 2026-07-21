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
