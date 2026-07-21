"""Audit event recording for superadmin intel."""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from backend.app.models import AuditEvent


def record_audit(
    db: Session,
    *,
    action: str,
    user_id: str | None = None,
    job_id: str | None = None,
    ip: str | None = None,
    user_agent: str | None = None,
    detail: dict[str, Any] | None = None,
    commit: bool = True,
) -> AuditEvent:
    event = AuditEvent(
        action=action,
        user_id=user_id,
        job_id=job_id,
        ip=ip,
        user_agent=(user_agent or "")[:500] or None,
        detail_json=detail or {},
    )
    db.add(event)
    if commit:
        db.commit()
    return event
