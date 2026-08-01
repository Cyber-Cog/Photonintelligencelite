"""Missing raw upload + user-facing error sanitization."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ["DATABASE_URL"] = "sqlite+pysqlite:///:memory:"
os.environ["SESSION_SECRET"] = "test-secret"
os.environ["AUTH_AUTO_VERIFY"] = "true"
os.environ["PIC_SUPERADMIN_EMAIL"] = ""
os.environ["PIC_SUPERADMIN_PASSWORD"] = ""
os.environ["CORS_ORIGINS"] = "http://testserver"

from backend.app.services.user_errors import (
    MSG_MISSING_RAW_UPLOAD,
    MSG_PROCESS_FAILED,
    MSG_VALIDATE_FAILED,
    MissingRawUploadError,
    user_facing_message,
)


def test_user_facing_message_strips_errno_and_paths():
    raw = (
        "[Errno 2] No such file or directory: "
        "'/tmp/pic-lite-jobs/9b0c2ffa-bf62-4448-8bl4-cd77fa91648e/raw/input.csv'"
    )
    out = user_facing_message(raw, fallback=MSG_VALIDATE_FAILED)
    assert out == MSG_MISSING_RAW_UPLOAD
    assert "/tmp/" not in out
    assert "Errno" not in out
    assert "input.csv" not in out


def test_user_facing_message_file_not_found_exception():
    exc = FileNotFoundError(
        2,
        "No such file or directory",
        "/tmp/pic-lite-jobs/abc/raw/input.csv",
    )
    out = user_facing_message(exc, fallback=MSG_VALIDATE_FAILED)
    assert out == MSG_MISSING_RAW_UPLOAD
    assert "pic-lite-jobs" not in out


def test_user_facing_message_missing_raw_upload_error():
    assert user_facing_message(MissingRawUploadError()) == MSG_MISSING_RAW_UPLOAD


def test_user_facing_message_allows_plant_incomplete():
    msg = "Plant configuration is incomplete (missing or invalid: plant_name). Finish Setup → Plant details, then Continue again."
    assert user_facing_message(msg, fallback=MSG_VALIDATE_FAILED) == msg


def test_user_facing_message_sanitizes_generic_exception_type():
    out = user_facing_message(RuntimeError("boom internals"), fallback=MSG_PROCESS_FAILED)
    assert out == MSG_PROCESS_FAILED
    assert "boom" not in out


def test_resolve_raw_input_csv_prefers_input_then_sole_part(tmp_path):
    from backend.app.services.storage import JobPaths
    from backend.app.services.validation_service import resolve_raw_input_csv

    paths = JobPaths(root=tmp_path / "job").ensure()
    assert resolve_raw_input_csv(paths) is None

    part = paths.raw_dir / "part_0.csv"
    part.write_text("Timestamp,Power\n2026-01-01,1\n", encoding="utf-8")
    assert resolve_raw_input_csv(paths) == part

    primary = paths.raw_dir / "input.csv"
    primary.write_text("Timestamp,Power\n2026-01-01,2\n", encoding="utf-8")
    assert resolve_raw_input_csv(paths) == primary


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
        yield c, tmp_path / "uploads", TestingSession

    app.dependency_overrides.clear()
    config.get_settings.cache_clear()
    rate_limit_mod._hits.clear()


def _signup(client):
    r = client.post(
        "/api/auth/signup",
        json={"email": "missingraw@example.com", "password": "password123", "name": "Missing"},
    )
    assert r.status_code == 200, r.text
    return r.json()["csrf_token"]


def test_mapping_continue_missing_raw_returns_friendly_error(client):
    """Job DB row exists but raw/input.csv is gone → friendly 400, no path leak."""
    api, job_root, Session = client
    csrf = _signup(api)

    from backend.app.models import Job, User
    from backend.app.services.storage import job_paths
    from analytics.core.job_states import JobState

    with Session() as db:
        user = db.query(User).filter(User.email == "missingraw@example.com").one()
        job = Job(
            id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
            user_id=user.id,
            state=JobState.MAPPING.value,
            original_filename="gone.csv",
            plant_config_json={
                "plant": {
                    "plant_name": "Test Plant",
                    "ac_capacity_mw": 1.0,
                    "dc_capacity_mwp": 1.2,
                    "module_rating_wp": 540,
                    "inverter_capacity_kw": 100,
                    "module_technology": "mono-PERC",
                    "bifacial": False,
                    "timezone": "Asia/Kolkata",
                },
                "threshold_overrides": {},
            },
        )
        db.add(job)
        db.commit()
        job_id = job.id

    # Create empty job dirs (as ensure() would) but no input.csv — simulates /tmp wipe
    paths = job_paths(Path(job_root), job_id)
    assert not (paths.raw_dir / "input.csv").exists()

    r = api.post(
        "/api/mapping",
        headers={"X-CSRF-Token": csrf},
        json={
            "job_id": job_id,
            "column_to_canonical": {"Timestamp": "timestamp", "Power": "ac_power_kw"},
        },
    )
    assert r.status_code == 400, r.text
    detail = r.json()["detail"]
    assert detail == MSG_MISSING_RAW_UPLOAD
    assert "/tmp" not in detail
    assert "Errno" not in detail
    assert "pic-lite-jobs" not in detail
    assert str(paths.raw_dir) not in detail

    with Session() as db:
        refreshed = db.get(Job, job_id)
        assert refreshed is not None
        assert refreshed.state == JobState.FAILED.value
        assert refreshed.error_summary == MSG_MISSING_RAW_UPLOAD
        blockers = (refreshed.validation_summary_json or {}).get("blockers") or []
        assert blockers and blockers[0]["code"] == "missing_raw_upload"
        assert "replace_upload" in (refreshed.validation_summary_json or {}).get("recovery_actions", [])
