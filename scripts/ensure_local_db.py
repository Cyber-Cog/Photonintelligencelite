"""Ensure local Postgres has the pic_lite role and database.

Tries in order:
  1. Connect with DATABASE_URL (or the default pic_lite/pic_lite@localhost/pic_lite)
  2. If that fails, connect as a superuser (postgres / env PGUSER) and create role + DB

Exit codes:
  0 = ready
  1 = could not connect / create
"""
from __future__ import annotations

import os
import sys
from urllib.parse import urlparse, unquote


DEFAULT_URL = "postgresql+psycopg://pic_lite:pic_lite@localhost:5432/pic_lite"


def _parse(url: str) -> dict:
    # SQLAlchemy style: postgresql+psycopg://user:pass@host:port/db
    cleaned = url.replace("postgresql+psycopg://", "postgresql://", 1)
    cleaned = cleaned.replace("postgresql+psycopg2://", "postgresql://", 1)
    p = urlparse(cleaned)
    return {
        "user": unquote(p.username or ""),
        "password": unquote(p.password or ""),
        "host": p.hostname or "localhost",
        "port": p.port or 5432,
        "dbname": (p.path or "/pic_lite").lstrip("/") or "pic_lite",
    }


def _connect(**kwargs):
    import psycopg

    return psycopg.connect(**kwargs, connect_timeout=5)


def _try_app_url(cfg: dict) -> bool:
    try:
        with _connect(
            host=cfg["host"],
            port=cfg["port"],
            user=cfg["user"],
            password=cfg["password"],
            dbname=cfg["dbname"],
        ) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
        print(f"OK: connected to {cfg['dbname']} as {cfg['user']}@{cfg['host']}:{cfg['port']}")
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"App credentials not ready yet: {exc}")
        return False


def _ensure_as_superuser(cfg: dict) -> bool:
    """Create role + database using a local superuser account."""
    candidates = []
    if os.getenv("PGUSER"):
        candidates.append((os.environ["PGUSER"], os.getenv("PGPASSWORD", "")))
    # Common local Windows installs
    candidates.extend(
        [
            ("postgres", os.getenv("PGPASSWORD", "postgres")),
            ("postgres", ""),
            ("postgres", "admin"),
            ("postgres", "root"),
        ]
    )

    last_err: Exception | None = None
    for user, password in candidates:
        try:
            with _connect(
                host=cfg["host"],
                port=cfg["port"],
                user=user,
                password=password,
                dbname="postgres",
            ) as conn:
                conn.autocommit = True
                with conn.cursor() as cur:
                    cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (cfg["user"],))
                    if cur.fetchone() is None:
                        print(f"Creating role '{cfg['user']}'...")
                        cur.execute(
                            f"CREATE ROLE {cfg['user']} LOGIN PASSWORD %s",
                            (cfg["password"],),
                        )
                    else:
                        # Keep password in sync with expected local default
                        cur.execute(f"ALTER ROLE {cfg['user']} WITH PASSWORD %s", (cfg["password"],))

                    cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (cfg["dbname"],))
                    if cur.fetchone() is None:
                        print(f"Creating database '{cfg['dbname']}'...")
                        cur.execute(f"CREATE DATABASE {cfg['dbname']} OWNER {cfg['user']}")
                    else:
                        cur.execute(f"ALTER DATABASE {cfg['dbname']} OWNER TO {cfg['user']}")

                    cur.execute(f"GRANT ALL PRIVILEGES ON DATABASE {cfg['dbname']} TO {cfg['user']}")
            print(f"OK: ensured role/db using superuser '{user}'")
            return True
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            continue

    print(f"ERROR: could not create role/db as a superuser. Last error: {last_err}")
    print("Tip: set PGUSER and PGPASSWORD to your Postgres admin credentials, then re-run start.bat")
    return False


def main() -> int:
    url = os.getenv("DATABASE_URL", DEFAULT_URL)
    cfg = _parse(url)

    if _try_app_url(cfg):
        return 0

    if not _ensure_as_superuser(cfg):
        return 1

    if _try_app_url(cfg):
        return 0

    print("ERROR: role/db created but app login still failed.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
