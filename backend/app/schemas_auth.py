"""Auth and admin API schemas."""
from __future__ import annotations

from pydantic import BaseModel, Field

from backend.app.auth.email_types import AuthEmail


class SignupRequest(BaseModel):
    email: AuthEmail
    password: str = Field(min_length=8, max_length=128)
    name: str = Field(default="", max_length=255)


class LoginRequest(BaseModel):
    email: AuthEmail
    password: str = Field(min_length=1, max_length=128)


class UserOut(BaseModel):
    id: str
    email: str
    name: str
    role: str
    email_verified: bool
    created_at: str
    last_login_at: str | None = None
    tour_completed_at: str | None = None


class AuthResponse(BaseModel):
    user: UserOut
    csrf_token: str
    message: str | None = None
    verification_link: str | None = None


class MeResponse(BaseModel):
    user: UserOut | None
    csrf_token: str | None = None
    smtp_configured: bool = False
    auth_auto_verify: bool = True


class UpdateProfileRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


class ForgotPasswordRequest(BaseModel):
    email: AuthEmail


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(min_length=8, max_length=128)


class VerifyEmailRequest(BaseModel):
    token: str


class MessageResponse(BaseModel):
    message: str
    verification_link: str | None = None
    reset_link: str | None = None


class AdminUserOut(BaseModel):
    id: str
    email: str
    name: str
    role: str
    email_verified: bool
    is_active: bool
    created_at: str
    last_login_at: str | None = None
    job_count: int = 0


class AdminUserUpdateRequest(BaseModel):
    """Partial update for superadmin user management."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    role: str | None = Field(default=None, pattern="^(user|superadmin)$")
    is_active: bool | None = None
    email_verified: bool | None = None


class AdminSessionOut(BaseModel):
    id: str
    user_id: str
    user_email: str | None = None
    created_at: str
    expires_at: str
    revoked_at: str | None = None
    ip: str | None = None
    user_agent: str | None = None


class AdminJobOut(BaseModel):
    id: str
    state: str
    user_id: str | None
    user_email: str | None = None
    is_demo: bool
    original_filename: str | None
    plant_name: str | None
    created_at: str
    completed_at: str | None
    abandoned_at: str | None


class AuditEventOut(BaseModel):
    id: str
    action: str
    user_id: str | None
    job_id: str | None
    ip: str | None
    detail: dict | None = None
    created_at: str


class FunnelStats(BaseModel):
    uploaded: int
    mapping: int
    validating: int
    queued_or_running: int
    completed: int
    failed: int
    abandoned: int
    demo: int
