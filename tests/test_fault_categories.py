"""Tests for actionable / non-actionable fault category settings."""
from __future__ import annotations

import os

import pytest

os.environ["DATABASE_URL"] = "sqlite+pysqlite:///:memory:"
os.environ["SESSION_SECRET"] = "test-secret"
os.environ["AUTH_AUTO_VERIFY"] = "true"
os.environ["PIC_SUPERADMIN_EMAIL"] = ""
os.environ["PIC_SUPERADMIN_PASSWORD"] = ""
os.environ["CORS_ORIGINS"] = "http://testserver"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("JOB_ROOT", str(tmp_path / "uploads"))
    monkeypatch.setenv("DATABASE_URL", "sqlite+pysqlite:///:memory:")
    monkeypatch.setenv("AUTH_AUTO_VERIFY", "true")
    monkeypatch.setenv("PIC_SUPERADMIN_EMAIL", "")

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

    from backend.app.main import app
    from backend.app.database import get_db

    def override_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_db
    monkeypatch.setattr("backend.app.main.reclaim_stale_jobs", lambda *_a, **_k: 0)
    monkeypatch.setattr("backend.app.main.seed_superadmin", lambda *_a, **_k: None)

    class _DummyRunner:
        async def start(self):
            return None

        async def stop(self):
            return None

        def submit(self, _job_id: str):
            return None

        def queue_position(self, _job_id: str):
            return None

        def estimated_wait_seconds(self, _job_id: str):
            return None

        @property
        def max_workers(self):
            return 1

        @property
        def running_count(self):
            return 0

        @property
        def queued_count(self):
            return 0

        @property
        def pool_started(self):
            return True

    monkeypatch.setattr("backend.app.main.get_runner", lambda *_a, **_k: _DummyRunner())
    monkeypatch.setattr(
        "backend.app.main.periodic_cleanup_loop",
        lambda *_a, **_k: __import__("asyncio").sleep(3600),
    )

    from backend.app.auth import rate_limit as rate_limit_mod

    rate_limit_mod._hits.clear()

    from fastapi.testclient import TestClient

    with TestClient(app) as c:
        yield c

    app.dependency_overrides.clear()
    config.get_settings.cache_clear()
    rate_limit_mod._hits.clear()


def _promote_to_superadmin(email: str) -> None:
    from backend.app.database import SessionLocal
    from backend.app.models import User

    with SessionLocal() as db:
        user = db.query(User).filter(User.email == email).first()
        assert user is not None
        user.role = "superadmin"
        db.add(user)
        db.commit()


def test_public_fault_categories_defaults(client):
    res = client.get("/api/config/fault-categories")
    assert res.status_code == 200, res.text
    body = res.json()
    assert "disconnected_strings" in body["actionable"]
    assert "module_damage" in body["actionable"]
    assert "clipping_power" in body["non_actionable"]
    assert "clipping_current" in body["non_actionable"]
    assert body["categories"]["disconnected_strings"] == "actionable"
    assert body["categories"]["clipping_power"] == "non_actionable"
    assert len(body["modules"]) >= 5


def test_admin_put_fault_categories(client):
    signup = client.post(
        "/api/auth/signup",
        json={"email": "boss@example.com", "password": "password123", "name": "Boss"},
    )
    assert signup.status_code == 200
    _promote_to_superadmin("boss@example.com")
    login = client.post(
        "/api/auth/login",
        json={"email": "boss@example.com", "password": "password123"},
    )
    assert login.status_code == 200
    csrf = login.json()["csrf_token"]

    res = client.put(
        "/api/admin/fault-categories",
        headers={"X-CSRF-Token": csrf},
        json={
            "actionable": [
                "disconnected_strings",
                "module_damage",
                "inverter_efficiency",
                "clipping_power",
            ],
            "non_actionable": ["clipping_current"],
        },
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert "clipping_power" in body["actionable"]
    assert body["categories"]["clipping_power"] == "actionable"

    public = client.get("/api/config/fault-categories")
    assert public.status_code == 200
    assert public.json()["categories"]["clipping_power"] == "actionable"


def test_admin_fault_categories_requires_superadmin(client):
    assert client.get("/api/admin/fault-categories").status_code == 401
    client.post(
        "/api/auth/signup",
        json={"email": "plain@example.com", "password": "password123", "name": "Plain"},
    )
    assert client.get("/api/admin/fault-categories").status_code == 403
    put = client.put(
        "/api/admin/fault-categories",
        json={"actionable": ["disconnected_strings"], "non_actionable": []},
    )
    assert put.status_code in (401, 403)
