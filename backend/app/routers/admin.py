"""Superadmin audit / client intel UI APIs."""
from __future__ import annotations

import hashlib
import logging
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.app.auth.audit import record_audit
from backend.app.auth.deps import enforce_csrf, require_superadmin
from backend.app.auth.email import send_password_reset_email, send_verification_email, smtp_configured
from backend.app.auth.rate_limit import client_ip
from backend.app.config import Settings, get_settings
from backend.app.database import get_db
from backend.app.models import AuditEvent, AuthSession, EmailToken, Job, User
from backend.app.schemas_auth import (
    AdminJobOut,
    AdminSessionOut,
    AdminUserOut,
    AdminUserUpdateRequest,
    AuditEventOut,
    FunnelStats,
    MessageResponse,
)

logger = logging.getLogger("pic_lite.admin")
router = APIRouter(prefix="/api/admin", tags=["admin"])

DELETED_EMAIL_SUFFIX = "@deleted.local"


def _issue_email_token(db: Session, user: User, purpose: str, hours: int = 48) -> str:
    raw = secrets.token_urlsafe(32)
    row = EmailToken(
        user_id=user.id,
        token_hash=hashlib.sha256(raw.encode("utf-8")).hexdigest(),
        purpose=purpose,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=hours),
    )
    db.add(row)
    db.commit()
    return raw


def _iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def _job_counts(db: Session) -> dict[str, int]:
    return dict(
        db.query(Job.user_id, func.count(Job.id)).filter(Job.user_id.isnot(None)).group_by(Job.user_id).all()
    )


def _admin_user_out(u: User, counts: dict[str, int] | None = None) -> AdminUserOut:
    job_count = 0
    if counts is not None:
        job_count = int(counts.get(u.id, 0))
    return AdminUserOut(
        id=u.id,
        email=u.email,
        name=u.name or "",
        role=u.role,
        email_verified=u.email_verified,
        is_active=u.is_active,
        created_at=_iso(u.created_at) or "",
        last_login_at=_iso(u.last_login_at),
        job_count=job_count,
    )


def _active_superadmin_count(db: Session) -> int:
    return (
        db.query(func.count(User.id))
        .filter(User.role == "superadmin", User.is_active.is_(True))
        .scalar()
        or 0
    )


def _revoke_user_sessions(db: Session, user_id: str) -> int:
    now = datetime.now(timezone.utc)
    rows = (
        db.query(AuthSession)
        .filter(AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None))
        .all()
    )
    for row in rows:
        row.revoked_at = now
        db.add(row)
    return len(rows)


def _get_target_user(db: Session, user_id: str) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(404, "User not found.")
    return user


@router.get("/users", response_model=list[AdminUserOut])
def list_users(
    db: Session = Depends(get_db),
    _: User = Depends(require_superadmin),
):
    users = (
        db.query(User)
        .filter(~User.email.endswith(DELETED_EMAIL_SUFFIX))
        .order_by(User.created_at.desc())
        .limit(500)
        .all()
    )
    counts = _job_counts(db)
    return [_admin_user_out(u, counts) for u in users]


@router.patch("/users/{user_id}", response_model=AdminUserOut)
def update_user(
    user_id: str,
    payload: AdminUserUpdateRequest,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_superadmin),
    _: None = Depends(enforce_csrf),
):
    target = _get_target_user(db, user_id)
    changes: dict = {}

    if payload.name is not None and payload.name != (target.name or ""):
        changes["name"] = {"from": target.name or "", "to": payload.name}
        target.name = payload.name

    if payload.role is not None and payload.role != target.role:
        if payload.role not in ("user", "superadmin"):
            raise HTTPException(400, "Role must be 'user' or 'superadmin'.")
        if target.id == admin.id and payload.role != "superadmin":
            raise HTTPException(400, "You cannot demote yourself.")
        if (
            target.role == "superadmin"
            and payload.role != "superadmin"
            and target.is_active
            and _active_superadmin_count(db) <= 1
        ):
            raise HTTPException(400, "Cannot demote the last remaining superadmin.")
        changes["role"] = {"from": target.role, "to": payload.role}
        target.role = payload.role

    if payload.is_active is not None and payload.is_active != target.is_active:
        if target.id == admin.id and not payload.is_active:
            raise HTTPException(400, "You cannot ban yourself.")
        if (
            not payload.is_active
            and target.role == "superadmin"
            and target.is_active
            and _active_superadmin_count(db) <= 1
        ):
            raise HTTPException(400, "Cannot ban the last remaining superadmin.")
        changes["is_active"] = {"from": target.is_active, "to": payload.is_active}
        target.is_active = payload.is_active
        if not payload.is_active:
            _revoke_user_sessions(db, target.id)

    if payload.email_verified is not None and payload.email_verified != target.email_verified:
        changes["email_verified"] = {"from": target.email_verified, "to": payload.email_verified}
        target.email_verified = payload.email_verified

    if not changes:
        return _admin_user_out(target, _job_counts(db))

    db.add(target)
    db.commit()
    db.refresh(target)

    action = "admin.user_updated"
    if "is_active" in changes:
        action = "admin.user_banned" if not changes["is_active"]["to"] else "admin.user_unbanned"
    elif "role" in changes and len(changes) == 1:
        action = "admin.user_role_changed"

    record_audit(
        db,
        action=action,
        user_id=admin.id,
        ip=client_ip(request),
        user_agent=request.headers.get("user-agent"),
        detail={"target_user_id": target.id, "target_email": target.email, "changes": changes},
    )
    return _admin_user_out(target, _job_counts(db))


