"""Mapping submission, plant metadata submission, and warning acknowledgement.

Validation runs automatically once both mapping and plant config are present (see
backend/app/services/validation_service.py). See docs/PRD.md §7.3, §7.5, §7.6.
"""
from __future__ import annotations

import json
import logging
import shutil

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from analytics.common.architecture_excel import (
    TEMPLATE_FILENAME,
    apply_smb_pattern,
    build_template_bytes,
    parse_architecture_excel,
)
from analytics.common.plant_config_consistency import IMPORTED_NAMEPLATE_KEYS, snapshot_imported_nameplate
from analytics.common.plant_structure import infer_from_csv, normalize_plant_type
from analytics.core.job_states import JobState
from backend.app.auth.deps import enforce_csrf, get_optional_user, require_verified_user
from backend.app.auth.audit import record_audit
from backend.app.auth.job_access import load_job_authorized
from backend.app.auth.rate_limit import client_ip
from backend.app.config import Settings, get_settings
from backend.app.database import get_db
from backend.app.models import Job, User
from backend.app.schemas import (
    AcknowledgeWarningsRequest,
    ArchitectureUploadResponse,
    DetectEquipmentRequest,
    DetectEquipmentResponse,
    InverterStructureOut,
    MappingSubmission,
    ModuleReadinessOut,
    PatternApplyRequest,
    PatternApplyResponse,
    PlantConfigSubmission,
    RetryValidationRequest,
    ScbStructureOut,
    SetupContextResponse,
    UploadArchitectureSummary,
    UploadFileInventoryItem,
    UploadHierarchyLevel,
    UploadModuleImpactPreview,
    UploadSignalCheckItem,
    ValidationIssueOut,
    ValidationResponse,
)
from backend.app.services import validation_service
from backend.app.services.job_service import get_runner
from backend.app.services.upload_intelligence import build_upload_intelligence
from backend.app.services.upload_inventory import inventory_from_job, signal_checklist
from backend.app.services.mapping_service import (
    detect_pack_match,
    mapping_payload,
    read_header,
    requires_manual_mapping,
    save_template,
    suggest_mapping,
    timestamp_column,
)
from backend.app.services.storage import job_paths
from backend.app.services.user_errors import (
    MSG_MISSING_RAW_UPLOAD,
    MSG_VALIDATE_FAILED,
    user_facing_message,
)

logger = logging.getLogger("pic_lite.intake")

router = APIRouter(prefix="/api", tags=["intake"])

# Analysis is mid-flight — do not accept setup edits until it finishes or fails.
_BLOCKED_WHILE_RUNNING = {
    JobState.QUEUED.value,
    JobState.RUNNING.value,
    JobState.GENERATING_CHARTS.value,
    JobState.GENERATING_REPORT.value,
}

# Setup revisions allowed (including after a finished or expired analysis).
_REVISABLE_STATES = {
    JobState.UPLOADED.value,
    JobState.PARSING.value,
    JobState.MAPPING.value,
    JobState.VALIDATING.value,
    JobState.NORMALIZING.value,
    JobState.FAILED.value,
    JobState.COMPLETED.value,
    JobState.CLEANED_UP.value,
}


def _setup_edit_blocked_message(state: str) -> str:
    if state in _BLOCKED_WHILE_RUNNING:
        return "Analysis is running. Wait for it to finish, then edit mapping or plant details."
    return f"Job is in state '{state}' and cannot accept setup changes right now."


def _get_job_or_404(db: Session, job_id: str, user: User | None = None) -> Job:
    return load_job_authorized(db, job_id, user)


def _assert_setup_editable(job: Job) -> None:
    if job.state in _BLOCKED_WHILE_RUNNING:
        raise HTTPException(409, _setup_edit_blocked_message(job.state))
    if job.state not in _REVISABLE_STATES:
        raise HTTPException(409, _setup_edit_blocked_message(job.state))


def _clear_analysis_outputs(settings: Settings, job: Job) -> None:
    """Drop stale results/reports so a revised job cannot serve old Completed artifacts."""
    paths = job_paths(settings.job_root_path, job.id)
    for d in (paths.results_dir, paths.reports_dir, paths.charts_dir):
        if d.exists():
            shutil.rmtree(d, ignore_errors=True)
        d.mkdir(parents=True, exist_ok=True)
    job.results_summary_json = None
    job.ai_integrity_json = None
    job.upload_integrity_json = None
    job.completed_at = None
    job.report_expires_at = None
    job.total_execution_time_ms = None
    job.downloaded_pdf = False
    job.downloaded_excel = False


