"""Runs the validate -> standardize -> normalize stage once both mapping and plant config
have been submitted. This runs synchronously inside the request (bounded by the chunked
reader + deployment size caps) — only the heavy analysis stage is queued through the
in-process worker pool (backend/app/services/job_service.py). See docs/PRD.md §7.6-7.7.
"""
from __future__ import annotations

import json
import logging
import shutil

from sqlalchemy.orm import Session

from analytics.core.context import ResolvedMapping
from analytics.core.job_states import JobState
from analytics.common.prerequisites import evaluate_prerequisites
from analytics.preprocessing.validation import PROCEED_WITH_DROPS_MIN_OK_RATIO
from backend.app.config import Settings
from backend.app.models import Job
from backend.app.services import pipeline
from backend.app.services.storage import job_paths

logger = logging.getLogger("pic_lite.validation_service")


def ready_for_validation(job: Job) -> bool:
    return bool(job.mapping_json) and bool(job.plant_config_json)


def _fields_present_in_canonical(paths) -> set[str]:
    """Fields with at least one non-null value in standardized data.

    Must match orchestrator readiness: empty schema columns (all-null ``dc_power_kw``,
    ``dc_current_a``, etc.) are NOT available. Returning schema ∪ populated was the bug
    that made Validation say \"Will run\" then Results flip to \"Needs input\".
    """
    from analytics.core.context import CanonicalDataAccess

    if not paths.canonical_dir.exists() or not any(paths.canonical_dir.rglob("*.parquet")):
        return set()
    access = CanonicalDataAccess.from_partitions(paths.canonical_dir)
    present = access.populated_columns()
    # Irradiance group: POA or GHI either satisfies clipping prerequisites
    if "poa_w_m2" in present or "ghi_w_m2" in present:
        present = set(present)
        present.add("poa_w_m2")
    return present

def _module_readiness(mapping_cfg: dict, plant_cfg: dict, available_fields: set[str] | None = None) -> list[dict]:
    mapped = set((mapping_cfg.get("column_to_canonical") or {}).values())
    if mapping_cfg.get("timestamp_column"):
        mapped.add("timestamp")
    # Prefer fields actually present in standardized data when available
    fields = available_fields if available_fields is not None else mapped
    # Keep mapped-only extras that aren't data columns (harmless)
    fields = set(fields) | {f for f in mapped if f == "timestamp"}
    plant = plant_cfg.get("plant") or {}
    has_arch = bool(plant.get("architecture"))
    has_ratings = bool(plant.get("equipment_ratings")) or bool(plant.get("inverter_capacity_kw"))
    return evaluate_prerequisites(
        available_fields=fields,
        has_architecture=has_arch,
        has_equipment_ratings=has_ratings,
    )


def _clear_canonical(paths) -> None:
    if paths.canonical_dir.exists():
        shutil.rmtree(paths.canonical_dir, ignore_errors=True)
    paths.canonical_dir.mkdir(parents=True, exist_ok=True)


