"""Signup, login, logout, profile, email verify, password reset."""
from __future__ import annotations

import hashlib
import logging
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from backend.app.auth.audit import record_audit
from backend.app.auth.deps import enforce_csrf, get_current_user, get_optional_user
from backend.app.auth.email import send_password_reset_email, send_verification_email, smtp_configured
from backend.app.auth.passwords import hash_password, verify_password
from backend.app.auth.rate_limit import client_ip, rate_limit_auth
from backend.app.auth.sessions import (
    SESSION_COOKIE,
    clear_auth_cookies,
    create_session,
    resolve_session,
    revoke_session,
    set_auth_cookies,
)
from backend.app.config import Settings, get_settings
from backend.app.database import get_db
from backend.app.models import EmailToken, User
from backend.app.schemas_auth import (
    AuthResponse,
    ChangePasswordRequest,
    ForgotPasswordRequest,
    LoginRequest,
    MeResponse,
    MessageResponse,
    ResetPasswordRequest,
    SignupRequest,
    UpdateProfileRequest,
    UserOut,
    VerifyEmailRequest,
)

logger = logging.getLogger("pic_lite.auth")
router = APIRouter(prefix="/api/auth", tags=["auth"])


def _iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def _user_out(user: User) -> UserOut:
    return UserOut(
        id=user.id,
        email=user.email,
        name=user.name or "",
        role=user.role,
        email_verified=user.email_verified,
        created_at=_iso(user.created_at) or "",
        last_login_at=_iso(user.last_login_at),
        tour_completed_at=_iso(user.tour_completed_at),
    )


def _token_hash(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _issue_email_token(db: Session, user: User, purpose: str, hours: int = 48) -> str:
    raw = secrets.token_urlsafe(32)
    row = EmailToken(
        user_id=user.id,
        token_hash=_token_hash(raw),
        purpose=purpose,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=hours),
    )
    db.add(row)
    db.commit()
    return raw


def _consume_token(db: Session, raw: str, purpose: str) -> User | None:
    row = (
        db.query(EmailToken)
        .filter(
            EmailToken.token_hash == _token_hash(raw),
            EmailToken.purpose == purpose,
            EmailToken.used_at.is_(None),
        )
        .first()
    )
    if row is None:
        return None
    expires = row.expires_at if row.expires_at.tzinfo else row.expires_at.replace(tzinfo=timezone.utc)
    if expires < datetime.now(timezone.utc):
        return None
    user = db.get(User, row.user_id)
    if user is None:
        return None
    row.used_at = datetime.now(timezone.utc)
    db.add(row)
    db.commit()
    return user


@router.get("/me", response_model=MeResponse)
def me(
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    user: User | None = Depends(get_optional_user),
):
    csrf = None
    if user is not None:
        session = resolve_session(db, request.cookies.get(SESSION_COOKIE))
        csrf = session.csrf_token if session else None
    return MeResponse(
        user=_user_out(user) if user else None,
        csrf_token=csrf,
        smtp_configured=smtp_configured(settings),
        auth_auto_verify=settings.auth_auto_verify and not smtp_configured(settings),
    )


