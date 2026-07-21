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
    """create_all does not alter existing tables — add columns if missing."""
    with engine.begin() as conn:
        for col, ddl in alters:
            exists = conn.execute(
                text(
                    """
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = :table AND column_name = :col
                    """
                ),
                {"table": table, "col": col},
            ).scalar()
            if not exists:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}"))


def _ensure_job_columns() -> None:
    _ensure_columns(
        "jobs",
        [
            ("user_id", "VARCHAR(36)"),
            ("is_demo", "BOOLEAN DEFAULT FALSE"),
            ("abandoned_at", "TIMESTAMP WITH TIME ZONE"),
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
