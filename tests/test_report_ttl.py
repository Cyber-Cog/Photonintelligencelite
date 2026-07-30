"""Report retention TTL defaults and account-job expiry alignment."""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import pytest


def test_default_report_ttl_is_seven_days(monkeypatch):
    monkeypatch.delenv("REPORT_TTL_MINUTES", raising=False)
    monkeypatch.delenv("PIC_LITE_FREE_TIER", raising=False)
    from analytics.common import config_loader

    config_loader.load_defaults.cache_clear()
    limits = config_loader.deployment_limits(free_tier=False)
    assert limits.report_ttl_minutes == 10080


def test_free_tier_report_ttl_is_seven_days(monkeypatch):
    monkeypatch.delenv("REPORT_TTL_MINUTES", raising=False)
    from analytics.common import config_loader

    config_loader.load_defaults.cache_clear()
    limits = config_loader.deployment_limits(free_tier=True)
    assert limits.report_ttl_minutes == 10080


def test_env_overrides_report_ttl(monkeypatch):
    monkeypatch.setenv("REPORT_TTL_MINUTES", "120")
    from analytics.common import config_loader

    config_loader.load_defaults.cache_clear()
    limits = config_loader.deployment_limits(free_tier=True)
    assert limits.report_ttl_minutes == 120


@pytest.fixture()
def db_session(tmp_path, monkeypatch):
    os.environ["DATABASE_URL"] = "sqlite+pysqlite:///:memory:"
    os.environ["SESSION_SECRET"] = "test-secret"
    monkeypatch.setenv("JOB_ROOT", str(tmp_path / "uploads"))
    monkeypatch.setenv("DATABASE_URL", "sqlite+pysqlite:///:memory:")
    monkeypatch.setenv("REPORT_TTL_MINUTES", "10080")

    from backend.app import config, database
    from backend.app.database import Base
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    config.get_settings.cache_clear()

    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    database.engine = engine
    database.SessionLocal = TestingSession
    monkeypatch.setattr(database, "_ensure_job_columns", lambda: None)

    from backend.app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    yield TestingSession
    config.get_settings.cache_clear()


def test_align_extends_short_ttl_for_account_jobs(db_session, monkeypatch):
    from analytics.core.job_states import JobState
    from backend.app import config
    from backend.app.models import Job, User
    from backend.app.services.cleanup_service import align_account_job_report_ttl

    config.get_settings.cache_clear()
    settings = config.get_settings()

    now = datetime.now(timezone.utc)
    with db_session() as db:
        user = User(
            email="ttl@example.com",
            name="TTL",
            password_hash="x",
            email_verified=True,
            role="user",
        )
        db.add(user)
        db.flush()
        job = Job(
            state=JobState.COMPLETED.value,
            user_id=user.id,
            is_demo=False,
            completed_at=now - timedelta(minutes=30),
            report_expires_at=now + timedelta(minutes=30),  # old 60-min window remnant
        )
        db.add(job)
        db.commit()
        job_id = job.id

    updated = align_account_job_report_ttl(settings)
    assert updated == 1

    with db_session() as db:
        row = db.get(Job, job_id)
        assert row is not None
        assert row.report_expires_at is not None
        exp = row.report_expires_at
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        # completed_at + 7 days should be ~6.5d from now
        assert exp > now + timedelta(days=6)
