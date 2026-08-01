"""Excel onboard pipeline — orchestrates phases 1–6 (AI optional, non-blocking for CSV)."""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from backend.app.config import Settings, get_settings
from backend.app.services.excel_onboard.ai_headers import run_header_ai_assist
from backend.app.services.excel_onboard.analyzer import WorkbookAnalysis, analyze_workbook
from backend.app.services.excel_onboard.bulk import extract_bulk_measurements, write_rows_csv
from backend.app.services.excel_onboard.header_recon import reconstruct_headers
from backend.app.services.excel_onboard.metadata import HeaderMetadataPayload, extract_header_metadata
from backend.app.services.excel_onboard.normalizer import normalize_sheet
from backend.app.services.excel_parser.types import ParseReport

logger = logging.getLogger(__name__)


@dataclass
class OnboardResult:
    rows_written: int
    report: ParseReport
    analysis: WorkbookAnalysis
    header_metadata: HeaderMetadataPayload
    ai_meta: dict[str, Any] = field(default_factory=dict)
    elapsed_ms: int = 0
    phase_timings_ms: dict[str, int] = field(default_factory=dict)


def run_excel_onboard(
    excel_path: Path,
    csv_path: Path,
    *,
    max_rows: int,
    max_decompressed_bytes: int = 0,  # reserved
    report_path: Path | None = None,
    settings: Settings | None = None,
    run_ai: bool = False,
) -> OnboardResult:
    """Full local onboard → tidy CSV. AI is optional and never required for success."""
    settings = settings or get_settings()
    t_all = time.perf_counter()
    timings: dict[str, int] = {}

    t0 = time.perf_counter()
    analysis = analyze_workbook(excel_path)
    timings["analyze"] = int((time.perf_counter() - t0) * 1000)

    sheet = analysis.primary_sheet or (analysis.sheet_names[0] if analysis.sheet_names else None)
    if not sheet:
        raise ValueError("Workbook has no sheets")

    t0 = time.perf_counter()
    normalized = normalize_sheet(excel_path, sheet, analysis=analysis)
    timings["normalize"] = int((time.perf_counter() - t0) * 1000)

    sheet_a = next((s for s in analysis.sheets if s.sheet_name == sheet), None)
    t0 = time.perf_counter()
    headers = reconstruct_headers(
        normalized.matrix,
        header_depth_hint=(sheet_a.header_depth_estimate if sheet_a else 3),
    )
    timings["headers"] = int((time.perf_counter() - t0) * 1000)

    t0 = time.perf_counter()
    meta = extract_header_metadata(analysis=analysis, normalized=normalized, headers=headers)
    timings["metadata"] = int((time.perf_counter() - t0) * 1000)

    ai_meta: dict[str, Any] = {"attempted": False, "skipped": not run_ai}
    if run_ai:
        t0 = time.perf_counter()
        ai_meta = run_header_ai_assist(settings, meta)
        timings["ai_headers"] = int((time.perf_counter() - t0) * 1000)

    t0 = time.perf_counter()
    bulk = extract_bulk_measurements(normalized, headers, sheet_name=sheet)
    timings["bulk"] = int((time.perf_counter() - t0) * 1000)
    if bulk is None:
        raise ValueError(
            f"Could not extract measurements from sheet '{sheet}' after normalize/header rebuild."
        )

    n = write_rows_csv(bulk.rows, csv_path, max_rows=max_rows)
    bulk.report.row_count = n
    bulk.report.sheets_probed = analysis.sheet_names

    elapsed = int((time.perf_counter() - t_all) * 1000)
    logger.info(
        "excel_onboard.done path=%s sheet=%s rows=%s strategy=%s elapsed_ms=%s timings=%s ai=%s",
        excel_path.name,
        sheet,
        n,
        bulk.strategy,
        elapsed,
        timings,
        ai_meta.get("ok") if run_ai else "skipped",
    )

    if report_path is not None:
        report_path.write_text(
            json.dumps(
                {
                    "parse_report": bulk.report.to_dict(),
                    "analysis": analysis.to_dict(),
                    "header_metadata": meta.prompt_json(),
                    "ai_meta": {k: v for k, v in ai_meta.items() if k != "response"}
                    | ({"response_confidence": (ai_meta.get("response") or {}).get("confidence")} if ai_meta.get("response") else {}),
                    "phase_timings_ms": timings,
                    "elapsed_ms": elapsed,
                },
                indent=2,
            ),
            encoding="utf-8",
        )

    return OnboardResult(
        rows_written=n,
        report=bulk.report,
        analysis=analysis,
        header_metadata=meta,
        ai_meta=ai_meta,
        elapsed_ms=elapsed,
        phase_timings_ms=timings,
    )
