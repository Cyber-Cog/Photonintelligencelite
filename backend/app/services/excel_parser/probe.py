"""Probe workbook sheets: dimensions, sample rows, rough dtype guesses."""
from __future__ import annotations

from pathlib import Path

from backend.app.services.excel_parser.headers import cell_to_str
from backend.app.services.excel_parser.types import SheetProbe


def probe_workbook(excel_path: Path, *, sample_rows: int = 30, max_sheets: int = 8) -> list[SheetProbe]:
    suffix = excel_path.suffix.lower()
    if suffix in {".xlsx", ".xlsm"}:
        return _probe_openpyxl(excel_path, sample_rows=sample_rows, max_sheets=max_sheets)
    if suffix == ".xls":
        return _probe_xls(excel_path, sample_rows=sample_rows, max_sheets=max_sheets)
    raise ValueError(f"Unsupported Excel type: {suffix}")


def _probe_openpyxl(excel_path: Path, *, sample_rows: int, max_sheets: int) -> list[SheetProbe]:
    from openpyxl import load_workbook

    wb = load_workbook(excel_path, read_only=True, data_only=True)
    try:
        probes: list[SheetProbe] = []
        for name in wb.sheetnames[:max_sheets]:
            ws = wb[name]
            rows: list[list[str]] = []
            n_cols = 0
            for i, row in enumerate(ws.iter_rows(values_only=True)):
                vals = [cell_to_str(c) for c in row]
                n_cols = max(n_cols, len(vals))
                if i < sample_rows:
                    rows.append(vals)
                # Cap full scan for huge sheets — still get approximate size from max_row when available
            n_rows = ws.max_row or len(rows)
            # Prefer counting non-empty from sample; max_row is fine for probe
            probes.append(
                SheetProbe(
                    sheet_name=name,
                    n_rows=int(n_rows),
                    n_cols=int(ws.max_column or n_cols),
                    sample_rows=rows,
                    merged_cell_count=0,  # read_only mode has no merged_cells
                    dtype_guesses=_guess_dtypes(rows),
                )
            )
        return probes
    finally:
        wb.close()


def _probe_xls(excel_path: Path, *, sample_rows: int, max_sheets: int) -> list[SheetProbe]:
    import pandas as pd

    xl = pd.ExcelFile(excel_path)
    probes: list[SheetProbe] = []
    for name in xl.sheet_names[:max_sheets]:
        df = pd.read_excel(xl, sheet_name=name, header=None, dtype=str, nrows=sample_rows)
        rows = [[cell_to_str(v) for v in row] for row in df.fillna("").to_numpy().tolist()]
        # Full size via another cheap read of shape
        full = pd.read_excel(xl, sheet_name=name, header=None, nrows=0)
        # nrows=0 doesn't give shape — approximate from sample; caller may re-read
        probes.append(
            SheetProbe(
                sheet_name=name,
                n_rows=max(len(rows), 1),
                n_cols=max((len(r) for r in rows), default=0),
                sample_rows=rows,
                merged_cell_count=0,
                dtype_guesses=_guess_dtypes(rows),
            )
        )
        _ = full  # silence unused
    return probes


def _guess_dtypes(rows: list[list[str]]) -> list[str]:
    if len(rows) < 2:
        return []
    width = max(len(r) for r in rows)
    guesses: list[str] = []
    for j in range(min(width, 20)):
        vals = [r[j].strip() for r in rows[1:] if j < len(r) and r[j].strip()]
        if not vals:
            guesses.append("empty")
            continue
        numeric = 0
        for v in vals[:20]:
            try:
                float(v.replace(",", ""))
                numeric += 1
            except ValueError:
                pass
        if numeric / max(len(vals[:20]), 1) >= 0.7:
            guesses.append("numeric")
        else:
            guesses.append("text")
    return guesses


def load_sheet_matrix(excel_path: Path, sheet_name: str | None = None) -> tuple[str, list[list[str]]]:
    """Load full sheet as string matrix. Returns (sheet_name, rows)."""
    suffix = excel_path.suffix.lower()
    if suffix in {".xlsx", ".xlsm"}:
        from openpyxl import load_workbook

        wb = load_workbook(excel_path, read_only=True, data_only=True)
        try:
            name = sheet_name or (wb.sheetnames[0] if wb.sheetnames else None)
            if not name:
                raise ValueError("Workbook has no sheets.")
            ws = wb[name]
            rows = [[cell_to_str(c) for c in row] for row in ws.iter_rows(values_only=True)]
            return name, rows
        finally:
            wb.close()

    if suffix == ".xls":
        import pandas as pd

        xl = pd.ExcelFile(excel_path)
        name = sheet_name or xl.sheet_names[0]
        df = pd.read_excel(xl, sheet_name=name, header=None, dtype=str)
        rows = [[cell_to_str(v) for v in row] for row in df.fillna("").to_numpy().tolist()]
        return name, rows

    raise ValueError(f"Unsupported Excel type: {suffix}")