def _reopen_for_revision(job: Job, settings: Settings, *, reason: str) -> bool:
    """If the job already finished (or has results), clear outputs and mark for re-validation.

    Returns True when prior analysis outputs were invalidated (UI should say re-run required).
    """
    had_results = bool(job.results_summary_json) or job.state == JobState.COMPLETED.value
    if had_results:
        _clear_analysis_outputs(settings, job)
        job.progress_message = reason
        job.error_summary = None
    return had_results


def _plant_fields_for_storage(payload: PlantConfigSubmission, existing_plant: dict | None = None) -> dict:
    """Serialize submission into the PlantConfig kwargs shape analytics expects."""
    plant_fields = payload.model_dump(
        exclude={
            "job_id",
            "threshold_overrides",
            "imported_equipment_ratings",
            "imported_inverter_capacity_kw",
            "imported_ac_capacity_mw",
            "imported_dc_capacity_mwp",
            "architecture_imported",
            "architecture_format",
        }
    )
    plant_fields["plant_type"] = normalize_plant_type(plant_fields.get("plant_type", "fixed_tilt"))
    # Drop ratings that are not positive; algorithms fall back to inverter_capacity_kw.
    plant_fields["equipment_ratings"] = {
        inv_id: float(kw) for inv_id, kw in (plant_fields.get("equipment_ratings") or {}).items() if kw and float(kw) > 0
    }
    # ArchitectureEntry dumps as nested dicts — strip empty optional keys so fallbacks work cleanly.
    arch_out: dict[str, dict] = {}
    for scb_id, entry in (plant_fields.get("architecture") or {}).items():
        if not isinstance(entry, dict):
            continue
        inv_id = str(entry.get("inverter_id") or "").strip()
        if not inv_id or not str(scb_id).strip():
            continue
        cleaned: dict = {"inverter_id": inv_id}
        if entry.get("strings_per_scb") is not None:
            cleaned["strings_per_scb"] = entry["strings_per_scb"]
        if entry.get("modules_per_string") is not None:
            cleaned["modules_per_string"] = entry["modules_per_string"]
        if entry.get("spare_flag"):
            cleaned["spare_flag"] = True
        if entry.get("dc_capacity_kwp") is not None:
            cleaned["dc_capacity_kwp"] = float(entry["dc_capacity_kwp"])
        if entry.get("ac_capacity_kw") is not None:
            cleaned["ac_capacity_kw"] = float(entry["ac_capacity_kw"])
        arch_out[str(scb_id).strip()] = cleaned
    plant_fields["architecture"] = arch_out

    # Prefer freshly submitted import snapshot (Excel upload on Setup); else keep prior pack snapshot.
    prior = existing_plant or {}
    if payload.imported_equipment_ratings:
        plant_fields.update(
            snapshot_imported_nameplate(
                {
                    "equipment_ratings": payload.imported_equipment_ratings,
                    "inverter_capacity_kw": payload.imported_inverter_capacity_kw,
                    "ac_capacity_mw": payload.imported_ac_capacity_mw,
                    "dc_capacity_mwp": payload.imported_dc_capacity_mwp,
                }
            )
        )
    else:
        for key in IMPORTED_NAMEPLATE_KEYS:
            if key in prior and prior[key] not in (None, "", {}, 0, 0.0):
                plant_fields[key] = prior[key]

    if payload.architecture_imported is not None:
        plant_fields["architecture_imported"] = payload.architecture_imported
    elif "architecture_imported" in prior:
        plant_fields["architecture_imported"] = prior["architecture_imported"]
    if payload.architecture_format:
        plant_fields["architecture_format"] = payload.architecture_format
    elif prior.get("architecture_format"):
        plant_fields["architecture_format"] = prior["architecture_format"]

    return plant_fields


