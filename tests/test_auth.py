"""API auth gating — bypass attempts must fail without a real session."""
from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest

# Force SQLite before backend modules cache settings (overrides .env for this process).
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

    # Skip heavy worker in lifespan by stubbing get_runner
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


def test_upload_requires_auth(client):
    files = {"file": ("t.csv", b"Timestamp,AC Power (kW)\n2024-01-01,1.0\n", "text/csv")}
    res = client.post("/api/upload", files=files)
    assert res.status_code == 401


def test_template_requires_auth(client):
    assert client.get("/api/templates/complete-analysis").status_code == 401
    assert client.get("/api/templates/complete-analysis.zip").status_code == 401


def test_admin_requires_superadmin(client):
    assert client.get("/api/admin/users").status_code == 401
    r = client.post(
        "/api/auth/signup",
        json={"email": "user@example.com", "password": "password123", "name": "User"},
    )
    assert r.status_code == 200
    assert client.get("/api/admin/users").status_code == 403


def test_signup_login_upload_ok(client):
    r = client.post(
        "/api/auth/signup",
        json={"email": "ok@example.com", "password": "password123", "name": "Ok"},
    )
    assert r.status_code == 200
    csrf = r.json()["csrf_token"]
    files = {"file": ("t.csv", b"Timestamp,AC Power (kW)\n2024-01-01,1.0\n", "text/csv")}
    res = client.post("/api/upload", files=files, headers={"X-CSRF-Token": csrf})
    assert res.status_code != 401
    assert res.status_code != 403


def test_failed_login(client):
    client.post(
        "/api/auth/signup",
        json={"email": "a@example.com", "password": "password123", "name": "A"},
    )
    bad = client.post("/api/auth/login", json={"email": "a@example.com", "password": "wrong-password"})
    assert bad.status_code == 401


def test_local_tld_email_accepted_on_login(client):
    """email-validator rejects .local via EmailStr; AuthEmail must allow lab domains."""
    r = client.post(
        "/api/auth/signup",
        json={"email": "ops@pic.local", "password": "password123", "name": "Ops"},
    )
    assert r.status_code == 200, r.text
    login = client.post(
        "/api/auth/login",
        json={"email": "ops@pic.local", "password": "password123"},
    )
    assert login.status_code == 200, login.text
    assert login.json()["user"]["email"] == "ops@pic.local"


def test_superadmin_seed_pic_local_login(tmp_path, monkeypatch):
    """Seed admin@pic.local from env and confirm login works after AuthEmail fix."""
    monkeypatch.setenv("JOB_ROOT", str(tmp_path / "uploads"))
    monkeypatch.setenv("DATABASE_URL", "sqlite+pysqlite:///:memory:")
    monkeypatch.setenv("AUTH_AUTO_VERIFY", "true")
    monkeypatch.setenv("PIC_SUPERADMIN_EMAIL", "admin@pic.local")
    monkeypatch.setenv("PIC_SUPERADMIN_PASSWORD", "admin12345")
    monkeypatch.setenv("SESSION_SECRET", "test-secret")
    monkeypatch.setenv("CORS_ORIGINS", "http://testserver")

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
    from backend.app.auth.seed import seed_superadmin
    from backend.app.config import get_settings

    def override_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_db
    monkeypatch.setattr("backend.app.main.reclaim_stale_jobs", lambda *_a, **_k: 0)

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

    monkeypatch.setattr("backend.app.main.get_runner", lambda *_a, **_k: _DummyRunner())
    monkeypatch.setattr(
        "backend.app.main.periodic_cleanup_loop",
        lambda *_a, **_k: __import__("asyncio").sleep(3600),
    )

    # Explicit seed (lifespan also seeds) then login via TestClient
    settings = get_settings()
    with TestingSession() as db:
        user = seed_superadmin(db, settings)
        assert user is not None
        assert user.email == "admin@pic.local"
        assert user.role == "superadmin"

    from fastapi.testclient import TestClient

    with TestClient(app) as c:
        login = c.post(
            "/api/auth/login",
            json={"email": "admin@pic.local", "password": "admin12345"},
        )
        assert login.status_code == 200, login.text
        body = login.json()
        assert body["user"]["email"] == "admin@pic.local"
        assert body["user"]["role"] == "superadmin"
        assert c.get("/api/admin/users").status_code == 200

    app.dependency_overrides.clear()
    config.get_settings.cache_clear()


