"""Wide multi-header inverter Excel → long/tidy CSV reshape."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from backend.app.services.excel_convert import convert_excel_to_csv, try_reshape_wide_inverter_report

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "wide_inverter_report.xlsx"


def test_try_reshape_wide_inverter_report_from_matrix():
    rows = [
        ["INVERTER REPORT"] + [""] * 12,
        [""] * 13,
        ["", "INVERTER 1", "", "", "", "", "", "", "", "", "", "", "INVERTER 2"],
        ["", "DC INPUT", "", "AC OUTPUT VOLTAGE (V)", "", "", "AC OUTPUT", "OUTPUT", "INVERTER", "", "", "", "DC INPUT"],
        [
            "Date And Time",
            "VOLTAGE (V)",
            "CURRENT (A)",
            "R-Y",
            "Y-B",
            "B-R",
            "POWER (KW)",
            "FREQUENCY (Hz)",
            "Temp (deg C)",
            "IGBT1 Temp (deg C)",
            "IGBT2 Temp (deg C)",
            "Efficiency",
            "VOLTAGE (V)",
        ],
        ["2026-03-01 12:01:00", "650", "10.5", "415", "416", "414", "120.5", "50", "57", "0", "0", "96.5", "640"],
        ["2026-03-01 12:02:00", "652", "11.0", "416", "417", "415", "125.0", "50", "57.5", "0", "0", "96.8", "641"],
    ]
    # Pad INV-2 metrics on data rows for a minimal second block (only voltage mapped from col 12)
    out = try_reshape_wide_inverter_report(rows)
    assert out is not None
    header, *data = out
    assert header[0] == "Timestamp"
    assert "Equipment ID" in header
    assert "AC Power (kW)" in header
    assert "DC Voltage (V)" in header
    assert "DC Current (A)" in header
    devices = {row[header.index("Equipment ID")] for row in data}
    assert "INV-01" in devices
    # INV-02 only has voltage in this minimal matrix — still emitted
    assert "INV-02" in devices
    inv1 = next(r for r in data if r[header.index("Equipment ID")] == "INV-01")
    assert inv1[header.index("AC Power (kW)")] == "120.5"
    assert inv1[header.index("DC Voltage (V)")] == "650"


def test_convert_wide_inverter_fixture_xlsx(tmp_path: Path):
    assert FIXTURE.exists(), f"Missing fixture {FIXTURE}"
    csv_path = tmp_path / "out.csv"
    n = convert_excel_to_csv(FIXTURE, csv_path, max_decompressed_bytes=5_000_000, max_rows=100_000)
    assert n == 6  # 3 timestamps × 2 inverters
    df = pd.read_csv(csv_path)
    assert list(df.columns)[:2] == ["Timestamp", "Equipment ID"]
    assert set(df["Equipment ID"]) == {"INV-01", "INV-02"}
    assert "AC Power (kW)" in df.columns
    assert "DC Voltage (V)" in df.columns
    assert "DC Current (A)" in df.columns
    assert "DC Power (kW)" in df.columns  # derived from V×I
    assert "Ambient Temp (C)" in df.columns
    # Frequency / phase voltages must not appear as columns
    assert not any("FREQUENCY" in c.upper() for c in df.columns)
    assert not any(c in df.columns for c in ("R-Y", "Y-B", "B-R"))
    row = df[(df["Equipment ID"] == "INV-01") & (df["Timestamp"] == "2026-03-01 12:01:00")].iloc[0]
    assert float(row["AC Power (kW)"]) == 120.5
    assert float(row["DC Voltage (V)"]) == 650.0
    assert float(row["DC Current (A)"]) == 200.0
    assert abs(float(row["DC Power (kW)"]) - (650.0 * 200.0 / 1000.0)) < 1e-6


def test_title_row_excel_promotes_date_and_time(tmp_path: Path):
    """Title banner must not become the CSV header (Unnamed: N failure mode)."""
    from openpyxl import Workbook

    xlsx = tmp_path / "titled.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.append(["INVERTER REPORT", "", ""])
    ws.append(["Date And Time", "AC Power (kW)", "Equipment ID"])
    ws.append(["2026-03-01 12:00:00", "120.5", "INV-01"])
    ws.append(["2026-03-01 12:01:00", "121.0", "INV-01"])
    wb.save(xlsx)

    csv_path = tmp_path / "out.csv"
    n = convert_excel_to_csv(xlsx, csv_path, max_decompressed_bytes=1_000_000, max_rows=10_000)
    assert n == 2
    df = pd.read_csv(csv_path)
    assert "Date And Time" in df.columns
    assert not any(str(c).startswith("Unnamed") for c in df.columns)


def test_tidy_excel_not_mistaken_for_wide(tmp_path: Path):
    from openpyxl import Workbook

    xlsx = tmp_path / "tidy.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.append(["Timestamp", "Equipment ID", "AC Power (kW)", "DC Voltage (V)"])
    ws.append(["2026-01-01 12:00:00", "INV-01", "100", "650"])
    wb.save(xlsx)
    csv_path = tmp_path / "tidy.csv"
    n = convert_excel_to_csv(xlsx, csv_path, max_decompressed_bytes=1_000_000, max_rows=10_000)
    assert n == 1
    df = pd.read_csv(csv_path)
    assert list(df.columns) == ["Timestamp", "Equipment ID", "AC Power (kW)", "DC Voltage (V)"]

