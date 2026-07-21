"""HttpOnly session cookies + CSRF double-submit token."""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import Response
from sqlalchemy.orm import Session

from backend.app.config import Settings
from backend.app.models import AuthSession, User

SESSION_COOKIE = "pic_session"
CSRF_COOKIE = "pic_csrf"

CookieSameSite = Literal["lax", "strict", "none"]


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def cookie_samesite(settings: Settings) -> CookieSameSite:
    """SameSite for session/CSRF cookies.

    Local same-origin (Vite + API on localhost): ``COOKIE_SECURE=false`` → ``lax``.
    Cross-origin free tier (Vercel UI + Render API): set ``COOKIE_SECURE=true`` so
    cookies are ``SameSite=None; Secure`` — browsers otherwise drop them on
    credentialed cross-site fetch. Requires HTTPS (Render/Vercel provide this).
    """
    return "none" if settings.cookie_secure else "lax"



def create_session(
    db: Session,
    user: User,
    settings: Settings,
    *,
    ip: str | None = None,
    user_agent: str | None = None,
) -> tuple[AuthSession, str, str]:
    """Returns (session_row, raw_session_token, csrf_token)."""
    raw = secrets.token_urlsafe(32)
    csrf = secrets.token_urlsafe(32)
    row = AuthSession(
        user_id=user.id,
        token_hash=_hash_token(raw),
        csrf_token=csrf,
        expires_at=datetime.now(timezone.utc) + timedelta(days=settings.session_ttl_days),
        ip=ip,
        user_agent=(user_agent or "")[:500] or None,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row, raw, csrf


def resolve_session(db: Session, raw_token: str | None) -> AuthSession | None:
    if not raw_token:
        return None
    row = (
        db.query(AuthSession)
        .filter(AuthSession.token_hash == _hash_token(raw_token), AuthSession.revoked_at.is_(None))
        .first()
    )
    if row is None:
        return None
    if row.expires_at.replace(tzinfo=timezone.utc) if row.expires_at.tzinfo is None else row.expires_at:
        expires = row.expires_at if row.expires_at.tzinfo else row.expires_at.replace(tzinfo=timezone.utc)
        if expires < datetime.now(timezone.utc):
            return None
    return row


def revoke_session(db: Session, session: AuthSession) -> None:
    session.revoked_at = datetime.now(timezone.utc)
    db.add(session)
    db.commit()


def set_auth_cookies(response: Response, settings: Settings, *, session_token: str, csrf_token: str) -> None:
    secure = settings.cookie_secure
    samesite = cookie_samesite(settings)
    max_age = settings.session_ttl_days * 86400
    response.set_cookie(
        key=SESSION_COOKIE,
        value=session_token,
        httponly=True,
        samesite=samesite,
        secure=secure,
        max_age=max_age,
        path="/",
    )
    response.set_cookie(
        key=CSRF_COOKIE,
        value=csrf_token,
        httponly=False,
        samesite=samesite,
        secure=secure,
        max_age=max_age,
        path="/",
    )


def clear_auth_cookies(response: Response, settings: Settings) -> None:
    secure = settings.cookie_secure
    samesite = cookie_samesite(settings)
    response.delete_cookie(SESSION_COOKIE, path="/", samesite=samesite, secure=secure)
    response.delete_cookie(CSRF_COOKIE, path="/", samesite=samesite, secure=secure)
