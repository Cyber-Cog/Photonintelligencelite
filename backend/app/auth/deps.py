"""FastAPI auth dependencies — never trust client-only flags."""
from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from backend.app.auth.sessions import CSRF_COOKIE, SESSION_COOKIE, resolve_session
from backend.app.config import Settings, get_settings
from backend.app.database import get_db
from backend.app.models import Job, User

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


@dataclass
class AuthContext:
    user: User
    session_id: str
    csrf_token: str


def _load_auth(request: Request, db: Session) -> AuthContext | None:
    raw = request.cookies.get(SESSION_COOKIE)
    session = resolve_session(db, raw)
    if session is None:
        return None
    user = db.get(User, session.user_id)
    if user is None or not user.is_active:
        return None
    return AuthContext(user=user, session_id=session.id, csrf_token=session.csrf_token)


def get_optional_user(request: Request, db: Session = Depends(get_db)) -> User | None:
    ctx = _load_auth(request, db)
    return ctx.user if ctx else None


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    ctx = _load_auth(request, db)
    if ctx is None:
        raise HTTPException(401, "Authentication required. Please log in.")
    return ctx.user


def require_verified_user(user: User = Depends(get_current_user)) -> User:
    if not user.email_verified:
        raise HTTPException(403, "Please verify your email before continuing.")
    return user


def require_superadmin(user: User = Depends(get_current_user)) -> User:
    if user.role != "superadmin":
        raise HTTPException(403, "Superadmin access required.")
    return user


def enforce_csrf(request: Request, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)) -> None:
    """CSRF check for cookie sessions on unsafe methods."""
    if request.method in SAFE_METHODS:
        return
    ctx = _load_auth(request, db)
    if ctx is None:
        return  # unauthenticated unsafe routes either public or blocked by get_current_user
    header = request.headers.get("x-csrf-token") or request.headers.get("X-CSRF-Token")
    cookie = request.cookies.get(CSRF_COOKIE)
    if not header or not cookie or header != cookie or header != ctx.csrf_token:
        raise HTTPException(403, "CSRF token missing or invalid.")
    # settings reserved for future SameSite/origin checks
    _ = settings


def require_job_access(
    job: Job,
    user: User | None,
    *,
    allow_demo_anonymous: bool = True,
) -> None:
    """Authorize job workspace access. Demo jobs stay reachable without login."""
    if allow_demo_anonymous and job.is_demo:
        return
    if user is None:
        raise HTTPException(401, "Authentication required. Please log in.")
    if user.role == "superadmin":
        return
    if job.user_id and job.user_id == user.id:
        return
    # Legacy jobs without owner: only superadmin (already handled) — block others
    if job.user_id is None and not job.is_demo:
        raise HTTPException(403, "You do not have access to this job.")
    raise HTTPException(403, "You do not have access to this job.")
