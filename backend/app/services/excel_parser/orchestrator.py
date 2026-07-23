"""Orchestrate probe → layout strategies → CSV write with confidence report."""
from __future__ import annotations

import csv
import json
from pathlib import Path

from backend.app.services.excel_parser.headers import pad_matrix, sanitize_headers
from backend.app.services.excel_parser.probe import load_sheet_matrix, probe_workbook
from backend.app.services.excel_parser.strategies import (
    try_tidy_long,
    try_transposed,
    try_wide_multi_header,
    try_wide_single_header,
)
from backend.app.services.excel_parser.types import MIN_USABLE_CONFIDENCE, ParseReport, StrategyResult
from backend.app.services.storage import UploadTooLargeError

# Prefer structured SCADA layouts before generic tidy promotion.
_STRATEGIES = (
    try_wide_multi_header,
    try_wide_single_header,
    try_transposed,
    try_tidy_long,
)


class ExcelConversionError(Exception):
    """Raised when no strategy can convert the workbook with usable confidence."""

    def __init__(self, message: str, report: ParseReport | None = None):
        super().__init__(message)
        self.report = report


def parse_excel_to_csv(
    excel_path: Path,
    csv_path: Path,
    *,
    max_decompressed_bytes: int,
    max_rows: int,
    report_path: Path | None = None,
) -> tuple[int, ParseReport]:
    """Convert Excel → pipeline CSV via strategy chain. Returns (rows, report)."""
    suffix = excel_path.suffix.lower()
    if suffix not in {".xlsx", ".xlsm", ".xls"}:
        raise ExcelConversionError(f"Unsupported Excel type: {suffix}")

    try:
        probes = probe_workbook(excel_path)
    except Exception as exc:  # noqa: BLE001
        raise ExcelConversionError(f"Could not read Excel file: {exc}") from exc

    if not probes:
        raise ExcelConversionError("The Excel file has no readable sheets.")

    sheet_names = [p.sheet_name for p in probes]
    attempts: list[str] = []
    best_fail: ParseReport | None = None

    # Score sheets: prefer ones whose sample looks like inverter reports
    ordered = _rank_sheets(probes)

    for sheet_name in ordered:
        try:
            name, matrix = load_sheet_matrix(excel_path, sheet_name)
        except Exception as exc:  # noqa: BLE001
            attempts.append(f"{sheet_name}: load failed ({exc})")
            continue
        if not matrix or not any(any(c.strip() for c in r) for r in matrix):
            attempts.append(f"{sheet_name}: empty")
            continue

        result = _run_strategies(matrix, sheet_name=name)
        if result is None:
            attempts.append(f"{sheet_name}: no strategy matched")
            continue

        report = result.report
        report.sheets_probed = sheet_names
        if report.confidence < MIN_USABLE_CONFIDENCE or report.error:
            attempts.append(
                f"{sheet_name}/{report.strategy}: low confidence {report.confidence}"
                + (f" — {report.error}" if report.error else "")
            )
            best_fail = report
            continue

        n = _write_matrix_csv(
            result.rows,
            csv_path,
            max_decompressed_bytes=max_decompressed_bytes,
            max_rows=max_rows,
        )
        report.row_count = n
        if report_path is not None:
            report_path.write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")
        return n, report

    detail = "; ".join(attempts) if attempts else "no sheets"
    msg = (
        "Could not confidently parse this Excel file. "
        f"Tried sheets/strategies: {detail}. "
        "Expected a tidy Timestamp+Equipment export, a wide INV*_P header, "
        "or a multi-row INVERTER REPORT with Date And Time + DC/AC metrics."
    )
    raise ExcelConversionError(msg, report=best_fail)


def convert_excel_to_csv(
    excel_path: Path,
    csv_path: Path,
    *,
    max_decompressed_bytes: int,
    max_rows: int,
    report_path: Path | None = None,
) -> int:
    """Backward-compatible wrapper used by upload + tests."""
    n, _ = parse_excel_to_csv(
        excel_path,
        csv_path,
        max_decompressed_bytes=max_decompressed_bytes,
        max_rows=max_rows,
        report_path=report_path,
    )
    return n


def try_reshape_wide_inverter_report(rows: list[list[str]]) -> list[list[str]] | None:
    """Test/compat helper: reshape matrix with wide multi-header strategy only."""
    result = try_wide_multi_header(pad_matrix(rows), sheet_name="Sheet1")
    return result.rows if result else None