@router.delete("/users/{user_id}", response_model=MessageResponse)
def delete_user(
    user_id: str,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_superadmin),
    _: None = Depends(enforce_csrf),
):
    target = _get_target_user(db, user_id)
    if target.id == admin.id:
        raise HTTPException(400, "You cannot delete yourself.")
    if target.role == "superadmin" and target.is_active and _active_superadmin_count(db) <= 1:
        raise HTTPException(400, "Cannot delete the last remaining superadmin.")

    email = target.email
    target_id = target.id
    _revoke_user_sessions(db, target_id)
    # Soft-delete: deactivate + anonymize so FK history (jobs/audit) stays useful.
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    target.is_active = False
    target.email = f"deleted-{target_id[:8]}-{stamp}{DELETED_EMAIL_SUFFIX}"
    target.name = "Deleted User"
    target.password_hash = "!"  # unusable hash
    target.role = "user" if target.role == "superadmin" else target.role
    db.add(target)
    db.query(EmailToken).filter(EmailToken.user_id == target_id).delete(synchronize_session=False)
    db.commit()

    record_audit(
        db,
        action="admin.user_deleted",
        user_id=admin.id,
        ip=client_ip(request),
        user_agent=request.headers.get("user-agent"),
        detail={"target_user_id": target_id, "target_email": email, "soft_delete": True},
    )
    return MessageResponse(message="User deleted.")


@router.post("/users/{user_id}/force-verify", response_model=AdminUserOut)
def force_verify_user(
    user_id: str,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_superadmin),
    _: None = Depends(enforce_csrf),
):
    target = _get_target_user(db, user_id)
    if not target.email_verified:
        target.email_verified = True
        db.add(target)
        db.commit()
        db.refresh(target)
        record_audit(
            db,
            action="admin.user_force_verified",
            user_id=admin.id,
            ip=client_ip(request),
            user_agent=request.headers.get("user-agent"),
            detail={"target_user_id": target.id, "target_email": target.email},
        )
    return _admin_user_out(target, _job_counts(db))


@router.post("/users/{user_id}/resend-reset", response_model=MessageResponse)
def resend_password_reset(
    user_id: str,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_superadmin),
    settings: Settings = Depends(get_settings),
    _: None = Depends(enforce_csrf),
):
    target = _get_target_user(db, user_id)
    if not target.is_active:
        raise HTTPException(400, "Cannot reset password for a banned user.")
    token = _issue_email_token(db, target, "reset", hours=2)
    reset_link = send_password_reset_email(settings, to=target.email, token=token)
    logger.info("Admin-issued password reset for %s: %s", target.email, reset_link)
    record_audit(
        db,
        action="admin.user_reset_requested",
        user_id=admin.id,
        ip=client_ip(request),
        user_agent=request.headers.get("user-agent"),
        detail={"target_user_id": target.id, "target_email": target.email},
    )
    return MessageResponse(
        message="Password reset link issued.",
        reset_link=reset_link if not smtp_configured(settings) else None,
    )


