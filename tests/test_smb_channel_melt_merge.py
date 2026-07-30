"""Mondelez-style multi-row SMB Excel → channel melt + multi-file merge."""
from __future__ import annotations

from pathlib import Path

import pytest
from openpyxl import Workbook

from backend.app.services.excel_parser import parse_excel_to_csv
from backend.app.services.merge_uploads import merge_csv_files


def _write_smb_xlsx(path: Path, *, smb_n: int, n_rows: int = 5) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = f"SMB_{smb_n}"
    # Row 0: group labels (merged-style blanks)
    row0 = ["No.", "Date & Time", "SMB Parameter", "", "", "", "", "Strings Current (A)"] + [""] * 23
    # Row 1: leaves
    row1 = ["", "", "Voltage (V)", "Current (A)", "Power (KW)", "Int. Temp. (°C)", "Ext. Temp (°C)"] + [
        f"I{i}" for i in range(1, 25)
    ]
    ws.append(row0)
    ws.append(row1)
    for r in range(n_rows):
        ts = f"01/02/2026 {6 + r:02d}:00:30"
        vals = [r + 1, ts, 800.0 + r, 10.0 + r, 8.0 + r, 25.0, 30.0] + [0.5 * i for i in range(1, 25)]
        ws.append(vals)
    wb.save(path)


def test_smb_multi_row_channel_melt_parses(tmp_path: Path):
    xlsx = tmp_path / "smb1.xlsx"
    _write_smb_xlsx(xlsx, smb_n=1)
    out = tmp_path / "out.csv"
    n, report = parse_excel_to_csv(
        xlsx,
        out,
        max_decompressed_bytes=50 * 1024 * 1024,
        max_rows=500_000,
    )
    assert report.strategy == "wide_channel_melt"
    assert report.multi_row_header is True
    assert n == 5 * 24  # rows × I1..I24
    assert "DC Current (A)" in report.columns_mapped
    assert "DC Voltage (V)" in report.columns_mapped
    assert "DC Power (kW)" in report.columns_mapped  # not AC
    import pandas as pd

    df = pd.read_csv(out)
    assert "Equipment ID" in df.columns
    assert df["Equipment ID"].str.startswith("SMB-01-STR-").all()


def test_thirteen_smb_workbooks_merge(tmp_path: Path):
    parts: list[Path] = []
    for i in range(1, 14):
        xlsx = tmp_path / f"upload_{i}.xlsx"
        _write_smb_xlsx(xlsx, smb_n=i, n_rows=3)
        csv_path = tmp_path / f"part_{i}.csv"
        n, report = parse_excel_to_csv(
            xlsx,
            csv_path,
            max_decompressed_bytes=50 * 1024 * 1024,
            max_rows=500_000,
        )
        assert report.strategy == "wide_channel_melt"
        assert n == 3 * 24
        parts.append(csv_path)

    dest = tmp_path / "input.csv"
    rows, names = merge_csv_files(parts, dest)
    assert len(names) == 13
    # Must not raise ambiguous DataFrame truthiness; must keep all SMBs
    assert rows == 13 * 3 * 24
    import pandas as pd

    df = pd.read_csv(dest)
    assert df["Equipment ID"].nunique() == 13 * 24
