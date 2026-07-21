"""Start the bundled portable Postgres under .tools/ (no Docker, no system install).

Downloads Windows Postgres binaries from Maven Central on first run (zonky embedded
binaries — same distribution many test frameworks use), initializes a data directory,
and starts listening on 127.0.0.1:5432 with role/database pic_lite / pic_lite.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tarfile
import time
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / ".tools"
PG_BIN = TOOLS / "pgsql" / "bin"
PG_DATA = TOOLS / "pgdata"
PG_LOG = TOOLS / "postgres.log"
JAR_PATH = TOOLS / "pg-binaries.jar"
TXZ_PATH = TOOLS / "postgres-windows-x86_64.txz"

MAVEN_JAR_URL = (
    "https://repo1.maven.org/maven2/io/zonky/test/postgres/"
    "embedded-postgres-binaries-windows-amd64/16.2.0/"
    "embedded-postgres-binaries-windows-amd64-16.2.0.jar"
)

APP_USER = "pic_lite"
APP_PASSWORD = "pic_lite"
APP_DB = "pic_lite"
PORT = 5432


def _run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, check=False, capture_output=True, text=True, **kwargs)


def ensure_binaries() -> None:
    pg_ctl = PG_BIN / "pg_ctl.exe"
    if pg_ctl.exists():
        return

    TOOLS.mkdir(parents=True, exist_ok=True)
    print("Downloading portable PostgreSQL binaries (one-time, ~22 MB)...")
    urllib.request.urlretrieve(MAVEN_JAR_URL, JAR_PATH)

    print("Extracting...")
    with zipfile.ZipFile(JAR_PATH, "r") as zf:
        zf.extract("postgres-windows-x86_64.txz", TOOLS)

    pgsql = TOOLS / "pgsql"
    pgsql.mkdir(parents=True, exist_ok=True)
    with tarfile.open(TXZ_PATH, "r:xz") as tar:
        tar.extractall(pgsql)

    if not pg_ctl.exists():
        raise RuntimeError(f"pg_ctl.exe not found after extract at {pg_ctl}")

    # Keep disk tidy — binaries stay; archives can go.
    JAR_PATH.unlink(missing_ok=True)
    TXZ_PATH.unlink(missing_ok=True)
    print("Portable PostgreSQL ready.")


def _write_config() -> None:
    conf = PG_DATA / "postgresql.conf"
    text = conf.read_text(encoding="utf-8", errors="ignore")
    lines = []
    seen_listen = seen_port = False
    for line in text.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("listen_addresses") or stripped.startswith("#listen_addresses"):
            lines.append("listen_addresses = '127.0.0.1'")
            seen_listen = True
        elif stripped.startswith("port ") or stripped.startswith("port=") or stripped.startswith("#port"):
            lines.append(f"port = {PORT}")
            seen_port = True
        else:
            lines.append(line)
    if not seen_listen:
        lines.append("listen_addresses = '127.0.0.1'")
    if not seen_port:
        lines.append(f"port = {PORT}")
    conf.write_text("\n".join(lines) + "\n", encoding="utf-8")

    hba = PG_DATA / "pg_hba.conf"
    hba.write_text(
        "\n".join(
            [
                "# TYPE  DATABASE        USER            ADDRESS                 METHOD",
                "local   all             all                                     trust",
                "host    all             all             127.0.0.1/32            trust",
                "host    all             all             ::1/128                 trust",
                "",
            ]
        ),
        encoding="utf-8",
    )


def ensure_cluster() -> None:
    if (PG_DATA / "PG_VERSION").exists():
        _write_config()
        return

    print("Initializing local Postgres data directory...")
    PG_DATA.mkdir(parents=True, exist_ok=True)
    result = _run(
        [
            str(PG_BIN / "initdb.exe"),
            "-D",
            str(PG_DATA),
            "-U",
            "postgres",
            "-A",
            "trust",
            "-E",
            "UTF8",
            "--locale=C",
        ]
    )
    if result.returncode != 0:
        raise RuntimeError(f"initdb failed:\n{result.stdout}\n{result.stderr}")
    _write_config()


def is_running() -> bool:
    result = _run([str(PG_BIN / "pg_ctl.exe"), "-D", str(PG_DATA), "status"])
    return result.returncode == 0 and "server is running" in (result.stdout + result.stderr)


def start_server() -> None:
    if is_running():
        print(f"Postgres already running on 127.0.0.1:{PORT}")
        return

    print(f"Starting Postgres on 127.0.0.1:{PORT}...")
    result = _run(
        [
            str(PG_BIN / "pg_ctl.exe"),
            "-D",
            str(PG_DATA),
            "-l",
            str(PG_LOG),
            "-o",
            f"-p {PORT}",
            "start",
        ]
    )
    if result.returncode != 0 and not is_running():
        log_tail = PG_LOG.read_text(encoding="utf-8", errors="ignore")[-2000:] if PG_LOG.exists() else ""
        raise RuntimeError(f"pg_ctl start failed:\n{result.stdout}\n{result.stderr}\n{log_tail}")

    for _ in range(30):
        if _can_connect("postgres", "postgres"):
            break
        time.sleep(0.3)
    else:
        raise RuntimeError("Postgres started but did not accept connections in time.")
    print("Postgres is up.")


def stop_server() -> None:
    if not (PG_DATA / "PG_VERSION").exists():
        print("No local Postgres data directory — nothing to stop.")
        return
    if not is_running():
        print("Postgres is not running.")
        return
    print("Stopping Postgres...")
    _run([str(PG_BIN / "pg_ctl.exe"), "-D", str(PG_DATA), "stop", "-m", "fast"])
    print("Postgres stopped.")


def _can_connect(user: str, dbname: str, password: str | None = None) -> bool:
    try:
        import psycopg

        kwargs = {"host": "127.0.0.1", "port": PORT, "user": user, "dbname": dbname, "connect_timeout": 3}
        if password is not None:
            kwargs["password"] = password
        with psycopg.connect(**kwargs) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
        return True
    except Exception:
        return False


def ensure_app_database() -> None:
    import psycopg
    from psycopg import sql

    # CREATE/ALTER ROLE ... PASSWORD does not accept bind parameters ($1) — Postgres
    # treats $1 as literal syntax. Use sql.Literal so the password is inlined safely.
    with psycopg.connect(host="127.0.0.1", port=PORT, user="postgres", dbname="postgres") as conn:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (APP_USER,))
            if cur.fetchone() is None:
                cur.execute(
                    sql.SQL("CREATE ROLE {} LOGIN PASSWORD {}").format(
                        sql.Identifier(APP_USER),
                        sql.Literal(APP_PASSWORD),
                    )
                )
            else:
                cur.execute(
                    sql.SQL("ALTER ROLE {} WITH PASSWORD {}").format(
                        sql.Identifier(APP_USER),
                        sql.Literal(APP_PASSWORD),
                    )
                )
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (APP_DB,))
            if cur.fetchone() is None:
                cur.execute(
                    sql.SQL("CREATE DATABASE {} OWNER {}").format(
                        sql.Identifier(APP_DB),
                        sql.Identifier(APP_USER),
                    )
                )
            else:
                cur.execute(
                    sql.SQL("ALTER DATABASE {} OWNER TO {}").format(
                        sql.Identifier(APP_DB),
                        sql.Identifier(APP_USER),
                    )
                )

    if not _can_connect(APP_USER, APP_DB, APP_PASSWORD):
        raise RuntimeError("pic_lite database exists but login failed.")
    print(f"OK: {APP_USER}@{APP_DB} on 127.0.0.1:{PORT}")


def main() -> int:
    action = sys.argv[1] if len(sys.argv) > 1 else "start"
    try:
        if action == "stop":
            if (PG_BIN / "pg_ctl.exe").exists():
                stop_server()
            return 0

        ensure_binaries()
        ensure_cluster()
        start_server()
        ensure_app_database()
        # Expose URL for the parent shell if needed
        os.environ.setdefault(
            "DATABASE_URL",
            f"postgresql+psycopg://{APP_USER}:{APP_PASSWORD}@127.0.0.1:{PORT}/{APP_DB}",
        )
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
