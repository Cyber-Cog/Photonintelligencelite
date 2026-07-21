"""Benchmark ingest/standardization (Phase 0) and the full analysis pipeline (Phase 2)
against a running PIC Lite API instance — local or deployed.

Phase 0 usage (ingest only, measures upload -> mapping -> validate -> normalize):
    python scripts/benchmark_ingest.py --base-url https://pic-lite-api.onrender.com --stage ingest

Phase 2/4 usage (full pipeline, used to set JOB_TIMEOUT_SEC = 3x this number, see
docs/deployment.md "Setting JOB_TIMEOUT_SEC"):
    python scripts/benchmark_ingest.py --base-url https://pic-lite-api.onrender.com --stage full

This intentionally does not import the analytics package directly — it drives the real
HTTP API end-to-end so the measured number reflects what a user actually experiences,
including Render cold start if the instance was asleep.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests.fixtures.synthetic_generator import write_demo_files  # noqa: E402


def _wait_for_terminal_state(client: httpx.Client, base_url: str, job_id: str, poll_sec: float = 2.5, hard_timeout_sec: float = 900) -> tuple[str, float]:
    start = time.perf_counter()
    while True:
        resp = client.get(f"{base_url}/api/jobs/{job_id}/status")
        resp.raise_for_status()
        data = resp.json()
        elapsed = time.perf_counter() - start
        if not data["is_active"]:
            return data["state"], elapsed
        if elapsed > hard_timeout_sec:
            return "timeout", elapsed
        time.sleep(poll_sec)


def benchmark_ingest_only(base_url: str, csv_path: Path) -> None:
    client = httpx.Client(timeout=120.0)
    t0 = time.perf_counter()
    with open(csv_path, "rb") as f:
        resp = client.post(f"{base_url}/api/upload", files={"file": (csv_path.name, f, "text/csv")})
    resp.raise_for_status()
    upload_data = resp.json()
    t_upload = time.perf_counter() - t0
    print(f"upload + column detection: {t_upload:.2f}s (job_id={upload_data['job_id']})")

    from backend.app.routers.demo import DEMO_MAPPING, DEMO_PLANT

    t1 = time.perf_counter()
    client.post(f"{base_url}/api/mapping", json={"job_id": upload_data["job_id"], "column_to_canonical": {**DEMO_MAPPING, "Timestamp": "timestamp"}}).raise_for_status()
    client.post(f"{base_url}/api/plant-config", json={"job_id": upload_data["job_id"], **DEMO_PLANT}).raise_for_status()
    t_validate = time.perf_counter() - t1
    print(f"validate + standardize + normalize: {t_validate:.2f}s")
    print(f"TOTAL ingest-only wall clock: {t_upload + t_validate:.2f}s")


def benchmark_full_pipeline(base_url: str) -> None:
    client = httpx.Client(timeout=120.0)
    t0 = time.perf_counter()
    resp = client.post(f"{base_url}/api/demo")
    resp.raise_for_status()
    job_id = resp.json()["job_id"]
    state, elapsed = _wait_for_terminal_state(client, base_url, job_id)
    total = time.perf_counter() - t0
    print(f"full demo pipeline: state={state} elapsed={elapsed:.2f}s total_wall_clock={total:.2f}s")
    print(f"Suggested JOB_TIMEOUT_SEC (3x measured): {round(total * 3)}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--stage", choices=["ingest", "full"], default="ingest")
    args = parser.parse_args()

    if args.stage == "ingest":
        fixtures_dir = Path(__file__).resolve().parents[1] / "tests" / "fixtures"
        csv_path = fixtures_dir / "demo_plant_scada.csv"
        if not csv_path.exists():
            write_demo_files(csv_path, fixtures_dir / "demo_plant_ground_truth.json")
        benchmark_ingest_only(args.base_url, csv_path)
    else:
        benchmark_full_pipeline(args.base_url)


if __name__ == "__main__":
    main()
