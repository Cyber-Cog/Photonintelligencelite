"""Report downloads. Cleanup fires once both PDF and Excel have been downloaded at least
once, or at TTL expiry — whichever comes first (docs/PRD.md §7.12, §0)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from starlette.background import BackgroundTask

from analytics.core.job_states import JobState
from backend.app.auth.audit import record_audit
from backend.app.auth.deps import get_optional_user
from backend.app.auth.job_access import load_job_authorized
from backend.app.auth.rate_limit import client_ip
from backend.app.config import Settings, get_settings
from backend.app.database import get_db
from backend.app.models import User
from backend.app.services.cleanup_service import cleanup_after_download
from backend.app.services.storage import job_paths

router = APIRouter(prefix="/api", tags=["reports"])


def _serve(
    job_id: str,
    db: Session,
    settings: Settings,
    filename: str,
    media_type: str,
    mark_field: str,
    *,
    user: User | None,
    request: Request,
    action: str,
):
    job = load_job_authorized(db, job_id, user)
    if job.state != JobState.COMPLETED.value:
        raise HTTPException(409, f"Job is in state '{job.state}'. Reports are only available once completed.")

    paths = job_paths(settings.job_root_path, job_id)
    file_path = paths.reports_dir / filename
    if not file_path.exists():
        raise HTTPException(410, "This report is no longer available (cleaned up after its download window).")

    setattr(job, mark_field, True)
    db.add(job)
    db.commit()
    record_audit(
        db,
        action=action,
        user_id=user.id if user else None,
        job_id=job_id,
        ip=client_ip(request),
        user_agent=request.headers.get("user-agent"),
        detail={"format": filename.split(".")[-1]},
    )

    # Cleanup must run AFTER the file is streamed — FileResponse reads lazily, so deleting
    # in-request causes 500 on the second (final) report download.
    background = None
    if job.downloaded_pdf and job.downloaded_excel:
        background = BackgroundTask(cleanup_after_download, settings, job_id)

    return FileResponse(file_path, media_type=media_type, filename=filename, background=background)


@router.get("/jobs/{job_id}/report.pdf")
def download_pdf(
    job_id: str,
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    user: User | None = Depends(get_optional_user),
):
    return _serve(
        job_id,
        db,
        settings,
        "report.pdf",
        "application/pdf",
        "downloaded_pdf",
        user=user,
        request=request,
        action="report.download_pdf",
    )


@router.get("/jobs/{job_id}/report.xlsx")
def download_excel(
    job_id: str,
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    user: User | None = Depends(get_optional_user),
):
    return _serve(
        job_id,
        db,
        settings,
        "report.xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "downloaded_excel",
        user=user,
        request=request,
        action="report.download_excel",
    )
