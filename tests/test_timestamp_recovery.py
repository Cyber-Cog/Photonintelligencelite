"""Timestamp parsing + validation recovery behaviour."""
from __future__ import annotations

import pandas as pd

from analytics.preprocessing.timestamps import normalise_timestamp, parse_timestamp, parse_timestamp_series
from analytics.preprocessing.validation import PROCEED_WITH_DROPS_MIN_OK_RATIO, validate_raw_frame
from analytics.common.aliasing import score_column
from backend.app.services.excel_convert import try_promote_header_row


def test_parse_iso_and_dmy():
    assert parse_timestamp("2026-03-01 12:01:00").year == 2026
    assert normalise_timestamp("01/03/2026 12:01") == "2026-03-01 12:01:00"
    assert normalise_timestamp("01/03/2026 12:01:30") == "2026-03-01 12:01:30"


def test_parse_excel_serial():
    # 2026-03-01 ≈ Excel serial 46082 (1900 system)
    dt = parse_timestamp(46082.0)
    assert dt is not None
    assert dt.year == 2026
    assert dt.month == 3


def test_parse_series_mixed_formats():
    s = pd.Series(["2026-01-01 00:00:00", "01/01/2026 00:15", "not-a-date", None])
    parsed = parse_timestamp_series(s)
    assert int(parsed.notna().sum()) == 2
    assert int(parsed.isna().sum()) == 2


def test_invalid_datetime_blocker_with_remediation_and_samples():
    df = pd.DataFrame(
        {
            "Unnamed: 1": ["garbage"] * 20 + ["2026-01-01 00:00:00"],
            "Power": [1.0] * 21,
        }
    )
    report = validate_raw_frame(df, "Unnamed: 1", ["Unnamed: 1", "Power"], ["Power"])
    assert report.has_blockers
    issue = next(i for i in report.blockers if i.code == "invalid_datetime_format")
    assert "Unnamed: 1" in issue.message
    assert issue.sample_values
    assert "remap" in issue.remediation.lower() or "Setup" in issue.remediation
    assert report.timestamp_column == "Unnamed: 1"
    assert report.can_proceed_with_row_drops is False  # far below 80%


def test_proceed_with_drops_when_mostly_ok():
    ok = [f"2026-01-01 00:{i:02d}:00" for i in range(16)]
    bad = ["xx", "yy", "zz"]
    df = pd.DataFrame({"Timestamp": ok + bad, "Power": [1.0] * 19})
    report = validate_raw_frame(df, "Timestamp", ["Timestamp", "Power"], ["Power"])
    assert report.has_blockers  # >5% bad
    assert report.can_proceed_with_row_drops
    assert report.timestamp_parse_ok / (report.timestamp_parse_ok + report.timestamp_parse_fail) >= PROCEED_WITH_DROPS_MIN_OK_RATIO

    dropped = validate_raw_frame(
        df, "Timestamp", ["Timestamp", "Power"], ["Power"], drop_unparseable_timestamps=True
    )
    assert not dropped.has_blockers


def test_unnamed_never_auto_maps():
    c = score_column("Unnamed: 1")
    assert c.canonical_field is None
    assert c.confidence == 0.0


def test_promote_header_skips_title_row():
    rows = [
        ["INVERTER REPORT", "", ""],
        ["Date And Time", "AC Power (kW)", "Equipment ID"],
        ["2026-03-01 12:00:00", "100", "INV-01"],
    ]
    out = try_promote_header_row(rows)
    assert out[0][0] == "Date And Time"
    assert out[1][0].startswith("2026")
