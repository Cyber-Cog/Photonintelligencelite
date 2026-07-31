"""Dashboard results endpoint. See docs/PRD.md §7.10."""
from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from analytics.core.job_states import JobState
from backend.app.auth.deps import enforce_csrf, get_optional_user, require_superadmin
from backend.app.auth.job_access import load_job_authorized
from backend.app.config import Settings, get_settings
from backend.app.database import get_db
from backend.app.models import User
from backend.app.schemas import AiIntegrityCheck, KpiResponse, ResultsResponse
from backend.app.services.fault_run_ai_check import (
    ai_check_configured,
    run_fault_run_integrity_check,
    skipped_result,
)
from backend.app.services.storage import job_paths

router = APIRouter(prefix="/api", tags=["results"])
logger = logging.getLogger("pic_lite.results")

_RESULTS_GONE = (
    "These results have expired. Upload your SCADA file and run analysis again."
)


def _integrity_from_job(job) -> AiIntegrityCheck | None:
    raw = job.ai_integrity_json
    if not isinstance(raw, dict):
        return None
    try:
        return AiIntegrityCheck(**raw)
    except Exception:  # noqa: BLE001
        return None


@router.get("/jobs/{job_id}/results", response_model=ResultsResponse)
def get_results(
    job_id: str,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    user: User | None = Depends(get_optional_user),
):
    job = load_job_authorized(db, job_id, user)
    if job.state == JobState.CLEANED_UP.value:
        raise HTTPException(410, _RESULTS_GONE)
    if job.state != JobState.COMPLETED.value:
        raise HTTPException(409, f"Job is in state '{job.state}'. Results are only available once completed.")

    paths = job_paths(settings.job_root_path, job_id)
    results_path = paths.results_dir / "results.json"
    if not results_path.exists():
        # DB row can still be COMPLETED while files are gone (Render /tmp wipe on restart).
        raise HTTPException(410, _RESULTS_GONE)

    payload = json.loads(results_path.read_text(encoding="utf-8"))
    return ResultsResponse(
        job_id=job_id,
        kpis=KpiResponse(**payload["kpis"]),
        results=payload["results"],
        ai_integrity=_integrity_from_job(job),
    )


@router.get("/jobs/{job_id}/ai-integrity", response_model=AiIntegrityCheck)
def get_ai_integrity(
    job_id: str,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_optional_user),
):
    job = load_job_authorized(db, job_id, user)
    if job.state != JobState.COMPLETED.value:
        raise HTTPException(409, f"Job is in state '{job.state}'. Integrity check requires completed analysis.")
    stored = _integrity_from_job(job)
    if stored is not None:
        return stored
    if not ai_check_configured(get_settings()):
        return AiIntegrityCheck(**skipped_result())
    return AiIntegrityCheck(
        status="pass",
        configured=True,
        source="none",
        ai_layer="skipped",
        rules_finding_count=0,
        summary="Integrity check has not been run yet.",
        findings=[],
    )


@router.post(
    "/jobs/{job_id}/ai-integrity",
    response_model=AiIntegrityCheck,
    dependencies=[Depends(enforce_csrf)],
)
def rerun_ai_integrity(
    job_id: str,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    user: User = Depends(require_superadmin),
):
    """Re-run integrity check (superadmin). Stores result on the job."""
    _ = user
    job = load_job_authorized(db, job_id, user)
    if job.state != JobState.COMPLETED.value:
        raise HTTPException(409, f"Job is in state '{job.state}'. Integrity check requires completed analysis.")

    paths = job_paths(settings.job_root_path, job_id)
    results_path = paths.results_dir / "results.json"
    if not results_path.exists():
        raise HTTPException(410, _RESULTS_GONE)

    payload = json.loads(results_path.read_text(encoding="utf-8"))
    try:
        check = run_fault_run_integrity_check(
            settings,
            results=payload.get("results") or [],
            kpis=payload.get("kpis") or {},
            results_summary=job.results_summary_json if isinstance(job.results_summary_json, dict) else None,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("ai integrity re-run failed job=%s", job_id)
        raise HTTPException(500, f"Integrity check failed: {exc}") from exc

    job.ai_integrity_json = check
    db.commit()
    return AiIntegrityCheck(**check)
