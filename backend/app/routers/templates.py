"""Downloadable data-format templates (Complete Analysis Pack)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session

from analytics.common.complete_analysis_pack import (
    EXCEL_FILENAME,
    ZIP_FILENAME,
    build_excel_bytes,
    build_zip_bytes,
)
from backend.app.auth.audit import record_audit
from backend.app.auth.deps import enforce_csrf, require_verified_user
from backend.app.auth.rate_limit import client_ip
from backend.app.database import get_db
from backend.app.models import User

router = APIRouter(prefix="/api/templates", tags=["templates"])


@router.get("/complete-analysis")
def download_complete_analysis_excel(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_verified_user),
):
    """Official multi-sheet Excel pack (README + scada + architecture + checklist)."""
    content = build_excel_bytes()
    record_audit(
        db,
        action="template.download",
        user_id=user.id,
        ip=client_ip(request),
        user_agent=request.headers.get("user-agent"),
        detail={"format": "excel"},
    )
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{EXCEL_FILENAME}"'},
    )


@router.get("/complete-analysis.zip")
def download_complete_analysis_zip(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_verified_user),
):
    """ZIP of long SCADA CSV + matching architecture Excel + README."""
    content = build_zip_bytes()
    record_audit(
        db,
        action="template.download",
        user_id=user.id,
        ip=client_ip(request),
        user_agent=request.headers.get("user-agent"),
        detail={"format": "zip"},
    )
    return Response(
        content=content,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{ZIP_FILENAME}"'},
    )


# GET downloads do not need CSRF; keep import for consistency with mutating routes
_ = enforce_csrf