def try_promote_header_row(rows: list[list[str]]) -> list[list[str]]:
    """Compat: promote best-scoring header row (tidy fallback without full strategy)."""
    from backend.app.services.excel_parser.headers import score_header_row

    if not rows:
        return rows
    matrix = pad_matrix(rows)
    best_i = 0
    best_s = -1.0
    for i, row in enumerate(matrix[:40]):
        s = score_header_row(row)
        if s > best_s:
            best_s = s
            best_i = i
    return matrix[best_i:]


def _run_strategies(matrix: list[list[str]], *, sheet_name: str) -> StrategyResult | None:
    best: StrategyResult | None = None
    padded = pad_matrix(matrix)
    input_width = len(padded[0]) if padded else 0

    for fn in _STRATEGIES:
        result = fn(matrix, sheet_name=sheet_name)
        if result is None:
            continue
        # Wide reshape intentionally collapses INV blocks into a few tidy metrics.
        # On very wide sheets that are NOT inverter-block layouts (e.g. hundreds of
        # SMB/string current columns), early-accepting wide would silently drop most
        # headers. Demote confidence so tidy_long (full header preserve) can win.
        if (
            result.report.strategy.startswith("wide")
            and input_width >= 40
            and _looks_like_per_device_metric_sheet(padded)
        ):
            mapped_n = len(result.report.columns_mapped or [])
            if mapped_n < max(10, int(input_width * 0.08)):
                result.report.confidence = min(result.report.confidence, 0.72)
                result.report.warnings = list(result.report.warnings or []) + [
                    f"Wide reshape kept {mapped_n} of ~{input_width} columns; "
                    "preferring full-header preserve for SMB/string-style exports."
                ]
        if best is None or result.report.confidence > best.report.confidence:
            best = result
        # Early accept high-confidence structured layouts (true inverter reports)
        if result.report.confidence >= 0.85 and result.report.strategy.startswith("wide"):
            return result
    return best


def _looks_like_per_device_metric_sheet(rows: list[list[str]]) -> bool:
    """True when many columns look like SMB/SCB/string currents rather than INV*_P blocks."""
    if not rows:
        return False
    header = rows[0]
    smbish = 0
    for h in header:
        n = (h or "").strip().lower().replace("_", " ").replace("-", " ")
        if not n:
            continue
        if any(tok in n for tok in ("smb", "scb", "string current", "combiner")) and (
            "current" in n or "idc" in n or n.endswith(" i") or " voltage" in n or "vdc" in n
        ):
            smbish += 1
        elif n.startswith("smb") or n.startswith("scb"):
            smbish += 1
    return smbish >= 5


def _rank_sheets(probes) -> list[str]:
    from analytics.common.complete_analysis_pack import prefer_scada_sheet_bonus

    scored: list[tuple[float, str]] = []
    for p in probes:
        text = " ".join(" ".join(r) for r in p.sample_rows[:15]).lower()
        score = 0.0
        score += prefer_scada_sheet_bonus(p.sheet_name)
        if "inverter" in text:
            score += 5.0
        if "date" in text and "time" in text:
            score += 3.0
        if "power" in text or "voltage" in text:
            score += 2.0
        if "equipment id" in text or "timestamp" in text:
            score += 4.0
        score += min(p.n_cols, 50) * 0.02
        scored.append((score, p.sheet_name))
    scored.sort(key=lambda x: (-x[0], x[1]))
    return [n for _, n in scored]


def _write_matrix_csv(
    rows: list[list[str]],
    csv_path: Path,
    *,
    max_decompressed_bytes: int,
    max_rows: int,
) -> int:
    if not rows:
        raise ExcelConversionError("The Excel sheet is empty.")

    header = sanitize_headers(rows[0])
    body = rows[1:]
    written_bytes = 0
    row_count = 0
    with open(csv_path, "w", encoding="utf-8", newline="") as out:
        writer = csv.writer(out)
        writer.writerow(header)
        written_bytes = out.tell()
        for values in body:
            if not any(str(v).strip() for v in values):
                continue
            width = len(header)
            row = list(values) + [""] * max(0, width - len(values))
            writer.writerow(row[:width])
            written_bytes = out.tell()
            if written_bytes > max_decompressed_bytes:
                csv_path.unlink(missing_ok=True)
                raise UploadTooLargeError(
                    f"Converted CSV exceeds the {max_decompressed_bytes // (1024 * 1024)} MB limit for this deployment."
                )
            row_count += 1
            if row_count > max_rows:
                csv_path.unlink(missing_ok=True)
                raise UploadTooLargeError(f"Excel sheet exceeds the {max_rows:,} row limit for this deployment.")
    if row_count == 0:
        raise ExcelConversionError("The Excel sheet has a header but no data rows.")
    return row_count
