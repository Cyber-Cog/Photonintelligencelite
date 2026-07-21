"""Shared job lookup + ownership checks for gated routers."""
from __future__ import annotations

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from backend.app.auth.deps import get_optional_user, require_job_access
from backend.app.database import get_db
from backend.app.models import Job, User


def get_job_for_request(
    job_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_optional_user),
) -> tuple[Job, User | None]:
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(404, "Job not found. It may have already been cleaned up.")
    require_job_access(job, user, allow_demo_anonymous=True)
    return job, user


def load_job_authorized(db: Session, job_id: str, user: User | None) -> Job:
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(404, "Job not found. It may have already been cleaned up.")
    require_job_access(job, user, allow_demo_anonymous=True)
    return job
