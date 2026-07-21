"""Local all-in-one launcher used by start.bat (no Docker).

Starts bundled Postgres, API (uvicorn), and frontend (Vite), then opens the browser.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VENV_PY = ROOT / ".venv" / "Scripts" / "python.exe"
API_URL = "http://127.0.0.1:8000/api/health"
UI_URL = "http://localhost:5173"

DATABASE_URL = "postgresql+psycopg://pic_lite:pic_lite@127.0.0.1:5432/pic_lite"


def _env() -> dict[str, str]:
    env = os.environ.copy()
    env["DATABASE_URL"] = DATABASE_URL
    env["JOB_ROOT"] = str(ROOT / "uploads")
    env["PIC_LITE_FREE_TIER"] = "false"
    env["CORS_ORIGINS"] = "http://localhost:5173"
    env["PUBLIC_APP_URL"] = "http://localhost:5173"
    # Empty = same-origin via Vite /api proxy (needed for reliable template downloads).
    env["VITE_API_BASE_URL"] = ""
    env["PYTHONPATH"] = str(ROOT)
    # Preserve auth env from user/.env if already set in the process environment.
    return env


def _ensure_venv_and_deps() -> None:
    if not VENV_PY.exists():
        print("Creating Python virtual environment...")
        subprocess.check_call([sys.executable, "-m", "venv", str(ROOT / ".venv")])
    print("Checking Python packages...")
    subprocess.check_call([str(VENV_PY), "-m", "pip", "install", "-q", "-r", str(ROOT / "requirements.txt")])


def _ensure_frontend_deps() -> None:
    node_modules = ROOT / "frontend" / "node_modules"
    if node_modules.exists():
        return
    npm = shutil.which("npm")
    if not npm:
        raise RuntimeError("npm not found on PATH. Install Node.js 20+ from https://nodejs.org")
    print("Installing frontend packages (first run only)...")
    subprocess.check_call([npm, "install"], cwd=str(ROOT / "frontend"))


def _start_postgres() -> None:
    print("Starting local Postgres...")
    subprocess.check_call([str(VENV_PY), str(ROOT / "scripts" / "start_local_postgres.py"), "start"])


def _wait_http(url: str, timeout_sec: float = 90.0) -> bool:
    import urllib.error
    import urllib.request

    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as resp:
                if resp.status == 200:
                    return True
        except urllib.error.HTTPError as exc:
            # Vite may briefly return non-200 while compiling; keep waiting unless connection fails forever.
            if exc.code < 500:
                return True
        except Exception:
            pass
        time.sleep(0.8)
    return False


def _wait_ui_ready(timeout_sec: float = 90.0) -> bool:
    """UI root must respond AND Tailwind/CSS must compile (blank-page guard)."""
    import urllib.error
    import urllib.request

    css_url = f"{UI_URL.rstrip('/')}/src/index.css"
    deadline = time.time() + timeout_sec
    root_ok = False
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(UI_URL, timeout=2) as resp:
                root_ok = resp.status == 200
        except Exception:
            root_ok = False
        if not root_ok:
            time.sleep(0.8)
            continue
        try:
            with urllib.request.urlopen(css_url, timeout=3) as resp:
                body = resp.read(800).decode("utf-8", errors="ignore")
                if resp.status == 200 and "Internal Server Error" not in body and "postcss" not in body.lower():
                    return True
        except urllib.error.HTTPError:
            pass
        except Exception:
            pass
        time.sleep(0.8)
    return False


def _kill_port(port: int) -> None:
    """Best-effort: free a TCP listen port on Windows so restart is clean."""
    try:
        out = subprocess.check_output(["netstat", "-ano"], text=True, errors="ignore")
    except Exception:
        return
    pids: set[int] = set()
    for line in out.splitlines():
        if f":{port} " not in line or "LISTENING" not in line:
            continue
        parts = line.split()
        if parts:
            try:
                pids.add(int(parts[-1]))
            except ValueError:
                pass
    for pid in pids:
        subprocess.run(["taskkill", "/PID", str(pid), "/F", "/T"], capture_output=True)


def _spawn_logged(name: str, args: list[str], cwd: Path, env: dict[str, str]) -> subprocess.Popen:
    log_path = ROOT / ".tools" / f"{name}.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_f = open(log_path, "w", encoding="utf-8", errors="replace")
    creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    # On Windows, npm is typically npm.cmd — list-form Popen cannot launch .cmd without shell.
    use_shell = os.name == "nt" and str(args[0]).lower().endswith((".cmd", ".bat"))
    popen_args: str | list[str]
    if use_shell:
        popen_args = subprocess.list2cmdline(args)
    else:
        popen_args = args
    return subprocess.Popen(
        popen_args,
        cwd=str(cwd),
        env=env,
        stdout=log_f,
        stderr=subprocess.STDOUT,
        creationflags=creationflags,
        shell=use_shell,
    )


def main() -> int:
    os.chdir(ROOT)
    (ROOT / "uploads").mkdir(exist_ok=True)
    (ROOT / "frontend" / ".env").write_text("VITE_API_BASE_URL=http://localhost:8000\n", encoding="utf-8")

    if shutil.which("node") is None:
        print("ERROR: Node.js is not on PATH. Install Node 20+ from https://nodejs.org")
        return 1

    try:
        _ensure_venv_and_deps()
        _start_postgres()
        _ensure_frontend_deps()
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR during setup: {exc}")
        return 1

    env = _env()

    # Stop any previous API/UI still bound to our ports so start.bat is idempotent.
    _kill_port(8000)
    _kill_port(5173)

    # No --reload: WatchFiles on Windows has left a stale single-job process serving
    # after a partial reload, which breaks concurrent analyses until a full restart.
    # After analytics/backend code changes, re-run start.bat / this launcher so workers
    # pick up new exports (e.g. build_excel_report) — partial file edits are not hot-loaded.
    print("Starting API on http://localhost:8000 ...")
    api_proc = _spawn_logged(
        "api",
        [
            str(VENV_PY),
            "-m",
            "uvicorn",
            "backend.app.main:app",
            "--host",
            "0.0.0.0",
            "--port",
            "8000",
        ],
        ROOT,
        env,
    )

    print("Starting UI on http://localhost:5173 ...")
    npm = shutil.which("npm") or shutil.which("npm.cmd")
    if not npm:
        print("ERROR: npm not found")
        return 1
    ui_proc = _spawn_logged(
        "ui",
        [npm, "run", "dev", "--", "--host", "0.0.0.0", "--port", "5173"],
        ROOT / "frontend",
        env,
    )

    print("Waiting for API health...")
    api_ok = _wait_http(API_URL, timeout_sec=90)
    print("Waiting for UI (including CSS compile)...")
    ui_ok = _wait_ui_ready(timeout_sec=90)

    print()
    print("=" * 40)
    if api_ok:
        print("API  OK  -> http://localhost:8000/docs")
    else:
        print("API  NOT READY  -> see .tools/api.log")
        print((ROOT / ".tools" / "api.log").read_text(encoding="utf-8", errors="ignore")[-800:])
    if ui_ok:
        print("UI   OK  -> http://localhost:5173")
        webbrowser.open(UI_URL)
    else:
        print("UI   NOT READY  -> see .tools/ui.log")
        print((ROOT / ".tools" / "ui.log").read_text(encoding="utf-8", errors="ignore")[-800:])
        if ui_proc.poll() is not None:
            print(f"UI process exited early with code {ui_proc.returncode}")
    print("=" * 40)
    print("Services keep running in the background.")
    print("Run stop.bat when finished.")
    print()

    if not api_ok or not ui_ok:
        return 1
    # Keep PIDs discoverable for stop.bat
    (ROOT / ".tools" / "pids.txt").write_text(f"{api_proc.pid}\n{ui_proc.pid}\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
