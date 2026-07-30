"""Setup Continue: /api/mapping must not 500 when pack left an incomplete plant_config."""
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


def _signup(client):
    r = client.post(
        "/api/auth/signup",
        json={"email": "continue@example.com", "password": "password123", "name": "Continue"},
    )
    assert r.status_code == 200, r.text
    return r.json()["csrf_token"]


def test_mapping_with_incomplete_pack_plant_does_not_500(client, tmp_path):
    """Regression: Continue called /mapping first; incomplete plant_config → TypeError 500."""
    csrf = _signup(client)
    csv = b"Timestamp,Device ID,AC Power (kW)\n2024-01-01 10:00:00,INV-1,1.0\n"
    up = client.post(
        "/api/upload",
        files={"file": ("t.csv", csv, "text/csv")},
        headers={"X-CSRF-Token": csrf},
    )
    assert up.status_code == 200, up.text
    job_id = up.json()["job_id"]

    # Simulate pack architecture import before Plant details are filled.
    from backend.app.database import SessionLocal
    from backend.app.models import Job

    db = SessionLocal()
    try:
        job = db.get(Job, job_id)
        assert job is not None
        job.plant_config_json = {
            "plant": {
                "architecture": {"INV-1-SCB-01": {"inverter_id": "INV-1", "strings_per_scb": 16}},
                "equipment_ratings": {"INV-1": 90.0},
                "module_rating_wp": 545.0,
                "module_technology": "Mono PERC",
                "bifacial": False,
                "timezone": "Asia/Kolkata",
                "architecture_imported": True,
            },
            "threshold_overrides": {},
        }
        db.add(job)
        db.commit()
    finally:
        db.close()

    res = client.post(
        "/api/mapping",
        headers={"X-CSRF-Token": csrf},
        json={
            "job_id": job_id,
            "column_to_canonical": {
                "Timestamp": "timestamp",
                "Device ID": "device_id",
                "AC Power (kW)": "ac_power_kw",
            },
        },
    )
    assert res.status_code == 200, res.text
    assert res.json()["job_id"] == job_id

    # Now plant-config with complete fields should validate (or return 400 with detail, never 500).
    plant = client.post(
        "/api/plant-config",
        headers={"X-CSRF-Token": csrf},
        json={
            "job_id": job_id,
            "plant_name": "Continue Plant",
            "ac_capacity_mw": 0.09,
            "dc_capacity_mwp": 0.11,
            "module_rating_wp": 545,
            "inverter_capacity_kw": 90,
            "module_technology": "Mono PERC",
            "bifacial": False,
            "timezone": "Asia/Kolkata",
            "plant_type": "fixed_tilt",
            "equipment_ratings": {"INV-1": 90.0},
            "architecture": {"INV-1-SCB-01": {"inverter_id": "INV-1", "strings_per_scb": 16}},
            "architecture_imported": True,
        },
    )
    assert plant.status_code in (200, 400), plant.text
    assert plant.status_code != 500
    if plant.status_code == 400:
        detail = plant.json().get("detail") or ""
        assert detail, "400 must include detail for the UI"