@router.post("/mapping")
def submit_mapping(
    request: Request,
    payload: MappingSubmission,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    user: User | None = Depends(get_optional_user),
    _: None = Depends(enforce_csrf),
):
    job = _get_job_or_404(db, payload.job_id, user)
    _assert_setup_editable(job)
    revised = _reopen_for_revision(
        job,
        settings,
        reason="Column mapping updated — previous results cleared. Re-validate and re-run analysis.",
    )

    ts_col = timestamp_column(payload.column_to_canonical)
    if not ts_col:
        raise HTTPException(400, "A timestamp column must be mapped before analysis can proceed.")

    columns = list(payload.column_to_canonical.keys())
    save_template(db, columns, payload.column_to_canonical)

    job.mapping_json = mapping_payload(
        payload.column_to_canonical,
        timestamp_col=ts_col,
        column_hierarchy_levels=payload.column_hierarchy_levels,
    )
    job.state = JobState.MAPPING.value
    job.error_summary = None
    if not revised:
        job.progress_message = "Column mapping saved."
    db.add(job)
    db.commit()
    record_audit(
        db,
        action="job.mapping_save",
        user_id=user.id if user else None,
        job_id=job.id,
        ip=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )

    # Only validate when plant_config is complete enough for PlantConfig.
    # Pack import may store architecture early; Continue saves mapping first then plant —
    # validating here with an incomplete plant used to raise TypeError → HTTP 500.
    if validation_service.ready_for_validation(job):
        try:
            validation_service.run_validation_stage(db, job, settings)
            record_audit(
                db,
                action="job.validation",
                user_id=user.id if user else None,
                job_id=job.id,
                ip=client_ip(request),
                detail={"state": job.state},
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("validation after mapping failed for job=%s", job.id)
            raise HTTPException(
                400,
                user_facing_message(exc, fallback=MSG_VALIDATE_FAILED),
            ) from exc
    return {"job_id": job.id, "state": job.state, "requires_reanalysis": revised}


@router.post("/plant-config")
def submit_plant_config(
    request: Request,
    payload: PlantConfigSubmission,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    user: User | None = Depends(get_optional_user),
    _: None = Depends(enforce_csrf),
):
    job = _get_job_or_404(db, payload.job_id, user)
    _assert_setup_editable(job)
    revised = _reopen_for_revision(
        job,
        settings,
        reason="Plant / architecture updated — previous results cleared. Re-validate and re-run analysis.",
    )

    plant_fields = _plant_fields_for_storage(
        payload,
        existing_plant=(job.plant_config_json or {}).get("plant") if job.plant_config_json else None,
    )
    job.plant_config_json = {"plant": plant_fields, "threshold_overrides": payload.threshold_overrides}
    job.plant_name = payload.plant_name
    if not revised:
        job.progress_message = "Plant configuration saved."
    # Never leave COMPLETED after a plant-config edit — re-enter mapping until validation runs.
    if revised or job.state == JobState.COMPLETED.value:
        job.state = JobState.MAPPING.value
    db.add(job)
    db.commit()
    record_audit(
        db,
        action="job.plant_save",
        user_id=user.id if user else None,
        job_id=job.id,
        ip=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )

    if validation_service.ready_for_validation(job):
        try:
            validation_service.run_validation_stage(db, job, settings)
            record_audit(
                db,
                action="job.validation",
                user_id=user.id if user else None,
                job_id=job.id,
                ip=client_ip(request),
                detail={"state": job.state},
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("validation after plant-config failed for job=%s", job.id)
            raise HTTPException(
                400,
                user_facing_message(exc, fallback=MSG_VALIDATE_FAILED),
            ) from exc
    return {"job_id": job.id, "state": job.state, "requires_reanalysis": revised}


@router.get("/architecture-template")
def download_architecture_template(user: User = Depends(require_verified_user)):
    """Downloadable Excel template for large-plant architecture entry."""
    content = build_template_bytes()
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{TEMPLATE_FILENAME}"'},
    )


@router.post("/architecture-upload", response_model=ArchitectureUploadResponse)
async def upload_architecture_excel(
    file: UploadFile = File(...),
    user: User = Depends(require_verified_user),
    _: None = Depends(enforce_csrf),
):
    """Parse a filled architecture Excel into equipment_ratings + architecture + UI tree."""
    name = (file.filename or "").lower()
    if not name.endswith((".xlsx", ".xlsm")):
        raise HTTPException(400, "Upload an .xlsx architecture file (download the template first).")
    raw = await file.read()
    if not raw:
        raise HTTPException(400, "Uploaded file is empty.")
    parsed = parse_architecture_excel(raw)
    if parsed.errors:
        raise HTTPException(400, "; ".join(parsed.errors))

    inverter_ratings = {inv["inverter_id"]: inv.get("rated_kw") for inv in parsed.inverters}
    return ArchitectureUploadResponse(
        equipment_ratings=parsed.equipment_ratings,
        architecture={
            scb_id: {
                "inverter_id": entry["inverter_id"],
                "strings_per_scb": entry.get("strings_per_scb"),
                **({"dc_capacity_kwp": entry["dc_capacity_kwp"]} if entry.get("dc_capacity_kwp") is not None else {}),
                **({"ac_capacity_kw": entry["ac_capacity_kw"]} if entry.get("ac_capacity_kw") is not None else {}),
            }
            for scb_id, entry in parsed.architecture.items()
        },
        inverters=[
            InverterStructureOut(
                inverter_id=inv["inverter_id"],
                scbs=[
                    ScbStructureOut(
                        scb_id=s["scb_id"],
                        strings_per_scb=s.get("strings_per_scb"),
                        strings_detected=bool(s.get("strings_detected")),
                    )
                    for s in inv.get("scbs", [])
                ],
            )
            for inv in parsed.inverters
        ],
        notes=parsed.notes,
        row_count=parsed.row_count,
        inverter_ratings=inverter_ratings,
        plant_name=parsed.plant_name,
        ac_capacity_mw=parsed.ac_capacity_mw,
        dc_capacity_mwp=parsed.dc_capacity_mwp,
        inverter_capacity_kw=parsed.inverter_capacity_kw,
    )


@router.post("/architecture-pattern", response_model=PatternApplyResponse)
def apply_architecture_pattern(
    payload: PatternApplyRequest,
    user: User = Depends(require_verified_user),
    _: None = Depends(enforce_csrf),
):
    """Compact bulk pattern: N SMBs × M strings for selected/all inverters."""
    if not payload.inverter_ids:
        raise HTTPException(400, "Provide at least one inverter_id (or generate IDs first).")
    try:
        inverters = apply_smb_pattern(
            payload.inverter_ids,
            smbs_per_inverter=payload.smbs_per_inverter,
            strings_per_smb=payload.strings_per_smb,
            rated_kw=payload.rated_kw,
            existing=payload.existing_inverters or None,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    n_scb = sum(len(inv.get("scbs") or []) for inv in inverters)
    notes = [
        f"Applied pattern: {payload.smbs_per_inverter} SMB(s) × {payload.strings_per_smb} string(s) "
        f"on {len(payload.inverter_ids)} inverter(s) → {n_scb} SCB rows total in structure."
    ]
    return PatternApplyResponse(inverters=inverters, notes=notes)


@router.post("/detect-equipment", response_model=DetectEquipmentResponse)
def detect_equipment(
    payload: DetectEquipmentRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    user: User | None = Depends(get_optional_user),
    _: None = Depends(enforce_csrf),
):
    """Peek at mapped equipment ID columns and return inverter → SCB → string counts."""
    job = _get_job_or_404(db, payload.job_id, user)
    paths = job_paths(settings.job_root_path, job.id)
    csv_path = validation_service.resolve_raw_input_csv(paths)
    if csv_path is None:
        raise HTTPException(404, MSG_MISSING_RAW_UPLOAD)

    structure = infer_from_csv(csv_path, payload.column_to_canonical)
    api = structure.to_api_dict()
    return DetectEquipmentResponse(
        detected=api["detected"],
        source=api.get("source"),
        unique_id_count=api.get("unique_id_count", 0),
        notes=api.get("notes", []),
        inverters=[
            InverterStructureOut(
                inverter_id=inv["inverter_id"],
                scbs=[ScbStructureOut(**scb) for scb in inv.get("scbs", [])],
            )
            for inv in api.get("inverters", [])
        ],
    )


@router.get("/jobs/{job_id}/setup-context", response_model=SetupContextResponse)
def get_setup_context(
    job_id: str,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    user: User | None = Depends(get_optional_user),
):
    """Reload Setup without re-uploading — used after validation recovery / page reload."""
    job = _get_job_or_404(db, job_id, user)
    paths = job_paths(settings.job_root_path, job.id)
    csv_path = validation_service.resolve_raw_input_csv(paths)

    # Excel still converting in background — UI polls until state advances.
    if job.state == JobState.PARSING.value and csv_path is None:
        return SetupContextResponse(
            job_id=job.id,
            state=job.state,
            detected_columns=[],
            mapping_suggestions=[],
            requires_manual_mapping=True,
            current_mapping={},
            plant_config=(job.plant_config_json or {}).get("plant") if job.plant_config_json else None,
            looks_like_complete_pack=False,
            pack_match_ratio=0.0,
        )

    if csv_path is None:
        if job.state == JobState.FAILED.value:
            raise HTTPException(
                404,
                user_facing_message(
                    job.error_summary or MSG_MISSING_RAW_UPLOAD,
                    fallback=MSG_MISSING_RAW_UPLOAD,
                ),
            )
        raise HTTPException(404, MSG_MISSING_RAW_UPLOAD)

    columns = read_header(csv_path)
    pack_match, pack_ratio = detect_pack_match(columns)
    suggestions = suggest_mapping(columns, pack_match=pack_match)
    current = dict((job.mapping_json or {}).get("column_to_canonical") or {})
    # Overlay saved mapping onto suggestions so the UI preserves prior choices
    for s in suggestions:
        if s.column_name in current:
            s.canonical_field = current[s.column_name]
            s.confidence = max(s.confidence, 0.99)
            s.band = "confirm"  # always editable on recovery
        elif (s.column_name or "").lower().startswith("unnamed") or (s.column_name or "").lower().startswith("column_"):
            s.canonical_field = None
            s.confidence = 0.0
            s.band = "manual"

    plant = None
    if job.plant_config_json:
        plant = job.plant_config_json.get("plant")

    needs_manual = requires_manual_mapping(suggestions)
    if not pack_match:
        needs_manual = True

    file_inv, total_rows = inventory_from_job(paths, job.original_filename)
    if not total_rows and csv_path.exists():
        try:
            import pandas as pd

            total_rows = max(0, len(pd.read_csv(csv_path, usecols=[0])))
        except Exception:  # noqa: BLE001
            total_rows = 0

    checklist = signal_checklist(suggestions, plant_config=plant or {})

    reshape_report = None
    reshape_path = paths.raw_dir / "wide_reshape_report.json"
    if reshape_path.exists():
        try:
            reshape_report = json.loads(reshape_path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            reshape_report = None

    intelligence = build_upload_intelligence(
        suggestions=suggestions,
        plant_config=plant,
        csv_path=csv_path,
        file_inventory=file_inv,
        reshape_report=reshape_report,
        column_names=columns,
    )
    file_inv = intelligence["file_inventory"]

    return SetupContextResponse(
        job_id=job.id,
        state=job.state,
        detected_columns=columns,
        mapping_suggestions=suggestions,
        requires_manual_mapping=needs_manual,
        current_mapping=current,
        plant_config=plant,
        looks_like_complete_pack=pack_match,
        pack_match_ratio=pack_ratio,
        file_inventory=[UploadFileInventoryItem(**f) for f in file_inv],
        total_rows=total_rows,
        signal_checklist=[UploadSignalCheckItem(**c) for c in checklist],
        hierarchy_overview=[UploadHierarchyLevel(**h) for h in intelligence["hierarchy_overview"]],
        architecture_summary=UploadArchitectureSummary(**intelligence["architecture_summary"]),
        module_impact_preview=UploadModuleImpactPreview(**intelligence["module_impact_preview"]),
        original_filename=job.original_filename,
    )


@router.get("/jobs/{job_id}/validation", response_model=ValidationResponse)
def get_validation(
    job_id: str,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_optional_user),
):
    job = _get_job_or_404(db, job_id, user)
    summary = job.validation_summary_json or {}
    blockers = [ValidationIssueOut(**b) for b in summary.get("blockers", [])]
    warnings = [ValidationIssueOut(**w) for w in summary.get("warnings", [])]
    readiness = [ModuleReadinessOut(**r) for r in summary.get("module_readiness", [])]
    return ValidationResponse(
        job_id=job.id,
        row_count=summary.get("row_count", 0),
        column_count=summary.get("column_count", 0),
        detected_interval_minutes=summary.get("detected_interval_minutes") or 0.0,
        is_irregular_interval=summary.get("is_irregular_interval", False),
        interval_notes=summary.get("interval_notes", []),
        blockers=blockers,
        warnings=warnings,
        can_proceed=job.state == JobState.NORMALIZING.value and not blockers,
        module_readiness=readiness,
        timestamp_column=summary.get("timestamp_column") or (job.mapping_json or {}).get("timestamp_column"),
        timestamp_parse_ok=summary.get("timestamp_parse_ok", 0),
        timestamp_parse_fail=summary.get("timestamp_parse_fail", 0),
        can_proceed_with_row_drops=summary.get("can_proceed_with_row_drops", False),
        proceed_with_drops_min_ok_ratio=summary.get("proceed_with_drops_min_ok_ratio", 0.80),
        recovery_actions=summary.get("recovery_actions", []),
        rows_that_would_be_dropped=summary.get("rows_that_would_be_dropped", 0),
        rows_that_would_be_kept=summary.get("rows_that_would_be_kept", 0),
        state=job.state,
    )


@router.post("/jobs/{job_id}/retry-validation")
def retry_validation(
    job_id: str,
    request: Request,
    payload: RetryValidationRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    user: User | None = Depends(get_optional_user),
    _: None = Depends(enforce_csrf),
):
    """Re-run validation on the existing upload (after remapping or to drop bad rows)."""
    job = _get_job_or_404(db, job_id, user)
    _assert_setup_editable(job)
    if job.state == JobState.COMPLETED.value:
        _reopen_for_revision(
            job,
            settings,
            reason="Re-validating after setup changes — previous results cleared.",
        )
        job.state = JobState.MAPPING.value
        db.add(job)
        db.commit()
    if not validation_service.ready_for_validation(job):
        raise HTTPException(400, "Mapping and plant config are required before validation.")

    summary = job.validation_summary_json or {}
    if payload.drop_unparseable_timestamps and not summary.get("can_proceed_with_row_drops"):
        raise HTTPException(
            400,
            "Cannot drop unparseable rows: fewer than 80% of timestamps parse successfully. "
            "Fix column mapping instead.",
        )

    try:
        validation_service.run_validation_stage(
            db,
            job,
            settings,
            drop_unparseable_timestamps=payload.drop_unparseable_timestamps,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("retry-validation failed for job=%s", job.id)
        raise HTTPException(
            400,
            user_facing_message(exc, fallback=MSG_VALIDATE_FAILED),
        ) from exc
    record_audit(
        db,
        action="job.validation",
        user_id=user.id if user else None,
        job_id=job.id,
        ip=client_ip(request),
        detail={"retry": True, "state": job.state},
    )
    return {"job_id": job.id, "state": job.state}


@router.post("/jobs/{job_id}/acknowledge")
def acknowledge_warnings(
    job_id: str,
    request: Request,
    payload: AcknowledgeWarningsRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    user: User | None = Depends(get_optional_user),
    _: None = Depends(enforce_csrf),
):
    job = _get_job_or_404(db, job_id, user)
    if not payload.acknowledged:
        raise HTTPException(400, "Warnings must be acknowledged to proceed.")

    # Recovery: drop bad timestamps then queue if validation becomes clean enough
    if payload.drop_unparseable_timestamps:
        summary = job.validation_summary_json or {}
        if not summary.get("can_proceed_with_row_drops"):
            raise HTTPException(
                400,
                "Cannot proceed with row drops: fewer than 80% of timestamps parse OK. Fix mapping instead.",
            )
        if not validation_service.ready_for_validation(job):
            raise HTTPException(400, "Mapping and plant config are required.")
        try:
            validation_service.run_validation_stage(
                db, job, settings, drop_unparseable_timestamps=True
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("validation during acknowledge failed for job=%s", job.id)
            raise HTTPException(
                400,
                user_facing_message(exc, fallback=MSG_VALIDATE_FAILED),
            ) from exc
        db.refresh(job)
        if job.state != JobState.NORMALIZING.value:
            raise HTTPException(409, "Validation still has blockers after dropping unparseable rows.")

    if job.state != JobState.NORMALIZING.value:
        raise HTTPException(409, f"Job is in state '{job.state}' and cannot be queued for analysis yet.")

    job.state = JobState.QUEUED.value
    job.progress_message = (
        "Queued — other analyses may be running in parallel; yours starts when a worker is free."
    )
    db.add(job)
    db.commit()
    record_audit(
        db,
        action="analysis.start",
        user_id=user.id if user else None,
        job_id=job.id,
        ip=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )

    get_runner(settings).submit(job.id)
    return {"job_id": job.id, "state": job.state}
