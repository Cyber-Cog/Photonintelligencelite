"""Backend configuration.

Environment variables only ever override deployment limits (upload size, job timeout,
free-tier switch) — never algorithm thresholds, which live exclusively in
analytics/config/*.yaml. See docs/architecture_decisions.md §6.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from analytics.common.config_loader import DeploymentLimits, deployment_limits


def normalize_database_url(url: str) -> str:
    """Accept Neon/Render-style URLs and force the psycopg (v3) SQLAlchemy dialect.

    Neon dashboards copy ``postgresql://…`` or ``postgres://…``; this app expects
    ``postgresql+psycopg://…``.
    """
    if url.startswith("postgres://"):
        url = "postgresql://" + url.removeprefix("postgres://")
    if url.startswith("postgresql://") and not url.startswith("postgresql+"):
        return "postgresql+psycopg://" + url.removeprefix("postgresql://")
    return url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+psycopg://pic_lite:pic_lite@localhost:5432/pic_lite"
    job_root: str = "./uploads"
    # Explicit alias: pydantic-settings would otherwise look for a bare `FREE_TIER` env var,
    # but render.yaml/.env.example (and analytics.common.config_loader's own standalone
    # PIC_LITE_FREE_TIER lookup) both use the prefixed name — this alias keeps them in sync.
    free_tier: bool = Field(default=False, validation_alias="PIC_LITE_FREE_TIER")
    cors_origins: str = "http://localhost:5173"
    log_level: str = "INFO"
    # In-process worker pool size (Lite supports concurrent analyses). Cap for RAM on small hosts.
    max_concurrent_jobs: int = Field(default=4, validation_alias="MAX_CONCURRENT_JOBS")

    # Auth / sessions
    session_secret: str = Field(default="dev-only-change-me", validation_alias="SESSION_SECRET")
    session_ttl_days: int = Field(default=14, validation_alias="SESSION_TTL_DAYS")
    # true on HTTPS cross-origin deploy (Vercel + Render) → cookies use SameSite=None; Secure
    cookie_secure: bool = Field(default=False, validation_alias="COOKIE_SECURE")
    public_app_url: str = Field(default="http://localhost:5173", validation_alias="PUBLIC_APP_URL")
    # When true (default in local DEV), new signups are auto-verified if SMTP is unset.
    auth_auto_verify: bool = Field(default=True, validation_alias="AUTH_AUTO_VERIFY")

    # Superadmin seed
    pic_superadmin_email: str | None = Field(default=None, validation_alias="PIC_SUPERADMIN_EMAIL")
    pic_superadmin_password: str | None = Field(default=None, validation_alias="PIC_SUPERADMIN_PASSWORD")
    pic_superadmin_name: str = Field(default="Superadmin", validation_alias="PIC_SUPERADMIN_NAME")

    @field_validator("database_url", mode="before")
    @classmethod
    def _normalize_database_url(cls, v: object) -> object:
        if isinstance(v, str) and v.strip():
            return normalize_database_url(v.strip())
        return v

    # SMTP (optional — without it, verification/reset links are logged)
    smtp_host: str | None = Field(default=None, validation_alias="SMTP_HOST")
    smtp_port: int = Field(default=587, validation_alias="SMTP_PORT")
    smtp_user: str | None = Field(default=None, validation_alias="SMTP_USER")
    smtp_password: str | None = Field(default=None, validation_alias="SMTP_PASSWORD")
    smtp_from: str | None = Field(default=None, validation_alias="SMTP_FROM")
    smtp_use_tls: bool = Field(default=True, validation_alias="SMTP_USE_TLS")

    @property
    def job_root_path(self) -> Path:
        p = Path(self.job_root)
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def limits(self) -> DeploymentLimits:
        return deployment_limits(free_tier=self.free_tier)

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
