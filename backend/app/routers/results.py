"""Dashboard results endpoint. See docs/PRD.md §7.10."""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from analytics.core.job_states import JobState
from backend.app.auth.deps import get_optional_user
from backend.app.auth.job_access import load_job_authorized
from backend.app.config import Settings, get_settings
from backend.app.database import get_db
from backend.app.models import User
from backend.app.schemas import KpiResponse, ResultsResponse
from backend.app.services.storage import job_paths

router = APIRouter(prefix="/api", tags=["results"])


@router.get("/jobs/{job_id}/results", response_model=ResultsResponse)
def get_results(
    job_id: str,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    user: User | None = Depends(get_optional_user),
):
    job = load_job_authorized(db, job_id, user)
    if job.state != JobState.COMPLETED.value:
        raise HTTPException(409, f"Job is in state '{job.state}'. Results are only available once completed.")

    paths = job_paths(settings.job_root_path, job_id)
    results_path = paths.results_dir / "results.json"
    if not results_path.exists():
        raise HTTPException(410, "Results are no longer available for this job (cleaned up).")

    payload = json.loads(results_path.read_text(encoding="utf-8"))
    return ResultsResponse(job_id=job_id, kpis=KpiResponse(**payload["kpis"]), results=payload["results"])
