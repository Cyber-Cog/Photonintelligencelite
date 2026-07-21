"""Job status polling. Locked at 2-3 second client-side polling, no SSE/WebSocket
(docs/PRD.md §0, §7.10).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from analytics.core.job_states import JobState
from backend.app.auth.deps import get_optional_user
from backend.app.auth.job_access import load_job_authorized
from backend.app.config import Settings, get_settings
from backend.app.database import get_db
from backend.app.models import User
from backend.app.schemas import JobStatusResponse
from backend.app.services.job_service import get_runner

router = APIRouter(prefix="/api", tags=["jobs"])


@router.get("/jobs/{job_id}/status", response_model=JobStatusResponse)
def get_status(
    job_id: str,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    user: User | None = Depends(get_optional_user),
):
    job = load_job_authorized(db, job_id, user)

    runner = get_runner(settings)
    state = JobState(job.state)
    progress_message = job.progress_message
    # Self-heal: DB says queued but in-memory pool lost the id (failed reload / crash mid-submit).
    if state == JobState.QUEUED:
        rewritten = runner.ensure_queued(job.id, progress_message=progress_message)
        if rewritten:
            progress_message = rewritten
    return JobStatusResponse(
        job_id=job.id,
        state=job.state,
        progress_message=progress_message,
        error_summary=job.error_summary,
        created_at=job.created_at.isoformat(),
        updated_at=job.updated_at.isoformat(),
        queue_position=runner.queue_position(job.id),
        estimated_wait_seconds=runner.estimated_wait_seconds(job.id),
        is_active=state.is_active,
    )