@router.post("/users/{user_id}/resend-verification", response_model=MessageResponse)
def resend_verification_admin(
    user_id: str,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_superadmin),
    settings: Settings = Depends(get_settings),
    _: None = Depends(enforce_csrf),
):
    target = _get_target_user(db, user_id)
    if target.email_verified:
        return MessageResponse(message="Email is already verified.")
    if not target.is_active:
        raise HTTPException(400, "Cannot resend verification for a banned user.")
    token = _issue_email_token(db, target, "verify")
    link = send_verification_email(settings, to=target.email, token=token)
    logger.info("Admin-resent verification for %s: %s", target.email, link)
    record_audit(
        db,
        action="admin.user_verification_resent",
        user_id=admin.id,
        ip=client_ip(request),
        user_agent=request.headers.get("user-agent"),
        detail={"target_user_id": target.id, "target_email": target.email},
    )
    return MessageResponse(
        message="Verification email sent.",
        verification_link=link if not smtp_configured(settings) else None,
    )


@router.get("/sessions", response_model=list[AdminSessionOut])
def list_sessions(
    db: Session = Depends(get_db),
    _: User = Depends(require_superadmin),
):
    rows = (
        db.query(AuthSession, User.email)
        .outerjoin(User, User.id == AuthSession.user_id)
        .order_by(AuthSession.created_at.desc())
        .limit(300)
        .all()
    )
    out: list[AdminSessionOut] = []
    for session, email in rows:
        out.append(
            AdminSessionOut(
                id=session.id,
                user_id=session.user_id,
                user_email=email,
                created_at=_iso(session.created_at) or "",
                expires_at=_iso(session.expires_at) or "",
                revoked_at=_iso(session.revoked_at),
                ip=session.ip,
                user_agent=session.user_agent,
            )
        )
    return out


@router.get("/jobs", response_model=list[AdminJobOut])
def list_jobs(
    db: Session = Depends(get_db),
    _: User = Depends(require_superadmin),
):
    rows = (
        db.query(Job, User.email)
        .outerjoin(User, User.id == Job.user_id)
        .order_by(Job.created_at.desc())
        .limit(500)
        .all()
    )
    return [
        AdminJobOut(
            id=job.id,
            state=job.state,
            user_id=job.user_id,
            user_email=email,
            is_demo=bool(job.is_demo),
            original_filename=job.original_filename,
            plant_name=job.plant_name,
            created_at=_iso(job.created_at) or "",
            completed_at=_iso(job.completed_at),
            abandoned_at=_iso(job.abandoned_at),
        )
        for job, email in rows
    ]


@router.get("/funnel", response_model=FunnelStats)
def funnel_stats(
    db: Session = Depends(get_db),
    _: User = Depends(require_superadmin),
):
    def count_state(*states: str) -> int:
        return db.query(func.count(Job.id)).filter(Job.state.in_(states)).scalar() or 0

    return FunnelStats(
        uploaded=count_state("uploaded", "parsing", "mapping"),
        mapping=count_state("mapping"),
        validating=count_state("validating", "normalizing"),
        queued_or_running=count_state("queued", "running", "generating_charts", "generating_report"),
        completed=count_state("completed", "cleaned_up"),
        failed=count_state("failed"),
        abandoned=db.query(func.count(Job.id)).filter(Job.abandoned_at.isnot(None)).scalar() or 0,
        demo=db.query(func.count(Job.id)).filter(Job.is_demo.is_(True)).scalar() or 0,
    )


@router.get("/audit", response_model=list[AuditEventOut])
def audit_log(
    action: str | None = Query(default=None),
    user_id: str | None = Query(default=None),
    job_id: str | None = Query(default=None),
    q: str | None = Query(default=None, description="Substring match on action"),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    _: User = Depends(require_superadmin),
):
    query = db.query(AuditEvent)
    if action:
        query = query.filter(AuditEvent.action == action)
    if user_id:
        query = query.filter(AuditEvent.user_id == user_id)
    if job_id:
        query = query.filter(AuditEvent.job_id == job_id)
    if q:
        query = query.filter(AuditEvent.action.ilike(f"%{q}%"))
    rows = query.order_by(AuditEvent.created_at.desc()).limit(limit).all()
    return [
        AuditEventOut(
            id=e.id,
            action=e.action,
            user_id=e.user_id,
            job_id=e.job_id,
            ip=e.ip,
            detail=e.detail_json,
            created_at=_iso(e.created_at) or "",
        )
        for e in rows
    ]
