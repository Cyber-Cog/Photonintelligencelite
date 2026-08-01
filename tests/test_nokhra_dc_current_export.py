"""Nokhra-style ICR/INV report: DC_CURRENT zeros must survive parse → export."""
from __future__ import annotations

import io
from pathlib import Path

import pandas as pd
from openpyxl import Workbook

from analytics.common.complete_analysis_pack import OFFICIAL_COLUMN_TO_CANONICAL
from analytics.common.user_facing_export import format_user_facing_frame
from analytics.core.context import ResolvedMapping
from analytics.preprocessing.interval_normalize import normalize_interval
from analytics.preprocessing.standardize import standardize
from analytics.preprocessing.timezone_normalize import normalize_timezone
from backend.app.services.excel_parser.orchestrator import parse_excel_to_csv
from backend.app.services.excel_parser.strategies.wide_multi_header import try_wide_multi_header
from backend.app.services.explorer_service import export_data_csv_bytes


def _nokhra_like_matrix() -> list[list[str]]:
    """Minimal NTPC Nokhra layout: ICR13 / INV1-2 / AC+DC_CURRENT+DC_POWER + WMS GHI/GTI."""
    width = 20
    rows: list[list[str]] = [[""] * width for _ in range(12)]
    rows[0][2] = "NTPC-300MW NOKHRA,Rajasthan"
    rows[6][0] = "DATE AND TIME"
    rows[6][3] = "ICR13"
    rows[6][15] = "MCR"
    rows[7][3] = "INV1"
    rows[7][9] = "INV2"
    rows[7][15] = "WMS"
    rows[8][3] = "AC_ACTIVE_POWER_kW"
    rows[8][6] = "DC_CURRENT"
    rows[8][7] = "DC_POWER"
    rows[8][9] = "AC_ACTIVE_POWER_kW"
    rows[8][12] = "DC_CURRENT"
    rows[8][13] = "DC_POWER"
    rows[8][15] = "GHI Main (W/m2)"
    rows[8][16] = "GHI Main (KWhr/m2)"
    rows[8][17] = "GTI 19 Deg(W/m2)"
    # Early morning zeros + WMS sentinels
    rows[9] = [""] * width
    rows[9][0] = "2026-07-30 05:01:00"
    rows[9][3] = "0"
    rows[9][6] = "0"
    rows[9][7] = "0"
    rows[9][9] = "0"
    rows[9][12] = "0"
    rows[9][13] = "0"
    rows[9][15] = "-1"
    rows[9][16] = "0"
    rows[9][17] = "-1"
    rows[10] = [""] * width
    rows[10][0] = "2026-07-30 12:00:00"
    rows[10][3] = "2884"
    rows[10][6] = "0"
    rows[10][7] = "1552"
    rows[10][9] = "2894"
    rows[10][12] = "0"
    rows[10][13] = "1596"
    rows[10][15] = "900"
    rows[10][16] = "2.7"
    rows[10][17] = "916"
    rows[11] = [""] * width
    rows[11][0] = "2026-07-30 12:01:00"
    rows[11][3] = "2840"
    rows[11][6] = "12.5"
    rows[11][7] = "1528"
    rows[11][9] = "2929"
    rows[11][12] = "11.0"
    rows[11][13] = "2980"
    rows[11][15] = "905"
    rows[11][16] = "2.8"
    rows[11][17] = "920"
    return rows


def test_wide_multi_header_captures_wms_ghi_gti():
    result = try_wide_multi_header(_nokhra_like_matrix(), sheet_name="NOKHRA")
    assert result is not None
    assert "GHI (W/m2)" in result.report.columns_mapped
    assert "Irradiance (W/m2)" in result.report.columns_mapped
    header = result.rows[0]
    eq_i = header.index("Equipment ID")
    ghi_i = header.index("GHI (W/m2)")
    poa_i = header.index("Irradiance (W/m2)")
    devices = {r[eq_i] for r in result.rows[1:]}
    assert "WMS" in devices
    wms_noon = next(
        r
        for r in result.rows[1:]
        if r[eq_i] == "WMS" and r[header.index("Timestamp")] == "2026-07-30 12:00:00"
    )
    assert wms_noon[ghi_i] == "900"
    assert wms_noon[poa_i] == "916"
    # Sentinel -1 morning must not invent a bogus WMS irradiance reading
    early_wms = [
        r
        for r in result.rows[1:]
        if r[eq_i] == "WMS" and r[header.index("Timestamp")] == "2026-07-30 05:01:00"
    ]
    assert early_wms == []


def test_wide_multi_header_preserves_dc_current_zeros_all_timestamps():
    result = try_wide_multi_header(_nokhra_like_matrix(), sheet_name="NOKHRA")
    assert result is not None
    assert "DC Current (A)" in result.report.columns_mapped
    header = result.rows[0]
    dc_i = header.index("DC Current (A)")
    ts_i = header.index("Timestamp")
    eq_i = header.index("Equipment ID")
    inv_rows = [r for r in result.rows[1:] if "INV" in r[eq_i]]
    # Every inverter row must carry DC current (including literal 0)
    for row in inv_rows:
        assert row[dc_i] != "", f"missing DC current at {row[ts_i]}"
    # Midday zero preserved
    noon = next(r for r in inv_rows if r[ts_i] == "2026-07-30 12:00:00")
    assert noon[dc_i] == "0"
    # Non-zero later preserved
    later = next(r for r in inv_rows if r[ts_i] == "2026-07-30 12:01:00")
    assert later[dc_i] in {"12.5", "11.0"} or float(later[dc_i]) > 0