def run_validation_stage(
    db: Session,
    job: Job,
    settings: Settings,
    *,
    drop_unparseable_timestamps: bool = False,
) -> None:
    job.state = JobState.VALIDATING.value
    job.progress_message = "Validating uploaded data…"
    db.add(job)
    db.commit()

    paths = job_paths(settings.job_root_path, job.id)
    _clear_canonical(paths)

    mapping_cfg = job.mapping_json
    plant_cfg = job.plant_config_json

    mapping = ResolvedMapping(
        column_to_canonical=mapping_cfg["column_to_canonical"],
        confidence_by_column=mapping_cfg.get("confidence_by_column", {}),
        detected_oem_signature=mapping_cfg.get("detected_oem_signature"),
    )

    from analytics.core.context import PlantConfig

    plant = PlantConfig(**{k: v for k, v in plant_cfg["plant"].items() if k in PlantConfig.__dataclass_fields__})

    inputs = pipeline.PipelineInputs(
        csv_path=paths.raw_dir / "input.csv",
        job_paths=paths,
        job_id=job.id,
        mapping=mapping,
        timestamp_column=mapping_cfg["timestamp_column"],
        plant=plant,
        threshold_overrides=plant_cfg.get("threshold_overrides", {}),
    )

    report, row_count = pipeline.parse_validate_standardize(
        inputs,
        drop_unparseable_timestamps=drop_unparseable_timestamps,
    )

    # Readiness from actual canonical fields (after standardize) so UI matches analysis.
    canonical_fields = _fields_present_in_canonical(paths) if not report.has_blockers else None
    readiness = _module_readiness(mapping_cfg, plant_cfg, available_fields=canonical_fields)

    if report.has_blockers:
        job.validation_summary_json = _report_to_dict(report, None, readiness)
        job.error_summary = "; ".join(i.message for i in report.blockers)[:500]
        # Stay recoverable: keep mapping/plant; state failed only means "cannot proceed yet"
        job.state = JobState.FAILED.value
        job.progress_message = "Validation found blocking issues — fix mapping or recover below."
        db.add(job)
        db.commit()
        return

    job.state = JobState.NORMALIZING.value
    job.error_summary = None
    db.add(job)
    db.commit()

    interval_result = pipeline.apply_interval_normalization(paths)
    (paths.canonical_dir / "_interval_meta.json").write_text(
        json.dumps(
            {
                "detected_interval_minutes": interval_result.detected_interval_minutes,
                "resampled": interval_result.resampled,
                "is_irregular": interval_result.is_irregular,
                "per_device_intervals_minutes": interval_result.per_device_intervals_minutes,
                "notes": interval_result.notes,
            }
        ),
        encoding="utf-8",
    )

    job.validation_summary_json = _report_to_dict(report, interval_result, readiness)
    job.progress_message = "Validation complete — review warnings, then run analysis."
    # NORMALIZING doubles as "awaiting acknowledgement" — the frontend calls
    # POST /api/jobs/{id}/acknowledge to move to QUEUED once the user has reviewed warnings.
    db.add(job)
    db.commit()


def _report_to_dict(report, interval_result, module_readiness=None) -> dict:
    blockers = [_issue_dict(i) for i in report.blockers]
    warnings = [_issue_dict(i) for i in report.warnings]
    total_ts = report.timestamp_parse_ok + report.timestamp_parse_fail
    can_drop = report.can_proceed_with_row_drops
    recovery = ["fix_mapping", "retry_validation"]
    if can_drop:
        recovery.append("proceed_with_row_drops")
    recovery.append("start_over")

    return {
        "row_count": report.row_count,
        "column_count": report.column_count,
        "blockers": blockers,
        "warnings": warnings,
        "detected_interval_minutes": interval_result.detected_interval_minutes if interval_result else None,
        "is_irregular_interval": interval_result.is_irregular if interval_result else False,
        "interval_notes": interval_result.notes if interval_result else [],
        "module_readiness": module_readiness or [],
        "timestamp_column": report.timestamp_column,
        "timestamp_parse_ok": report.timestamp_parse_ok,
        "timestamp_parse_fail": report.timestamp_parse_fail,
        "can_proceed_with_row_drops": can_drop,
        "proceed_with_drops_min_ok_ratio": PROCEED_WITH_DROPS_MIN_OK_RATIO,
        "recovery_actions": recovery if blockers else [],
        "rows_that_would_be_dropped": report.timestamp_parse_fail if can_drop else 0,
        "rows_that_would_be_kept": report.timestamp_parse_ok if can_drop else (total_ts if not blockers else 0),
    }


def _issue_dict(issue) -> dict:
    return {
        "code": issue.code,
        "severity": issue.severity,
        "message": issue.message,
        "likely_cause": issue.likely_cause,
        "blocks_analysis": issue.blocks_analysis,
        "affected_rows": issue.affected_rows,
        "affected_columns": list(issue.affected_columns),
        "sample_values": list(getattr(issue, "sample_values", []) or []),
        "remediation": getattr(issue, "remediation", "") or "",
    }
