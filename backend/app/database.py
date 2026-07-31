"""SQLAlchemy engine/session setup. Postgres stores metadata only — never raw or
canonical time-series data. See docs/architecture_decisions.md §7.
"""
from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from backend.app.config import get_settings

settings = get_settings()
engine = create_engine(settings.database_url, pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _ensure_columns(table: str, alters: list[tuple[str, str]]) -> None:
    """create_all does not alter existing tables — add columns if missing.

    Uses SQLAlchemy inspection so SQLite (pytest) and Postgres (prod) both work.
    ``information_schema.columns`` is Postgres-only and breaks local auth tests.
    """
    from sqlalchemy import inspect

    inspector = inspect(engine)
    try:
        existing = {c["name"] for c in inspector.get_columns(table)}
    except Exception:
        existing = set()
    with engine.begin() as conn:
        for col, ddl in alters:
            if col in existing:
                continue
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}"))
            existing.add(col)


def _ensure_job_columns() -> None:
    _ensure_columns(
        "jobs",
        [
            ("user_id", "VARCHAR(36)"),
            ("is_demo", "BOOLEAN DEFAULT FALSE"),
            ("abandoned_at", "TIMESTAMP WITH TIME ZONE"),
            ("ai_integrity_json", "JSON"),
            ("upload_integrity_json", "JSON"),
        ],
    )


def _ensure_user_columns() -> None:
    _ensure_columns(
        "users",
        [
            ("tour_completed_at", "TIMESTAMP WITH TIME ZONE"),
        ],
    )


def init_db() -> None:
    from backend.app import models  # noqa: F401 - ensure models are registered

    Base.metadata.create_all(bind=engine)
    _ensure_job_columns()
    _ensure_user_columns()