def test_nokhra_xlsx_parse_standardize_export_local(tmp_path: Path):
    wb = Workbook()
    ws = wb.active
    ws.title = "NEW 300MW NOKHRA REPORT"
    for r_i, row in enumerate(_nokhra_like_matrix(), start=1):
        for c_i, val in enumerate(row, start=1):
            if val != "":
                ws.cell(r_i, c_i, val)
    xlsx = tmp_path / "nokhra.xlsx"
    wb.save(xlsx)

    raw_csv = tmp_path / "input.csv"
    n, report = parse_excel_to_csv(
        xlsx, raw_csv, max_decompressed_bytes=5_000_000, max_rows=100_000
    )
    assert n >= 4
    assert "DC Current (A)" in (report.columns_mapped or [])
    assert "GHI (W/m2)" in (report.columns_mapped or [])
    raw = pd.read_csv(raw_csv)
    assert "DC Current (A)" in raw.columns
    assert "GHI (W/m2)" in raw.columns
    assert (raw["Equipment ID"] == "WMS").any()
    assert raw["DC Current (A)"].notna().all() or raw.loc[raw["Equipment ID"] != "WMS", "DC Current (A)"].notna().all()
    # At least one explicit zero and one positive on inverters
    inv = raw[raw["Equipment ID"].astype(str).str.contains("INV", na=False)]
    vals = pd.to_numeric(inv["DC Current (A)"], errors="coerce")
    assert (vals == 0).any()
    assert (vals > 0).any()
    wms = raw[raw["Equipment ID"] == "WMS"]
    ghi = pd.to_numeric(wms["GHI (W/m2)"], errors="coerce")
    assert (ghi >= 900).any()

    c2c = {}
    for col in raw.columns:
        if col == "Timestamp":
            continue
        if col in OFFICIAL_COLUMN_TO_CANONICAL:
            c2c[col] = OFFICIAL_COLUMN_TO_CANONICAL[col]
        elif col == "Equipment ID":
            c2c[col] = "device_id"
        elif col == "ICR ID":
            c2c[col] = "icr_id"
    mapping = ResolvedMapping(column_to_canonical=c2c, confidence_by_column={k: 1.0 for k in c2c})
    canon = standardize(raw, mapping, "Timestamp")
    inv_canon = canon[canon["device_type"] == "inverter"]
    wms_canon = canon[canon["device_type"] == "wms"]
    assert not inv_canon.empty
    assert not wms_canon.empty
    assert inv_canon["dc_current_a"].notna().all()
    assert wms_canon["ghi_w_m2"].notna().any()
    assert wms_canon["poa_w_m2"].notna().any()
    canon = normalize_timezone(canon, "Asia/Kolkata")
    # First local 05:01 → UTC previous evening
    assert str(canon["timestamp_utc"].iloc[0]).startswith("2026-07-29 23:31")
    canon, _ = normalize_interval(canon)
    assert canon.loc[canon["device_type"] == "inverter", "dc_current_a"].notna().all()
    assert canon.loc[canon["device_type"] == "wms", "ghi_w_m2"].notna().any()

    # Write parquet like pipeline, then export with professional headers + local time
    canon_dir = tmp_path / "canonical"
    canon_dir.mkdir()
    for col in ("scb_id", "string_id", "dc_voltage_v", "poa_w_m2", "ghi_w_m2", "module_temp_c", "ambient_temp_c", "energy_kwh"):
        if col not in canon.columns:
            canon[col] = pd.NA
    if "icr_id" not in canon.columns:
        canon["icr_id"] = "ICR13"
    canon.to_parquet(canon_dir, engine="pyarrow", partition_cols=["device_type"], index=False)

    content = export_data_csv_bytes(canon_dir, Path(), timezone="Asia/Kolkata")
    assert content
    exported = pd.read_csv(io.BytesIO(content))
    assert "Timestamp" in exported.columns
    assert "timestamp_utc" not in exported.columns
    assert "DC Current (A)" in exported.columns
    assert "GHI (W/m²)" in exported.columns or "GHI (W/m2)" in exported.columns
    assert "dc_current_a" not in exported.columns
    # Empty identity cols dropped
    assert "SCB ID" not in exported.columns or exported["SCB ID"].notna().any()
    # Plant local (not UTC offset)
    assert str(exported["Timestamp"].iloc[0]).startswith("2026-07-30 05:01")
    inv_exp = exported[exported["Equipment ID"].astype(str).str.contains("INV", na=False)]
    dc = pd.to_numeric(inv_exp["DC Current (A)"], errors="coerce")
    assert dc.notna().all()
    assert (dc == 0).any()
    wms_exp = exported[exported["Equipment ID"] == "WMS"]
    assert not wms_exp.empty


def test_format_user_facing_drops_internal_and_empty():
    df = pd.DataFrame(
        {
            "timestamp_utc": pd.to_datetime(["2026-07-30 00:00:00+00:00", "2026-07-30 00:01:00+00:00"]),
            "device_id": ["INV-01", "INV-01"],
            "ac_power_kw": [10.0, 11.0],
            "dc_current_a": [0.0, 1.5],
            "scb_id": [pd.NA, pd.NA],
            "__fragment_meta": ["x", "y"],
            "energy_kwh": [pd.NA, pd.NA],
        }
    )
    out = format_user_facing_frame(df, timezone="Asia/Kolkata", drop_empty=True)
    assert list(out.columns)[:2] == ["Timestamp", "Equipment ID"]
    assert "DC Current (A)" in out.columns
    assert "__fragment_meta" not in out.columns
    assert "SCB ID" not in out.columns
    assert "Energy (kWh)" not in out.columns
    assert str(out["Timestamp"].iloc[0]).startswith("2026-07-30 05:30")
