"""The end-to-end per-job pipeline: parse -> validate -> standardize -> normalize ->
analyze -> report. This is the only place that wires the analytics package into the
backend; API routers never call algorithms directly (docs/architecture_decisions.md §4).

Chunked reading: the raw CSV is read with `pandas.read_csv(chunksize=...)` and only the
mapped columns are kept (`usecols`), so peak memory during ingestion is bounded to one
chunk at a time rather than the whole file. Interval normalization then reads back the
already-written (size-capped) canonical partitions in one pass — see the inline note in
`run_pipeline` for why this is an acceptable MVP boundary rather than a fully chunked
resample.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from analytics.common.config_loader import resolve_thresholds
from analytics.core.context import AnalysisContext, CanonicalDataAccess, JobMeta, PlantConfig, ResolvedMapping
from analytics.core.orchestrator import AnalysisOrchestrator, OrchestratorRun
from analytics.preprocessing.interval_normalize import IntervalNormalizationResult, normalize_interval
from analytics.preprocessing.standardize import standardize
from analytics.preprocessing.timezone_normalize import normalize_timezone
from analytics.preprocessing.validation import ValidationIssue, ValidationReport, validate_raw_frame
from backend.app.services.storage import JobPaths

logger = logging.getLogger("pic_lite.pipeline")

CHUNK_ROWS = 200_000


@dataclass
class PipelineInputs:
    csv_path: Path
    job_paths: JobPaths
    job_id: str
    mapping: ResolvedMapping
    timestamp_column: str
    plant: PlantConfig
    threshold_overrides: dict[str, dict[str, float]]


def _merge_reports(reports: list[ValidationReport]) -> ValidationReport:
    merged = ValidationReport(
        row_count=sum(r.row_count for r in reports),
        column_count=reports[0].column_count if reports else 0,
        timestamp_column=reports[0].timestamp_column if reports else None,
        timestamp_parse_ok=sum(r.timestamp_parse_ok for r in reports),
        timestamp_parse_fail=sum(r.timestamp_parse_fail for r in reports),
    )
    by_code: dict[str, ValidationIssue] = {}
    for report in reports:
        for issue in report.issues:
            if issue.code in by_code:
                existing = by_code[issue.code]
                existing.affected_rows += issue.affected_rows
                # Keep richest remediation / samples
                if len(issue.sample_values) > len(existing.sample_values):
                    existing.sample_values = list(issue.sample_values)
                if issue.remediation and not existing.remediation:
                    existing.remediation = issue.remediation
            else:
                by_code[issue.code] = ValidationIssue(
                    code=issue.code,
                    severity=issue.severity,
                    message=issue.message,
                    likely_cause=issue.likely_cause,
                    blocks_analysis=issue.blocks_analysis,
                    affected_rows=issue.affected_rows,
                    affected_columns=list(issue.affected_columns),
                    sample_values=list(issue.sample_values),
                    remediation=issue.remediation,
                )
    # Recompute datetime blocker severity from merged totals
    dt = by_code.get("invalid_datetime_format")
    if dt is not None:
        total = merged.timestamp_parse_ok + merged.timestamp_parse_fail
        bad_ratio = merged.timestamp_parse_fail / max(total, 1)
        from analytics.preprocessing.validation import DATETIME_BLOCKER_BAD_RATIO

        # drop_unparseable mode: every chunk marked the issue non-blocking
        force_warn = all(
            (not iss.blocks_analysis)
            for r in reports
            for iss in r.issues
            if iss.code == "invalid_datetime_format"
        )
        if bad_ratio < DATETIME_BLOCKER_BAD_RATIO or force_warn:
            dt.blocks_analysis = False
            dt.severity = "warning"
        else:
            dt.blocks_analysis = True
            dt.severity = "blocker"
        ts_col = merged.timestamp_column or (dt.affected_columns[0] if dt.affected_columns else "timestamp")
        dt.message = (
            f"{merged.timestamp_parse_fail:,} of {total:,} value(s) in timestamp column '{ts_col}' "
            f"could not be parsed ({merged.timestamp_parse_ok:,} OK)."
        )
        if dt.sample_values:
            dt.message += f" Sample raw values: {', '.join(repr(s) for s in dt.sample_values)}."

    merged.issues = list(by_code.values())
    return merged


def parse_validate_standardize(
    inputs: PipelineInputs,
    *,
    drop_unparseable_timestamps: bool = False,
) -> tuple[ValidationReport, int]:
    """Chunked read -> per-chunk validation -> standardize -> tz-normalize -> write canonical
    parquet partitions. Returns the merged validation report and total row count written.
    """
    required_columns = list(inputs.mapping.column_to_canonical.keys()) + [inputs.timestamp_column]
    numeric_targets = {"ac_power_kw", "dc_power_kw", "dc_current_a", "dc_voltage_v", "poa_w_m2", "ghi_w_m2", "energy_kwh"}
    numeric_columns = [c for c, f in inputs.mapping.column_to_canonical.items() if f in numeric_targets]

    reports: list[ValidationReport] = []
    total_written = 0

    reader = pd.read_csv(inputs.csv_path, chunksize=CHUNK_ROWS, usecols=lambda c: c in required_columns or c == inputs.timestamp_column)
    for chunk in reader:
        chunk_report = validate_raw_frame(
            chunk,
            inputs.timestamp_column,
            required_columns,
            numeric_columns,
            drop_unparseable_timestamps=drop_unparseable_timestamps,
        )
        reports.append(chunk_report)
        if chunk_report.has_blockers:
            continue

        canonical_chunk = standardize(
            chunk,
            inputs.mapping,
            inputs.timestamp_column,
            architecture=inputs.plant.architecture or None,
        )
        if canonical_chunk.empty:
            continue
        canonical_chunk = normalize_timezone(canonical_chunk, inputs.plant.timezone)
        canonical_chunk.to_parquet(inputs.job_paths.canonical_dir, engine="pyarrow", partition_cols=["device_type"], index=False)
        total_written += len(canonical_chunk)

    if not reports:
        empty = ValidationReport(row_count=0, column_count=0)
        empty.add(
            ValidationIssue(
                code="empty_file",
                severity="blocker",
                message="The uploaded file contains no data rows.",
                likely_cause="The CSV export was empty or only contained a header row.",
                blocks_analysis=True,
                remediation="Re-export the SCADA file with data rows, then upload again.",
            )
        )
        return empty, 0

    return _merge_reports(reports), total_written


def apply_interval_normalization(job_paths: JobPaths) -> IntervalNormalizationResult:
    """Reads back the (already size-capped) canonical partitions once, detects the dominant
    sampling interval, resamples every device to it, and rewrites the canonical partitions.
    Acceptable MVP boundary: this is not itself chunked because the data has already passed
    the ingestion-time row/size caps (analytics/config/defaults.yaml deployment_limits), so
    the working set here is bounded by the same caps that bounded the chunked ingest above.
    """
    access = CanonicalDataAccess.from_partitions(job_paths.canonical_dir)
    full = access.frame()
    resampled, result = normalize_interval(full)

    import shutil

    shutil.rmtree(job_paths.canonical_dir, ignore_errors=True)
    job_paths.canonical_dir.mkdir(parents=True, exist_ok=True)
    if not resampled.empty:
        resampled.to_parquet(job_paths.canonical_dir, engine="pyarrow", partition_cols=["device_type"], index=False)
    return result


def build_context(inputs: PipelineInputs, interval_result: IntervalNormalizationResult) -> AnalysisContext:
    thresholds = resolve_thresholds(inputs.plant.plant_type, inputs.plant.bifacial, inputs.threshold_overrides)
    canonical = CanonicalDataAccess.from_partitions(inputs.job_paths.canonical_dir)
    job_meta = JobMeta(job_id=inputs.job_id, created_at=datetime.now(timezone.utc).isoformat(), trace_id=inputs.job_id)
    return AnalysisContext(
        canonical=canonical,
        plant=inputs.plant,
        mapping=inputs.mapping,
        timezone=inputs.plant.timezone,
        sample_interval_minutes=interval_result.detected_interval_minutes,
        thresholds=thresholds,
        job_meta=job_meta,
    )


def run_orchestrator(context: AnalysisContext) -> OrchestratorRun:
    import analytics.algorithms  # noqa: F401 - triggers registration

    orchestrator = AnalysisOrchestrator()
    return orchestrator.run(context)