def test_demo_not_auth_gated(client, monkeypatch, tmp_path):
    # Point demo CSV at a tiny fixture so we don't depend on full synthetic gen
    demo_csv = tmp_path / "demo.csv"
    demo_csv.write_text(
        "Timestamp,Equipment ID,AC Power (kW),DC Power (kW),DC Current (A),DC Voltage (V),"
        "Irradiance (W/m2),GHI (W/m2),Module Temp (C),Ambient Temp (C)\n"
        "2024-01-01 10:00:00,INV-01,50,55,10,550,800,750,45,30\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("backend.app.routers.demo._demo_csv_path", lambda: demo_csv)
    # Avoid running full validation pipeline in unit test
    monkeypatch.setattr(
        "backend.app.routers.demo.validation_service.run_validation_stage",
        lambda *a, **k: None,
    )
    monkeypatch.setattr("backend.app.routers.demo.save_template", lambda *a, **k: None)
    res = client.post("/api/demo")
    assert res.status_code == 200
    assert "job_id" in res.json()


def test_random_job_not_leaked(client):
    fake = str(uuid.uuid4())
    res = client.get(f"/api/jobs/{fake}/status")
    assert res.status_code in (401, 404)


def _promote_to_superadmin(email: str):
    from backend.app.database import SessionLocal
    from backend.app.models import User

    with SessionLocal() as db:
        user = db.query(User).filter(User.email == email).first()
        assert user is not None
        user.role = "superadmin"
        db.add(user)
        db.commit()
        return user.id


def test_admin_user_ban_blocks_login(client):
    admin_res = client.post(
        "/api/auth/signup",
        json={"email": "boss@example.com", "password": "password123", "name": "Boss"},
    )
    assert admin_res.status_code == 200
    csrf = admin_res.json()["csrf_token"]
    _promote_to_superadmin("boss@example.com")

    victim = client.post(
        "/api/auth/signup",
        json={"email": "victim@example.com", "password": "password123", "name": "Victim"},
    )
    assert victim.status_code == 200
    victim_id = victim.json()["user"]["id"]

    # Ban as superadmin (re-login for admin session after victim signup stole cookies)
    login = client.post(
        "/api/auth/login",
        json={"email": "boss@example.com", "password": "password123"},
    )
    assert login.status_code == 200
    csrf = login.json()["csrf_token"]

    ban = client.patch(
        f"/api/admin/users/{victim_id}",
        json={"is_active": False},
        headers={"X-CSRF-Token": csrf},
    )
    assert ban.status_code == 200, ban.text
    assert ban.json()["is_active"] is False

    blocked = client.post(
        "/api/auth/login",
        json={"email": "victim@example.com", "password": "password123"},
    )
    assert blocked.status_code == 401


def test_admin_cannot_delete_self(client):
    r = client.post(
        "/api/auth/signup",
        json={"email": "solo@example.com", "password": "password123", "name": "Solo"},
    )
    assert r.status_code == 200
    csrf = r.json()["csrf_token"]
    uid = r.json()["user"]["id"]
    _promote_to_superadmin("solo@example.com")

    # Refresh session so role is visible (role change is DB-only; session still valid)
    login = client.post(
        "/api/auth/login",
        json={"email": "solo@example.com", "password": "password123"},
    )
    csrf = login.json()["csrf_token"]

    res = client.delete(f"/api/admin/users/{uid}", headers={"X-CSRF-Token": csrf})
    assert res.status_code == 400
    assert "yourself" in res.json()["detail"].lower()


def test_admin_user_mutations_forbidden_for_non_admin(client):
    r = client.post(
        "/api/auth/signup",
        json={"email": "pleb@example.com", "password": "password123", "name": "Pleb"},
    )
    assert r.status_code == 200
    csrf = r.json()["csrf_token"]
    uid = r.json()["user"]["id"]

    assert client.patch(
        f"/api/admin/users/{uid}",
        json={"name": "Hacked"},
        headers={"X-CSRF-Token": csrf},
    ).status_code == 403
    assert client.delete(
        f"/api/admin/users/{uid}",
        headers={"X-CSRF-Token": csrf},
    ).status_code == 403


def test_admin_edit_and_delete_other_user(client):
    admin_res = client.post(
        "/api/auth/signup",
        json={"email": "admin2@example.com", "password": "password123", "name": "Admin"},
    )
    assert admin_res.status_code == 200
    _promote_to_superadmin("admin2@example.com")

    other = client.post(
        "/api/auth/signup",
        json={"email": "other@example.com", "password": "password123", "name": "Other"},
    )
    assert other.status_code == 200
    other_id = other.json()["user"]["id"]

    login = client.post(
        "/api/auth/login",
        json={"email": "admin2@example.com", "password": "password123"},
    )
    csrf = login.json()["csrf_token"]

    edited = client.patch(
        f"/api/admin/users/{other_id}",
        json={"name": "Renamed", "role": "user"},
        headers={"X-CSRF-Token": csrf},
    )
    assert edited.status_code == 200, edited.text
    assert edited.json()["name"] == "Renamed"

    deleted = client.delete(
        f"/api/admin/users/{other_id}",
        headers={"X-CSRF-Token": csrf},
    )
    assert deleted.status_code == 200, deleted.text

    users = client.get("/api/admin/users")
    assert users.status_code == 200
    emails = {u["email"] for u in users.json()}
    assert "other@example.com" not in emails


def test_cookie_samesite_follows_cookie_secure():
    from backend.app.auth.sessions import cookie_samesite
    from backend.app.config import Settings

    assert cookie_samesite(Settings(COOKIE_SECURE="false")) == "lax"
    assert cookie_samesite(Settings(COOKIE_SECURE="true")) == "none"


def test_normalize_database_url_accepts_neon_style():
    from backend.app.config import normalize_database_url

    neon = "postgresql://user:pass@ep-x.aws.neon.tech/neondb?sslmode=require"
    assert normalize_database_url(neon).startswith("postgresql+psycopg://")
    assert normalize_database_url("postgres://u:p@h/db").startswith("postgresql+psycopg://")
    already = "postgresql+psycopg://u:p@h/db"
    assert normalize_database_url(already) == already

