"""Phase 6 — Bulk measurement extract locally (pandas / existing strategies). Never AI."""
from __future__ import annotations

import csv
import logging
from dataclasses import dataclass
from pathlib import Path

from backend.app.services.excel_onboard.header_recon import HeaderReconstruction
from backend.app.services.excel_onboard.normalizer import NormalizedSheet
from backend.app.services.excel_parser.orchestrator import _run_strategies
from backend.app.services.excel_parser.types import ParseReport

logger = logging.getLogger(__name__)


@dataclass
class BulkExtractResult:
    rows: list[list[str]]
    report: ParseReport
    strategy: str


def extract_bulk_measurements(
    normalized: NormalizedSheet,
    headers: HeaderReconstruction,
    *,
    sheet_name: str,
) -> BulkExtractResult | None:
    """Melt / reshape normalized matrix into tidy long CSV rows (header + data)."""
    matrix = normalized.matrix
    # Prefer battle-tested multi-strategy reshape on the normalized matrix
    result = _run_strategies(matrix, sheet_name=sheet_name)
    if result is not None and result.report.confidence >= 0.55 and len(result.rows) > 1:
        logger.info(
            "excel_onboard.bulk strategy=%s conf=%s out_rows=%s",
            result.report.strategy,
            result.report.confidence,
            len(result.rows) - 1,
        )
        return BulkExtractResult(
            rows=result.rows,
            report=result.report,
            strategy=result.report.strategy,
        )

    # Fallback: write reconstructed flat header + data via pandas-friendly lists
    if headers.timestamp_column_index is None or headers.first_data_row >= len(matrix):
        logger.warning("excel_onboard.bulk fallback unavailable (no ts / data)")
        return None

    col_names = [c.reconstructed_name for c in headers.columns]
    out = [col_names]
    for row in matrix[headers.first_data_row :]:
        out.append([(row[c.index] if c.index < len(row) else "") for c in headers.columns])
    from backend.app.services.excel_parser.types import LayoutKind, ParseReport as PR

    report = PR(
        layout=LayoutKind.TIDY_LONG.value,
        strategy="excel_onboard_flat_fallback",
        sheet_name=sheet_name,
        confidence=0.6,
        header_rows=headers.header_row_indexes,
        timestamp_column=col_names[headers.timestamp_column_index]
        if headers.timestamp_column_index < len(col_names)
        else None,
        inverters_found=sorted({c.equipment_hint for c in headers.columns if c.equipment_hint}),
        columns_mapped=col_names[:20],
        row_count=len(out) - 1,
        warnings=["Used flat header reconstruction fallback; prefer wide melt when possible."],
    )
    logger.info("excel_onboard.bulk fallback flat rows=%s cols=%s", len(out) - 1, len(col_names))
    return BulkExtractResult(rows=out, report=report, strategy=report.strategy)


def write_rows_csv(rows: list[list[str]], csv_path: Path, *, max_rows: int) -> int:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        for i, row in enumerate(rows):
            if i == 0:
                w.writerow(row)
                continue
            if n >= max_rows:
                break
            w.writerow(row)
            n += 1
    return n