@router.post("/signup", response_model=AuthResponse)
def signup(
    payload: SignupRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    rate_limit_auth(request, "signup", limit=8, window_sec=60)
    email = payload.email.strip().lower()
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(400, "An account with this email already exists.")

    auto_verify = settings.auth_auto_verify and not smtp_configured(settings)
    user = User(
        email=email,
        name=(payload.name or "").strip() or email.split("@")[0],
        password_hash=hash_password(payload.password),
        role="user",
        email_verified=auto_verify,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    verification_link = None
    if not user.email_verified:
        token = _issue_email_token(db, user, "verify")
        verification_link = send_verification_email(settings, to=user.email, token=token)
        logger.info("Verification link for %s: %s", user.email, verification_link)

    record_audit(
        db,
        action="auth.signup",
        user_id=user.id,
        ip=client_ip(request),
        user_agent=request.headers.get("user-agent"),
        detail={"email": user.email, "auto_verified": user.email_verified},
    )

    # Auto-login after signup (even if unverified — gated features still check verified)
    session, raw, csrf = create_session(
        db, user, settings, ip=client_ip(request), user_agent=request.headers.get("user-agent")
    )
    set_auth_cookies(response, settings, session_token=raw, csrf_token=csrf)
    msg = "Account created."
    if verification_link and not auto_verify:
        msg = "Account created. Check your email (or the verification link below in DEV) to verify."
    elif auto_verify:
        msg = "Account created and auto-verified (DEV — SMTP not configured)."

    return AuthResponse(user=_user_out(user), csrf_token=csrf, message=msg, verification_link=verification_link)


@router.post("/login", response_model=AuthResponse)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    rate_limit_auth(request, "login", limit=12, window_sec=60)
    email = payload.email.strip().lower()
    user = db.query(User).filter(User.email == email).first()
    if user is None or not verify_password(payload.password, user.password_hash) or not user.is_active:
        record_audit(
            db,
            action="auth.login_failed",
            user_id=user.id if user else None,
            ip=client_ip(request),
            user_agent=request.headers.get("user-agent"),
            detail={"email": email},
        )
        raise HTTPException(401, "Invalid email or password.")

    user.last_login_at = datetime.now(timezone.utc)
    db.add(user)
    db.commit()

    session, raw, csrf = create_session(
        db, user, settings, ip=client_ip(request), user_agent=request.headers.get("user-agent")
    )
    set_auth_cookies(response, settings, session_token=raw, csrf_token=csrf)
    record_audit(
        db,
        action="auth.login",
        user_id=user.id,
        ip=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    return AuthResponse(user=_user_out(user), csrf_token=csrf, message="Logged in.")


@router.post("/logout", response_model=MessageResponse)
def logout(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _: None = Depends(enforce_csrf),
    user: User | None = Depends(get_optional_user),
):
    session = resolve_session(db, request.cookies.get(SESSION_COOKIE))
    if session:
        revoke_session(db, session)
    clear_auth_cookies(response, settings)
    if user:
        record_audit(
            db,
            action="auth.logout",
            user_id=user.id,
            ip=client_ip(request),
            user_agent=request.headers.get("user-agent"),
        )
    return MessageResponse(message="Logged out.")


@router.post("/verify-email", response_model=MessageResponse)
def verify_email(
    payload: VerifyEmailRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    rate_limit_auth(request, "verify", limit=20, window_sec=60)
    user = _consume_token(db, payload.token.strip(), "verify")
    if user is None:
        raise HTTPException(400, "Invalid or expired verification link.")
    user.email_verified = True
    db.add(user)
    db.commit()
    record_audit(
        db,
        action="auth.email_verified",
        user_id=user.id,
        ip=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    return MessageResponse(message="Email verified. You can continue.")


@router.post("/resend-verification", response_model=MessageResponse)
def resend_verification(
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _: None = Depends(enforce_csrf),
    user: User = Depends(get_current_user),
):
    if user.email_verified:
        return MessageResponse(message="Email is already verified.")
    rate_limit_auth(request, "resend", limit=5, window_sec=60)
    token = _issue_email_token(db, user, "verify")
    link = send_verification_email(settings, to=user.email, token=token)
    logger.info("Resent verification link for %s: %s", user.email, link)
    return MessageResponse(message="Verification email sent.", verification_link=link)


@router.post("/forgot-password", response_model=MessageResponse)
def forgot_password(
    payload: ForgotPasswordRequest,
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    rate_limit_auth(request, "forgot", limit=5, window_sec=60)
    email = payload.email.strip().lower()
    user = db.query(User).filter(User.email == email).first()
    # Always return the same message to avoid account enumeration
    msg = "If that email is registered, a reset link has been issued."
    reset_link = None
    if user and user.is_active:
        token = _issue_email_token(db, user, "reset", hours=2)
        reset_link = send_password_reset_email(settings, to=user.email, token=token)
        logger.info("Password reset link for %s: %s", user.email, reset_link)
        record_audit(
            db,
            action="auth.password_reset_requested",
            user_id=user.id,
            ip=client_ip(request),
            user_agent=request.headers.get("user-agent"),
        )
    return MessageResponse(message=msg, reset_link=reset_link if not smtp_configured(settings) else None)


@router.post("/reset-password", response_model=MessageResponse)
def reset_password(
    payload: ResetPasswordRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    rate_limit_auth(request, "reset", limit=10, window_sec=60)
    user = _consume_token(db, payload.token.strip(), "reset")
    if user is None:
        raise HTTPException(400, "Invalid or expired reset link.")
    user.password_hash = hash_password(payload.new_password)
    user.email_verified = True
    db.add(user)
    db.commit()
    record_audit(
        db,
        action="auth.password_reset",
        user_id=user.id,
        ip=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    return MessageResponse(message="Password updated. You can log in.")


@router.patch("/profile", response_model=AuthResponse)
def update_profile(
    payload: UpdateProfileRequest,
    request: Request,
    db: Session = Depends(get_db),
    _: None = Depends(enforce_csrf),
    user: User = Depends(get_current_user),
):
    user.name = payload.name.strip()
    db.add(user)
    db.commit()
    db.refresh(user)
    session = resolve_session(db, request.cookies.get(SESSION_COOKIE))
    csrf = session.csrf_token if session else ""
    record_audit(
        db,
        action="auth.profile_updated",
        user_id=user.id,
        ip=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    return AuthResponse(user=_user_out(user), csrf_token=csrf, message="Profile updated.")


@router.post("/tour/complete", response_model=AuthResponse)
def complete_demo_tour(
    request: Request,
    db: Session = Depends(get_db),
    _: None = Depends(enforce_csrf),
    user: User = Depends(get_current_user),
):
    """Mark the interactive demo tour as completed for this account."""
    if user.tour_completed_at is None:
        user.tour_completed_at = datetime.now(timezone.utc)
        db.add(user)
        db.commit()
        db.refresh(user)
        record_audit(
            db,
            action="auth.tour_completed",
            user_id=user.id,
            ip=client_ip(request),
            user_agent=request.headers.get("user-agent"),
        )
    session = resolve_session(db, request.cookies.get(SESSION_COOKIE))
    csrf = session.csrf_token if session else ""
    return AuthResponse(user=_user_out(user), csrf_token=csrf, message="Tour completed.")


@router.post("/tour/reset", response_model=AuthResponse)
def reset_demo_tour(
    request: Request,
    db: Session = Depends(get_db),
    _: None = Depends(enforce_csrf),
    user: User = Depends(get_current_user),
):
    """Clear tour completion so the demo walkthrough can run again (Profile → Replay)."""
    user.tour_completed_at = None
    db.add(user)
    db.commit()
    db.refresh(user)
    session = resolve_session(db, request.cookies.get(SESSION_COOKIE))
    csrf = session.csrf_token if session else ""
    record_audit(
        db,
        action="auth.tour_reset",
        user_id=user.id,
        ip=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    return AuthResponse(user=_user_out(user), csrf_token=csrf, message="Tour reset.")


@router.post("/change-password", response_model=MessageResponse)
def change_password(
    payload: ChangePasswordRequest,
    request: Request,
    db: Session = Depends(get_db),
    _: None = Depends(enforce_csrf),
    user: User = Depends(get_current_user),
):
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(400, "Current password is incorrect.")
    user.password_hash = hash_password(payload.new_password)
    db.add(user)
    db.commit()
    record_audit(
        db,
        action="auth.password_changed",
        user_id=user.id,
        ip=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    return MessageResponse(message="Password changed.")
