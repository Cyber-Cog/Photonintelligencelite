"""Unit tests for fault-run integrity checker (mocked HTTP — no real API key)."""
from __future__ import annotations

import json

import httpx
import pytest

from backend.app.config import Settings
from backend.app.services.fault_run_ai_check import (
    build_integrity_evidence,
    call_zenmux_integrity,
    format_integrity_progress,
    run_deterministic_checks,
    run_fault_run_integrity_check,
)


def _settings(monkeypatch: pytest.MonkeyPatch, **env) -> Settings:
    """Build Settings without loading .env; env vars control AI fields (aliases)."""
    monkeypatch.setenv("DATABASE_URL", "sqlite+pysqlite:///:memory:")
    monkeypatch.setenv("SESSION_SECRET", "test")
    # Clear any process/.env key unless the test opts in.
    if "ZENMUX_API_KEY" not in env:
        monkeypatch.setenv("ZENMUX_API_KEY", "")
    if "GEMINI_API_KEY" not in env:
        monkeypatch.setenv("GEMINI_API_KEY", "")
    for k, v in env.items():
        monkeypatch.setenv(k, "" if v is None else str(v))
    return Settings(_env_file=None)


def test_deterministic_needs_data_with_findings():
    evidence = build_integrity_evidence(
        results=[
            {
                "algorithm_id": "soiling",
                "title": "Soiling",
                "status": "unavailable",
                "module_kind": "fault",
                "tables": [{"title": "t", "columns": ["a"], "rows": [["x"]]}],
                "affected_equipment": [],
                "missing_fields": ["poa_w_m2"],
            }
        ],
        kpis={"fault_count": 0},
    )
    findings = run_deterministic_checks(evidence)
    codes = {f["code"] for f in findings}
    assert "needs_data_with_findings" in codes


def test_deterministic_summary_status_mismatch():
    evidence = build_integrity_evidence(
        results=[
            {
                "algorithm_id": "clipping",
                "title": "Clipping",
                "status": "ok",
                "module_kind": "fault",
                "tables": [],
                "affected_equipment": [],
            }
        ],
        kpis={"fault_count": 0},
        results_summary={"modules": [{"id": "clipping", "status": "unavailable", "loss_kwh": None}]},
    )
    findings = run_deterministic_checks(evidence)
    assert any(f["code"] == "status_mismatch_summary_vs_results" for f in findings)


def test_skipped_when_no_api_key_and_clean(monkeypatch):
    out = run_fault_run_integrity_check(
        _settings(monkeypatch),
        results=[
            {
                "algorithm_id": "clipping",
                "status": "ok",
                "module_kind": "fault",
                "tables": [],
                "affected_equipment": [],
                "severity": "info",
            }
        ],
        kpis={"fault_count": 0},
    )
    # Still visible to UI — rules pass + honest AI-not-configured (do not hide panel).
    assert out["status"] == "pass"
    assert out["configured"] is False
    assert out["ai_layer"] == "not_configured"
    assert out["source"] == "rules"
    assert "not configured" in out["summary"].lower()


def test_rules_surface_without_api_key(monkeypatch):
    out = run_fault_run_integrity_check(
        _settings(monkeypatch),
        results=[
            {
                "algorithm_id": "soiling",
                "status": "unavailable",
                "module_kind": "fault",
                "tables": [{"title": "t", "columns": ["a"], "rows": [[1]]}],
                "affected_equipment": [],
            }
        ],
        kpis={"fault_count": 0},
    )
    assert out["status"] == "fail"
    assert out["source"] == "rules"
    assert out["configured"] is False
    assert out["ai_layer"] == "not_configured"
    assert out["rules_finding_count"] >= 1


def test_format_integrity_progress_not_configured():
    from backend.app.services.fault_run_ai_check import format_integrity_progress

    line = format_integrity_progress(
        {
            "rules_finding_count": 0,
            "ai_layer": "not_configured",
            "findings": [],
        }
    )
    assert line.startswith("AI integrity · rules: 0 finding(s)")
    assert "AI: skipped (AI not configured)" in line or "skipped (AI not configured)" in line


def test_format_integrity_progress_mg_key_failure():
    from backend.app.services.fault_run_ai_check import format_integrity_progress

    line = format_integrity_progress(
        {
            "rules_finding_count": 2,
            "ai_layer": "failed",
            "provider": "zenmux",
            "error": (
                "AI provider returned HTTP 403. This looks like a management key (sk-mg-v1-…). "
                "Chat completions usually need a chat key (sk-ai-v1-…)."
            ),
            "findings": [],
        }
    )
    assert "rules: 2 finding(s)" in line
    assert "ZenMux: failed" in line
    assert "sk-ai-v1" in line


def test_zenmux_call_parses_json(monkeypatch):
    settings = _settings(monkeypatch, ZENMUX_API_KEY="sk-ai-v1-test-key")
    assert (settings.zenmux_api_key or "").startswith("sk-ai")

    class _Resp:
        status_code = 200
        text = ""

        def json(self):
            return {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "overall": "warn",
                                    "summary": "One mismatch",
                                    "findings": [
                                        {
                                            "severity": "warn",
                                            "code": "ai_display_gap",
                                            "message": "Empty table for high severity",
                                            "module_id": "soiling",
                                        }
                                    ],
                                }
                            )
                        }
                    }
                ]
            }

    class _Client:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def post(self, *a, **k):
            return _Resp()

    monkeypatch.setattr(httpx, "Client", _Client)
    findings, overall, model, err = call_zenmux_integrity(settings, {"modules": []}, [])
    assert err is None
    assert overall == "warn"
    assert model == "google/gemini-2.5-flash"
    assert findings[0]["code"] == "ai_display_gap"


def test_gemini_integrity_preferred(monkeypatch):
    settings = _settings(monkeypatch, GEMINI_API_KEY="AQ.test-gemini-key")

    class _Resp:
        status_code = 200
        text = ""

        def json(self):
            return {
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {
                                    "text": json.dumps(
                                        {
                                            "overall": "pass",
                                            "summary": "OK",
                                            "findings": [],
                                        }
                                    )
                                }
                            ]
                        }
                    }
                ]
            }

    class _Client:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def post(self, url, *a, **k):
            assert "generativelanguage.googleapis.com" in str(url)
            return _Resp()

    monkeypatch.setattr(httpx, "Client", _Client)
    out = run_fault_run_integrity_check(
        settings,
        results=[
            {
                "algorithm_id": "clipping",
                "status": "ok",
                "module_kind": "fault",
                "tables": [],
                "affected_equipment": [],
                "severity": "info",
            }
        ],
        kpis={"fault_count": 0},
        results_summary={"modules": [{"id": "clipping", "status": "ok"}]},
    )
    assert out["ai_layer"] == "ok"
    assert out["provider"] == "gemini"
    assert out["source"] == "rules+gemini"
    assert "gemini" in out["source"]
    assert "Gemini: ok" in format_integrity_progress(out)


def test_management_key_hint_on_401(monkeypatch):
    settings = _settings(monkeypatch, ZENMUX_API_KEY="sk-mg-v1-fake-management-key")

    class _Resp:
        status_code = 401
        text = "invalid api key"

        def json(self):
            return {}

    class _Client:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def post(self, *a, **k):
            return _Resp()

    monkeypatch.setattr(httpx, "Client", _Client)
    findings, overall, model, err = call_zenmux_integrity(settings, {"modules": []}, [])
    assert findings == []
    assert overall == "error"
    assert err is not None
    assert "sk-ai-v1" in err
    assert "management" in err.lower()


def test_full_check_merges_ai(monkeypatch):
    settings = _settings(monkeypatch, ZENMUX_API_KEY="sk-ai-v1-test")

    class _Resp:
        status_code = 200
        text = ""

        def json(self):
            return {
                "choices": [
                    {
                        "message": {
                            "content": '{"overall":"pass","summary":"OK","findings":[]}'
                        }
                    }
                ]
            }

    class _Client:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def post(self, *a, **k):
            return _Resp()

    monkeypatch.setattr(httpx, "Client", _Client)
    out = run_fault_run_integrity_check(
        settings,
        results=[
            {
                "algorithm_id": "clipping",
                "status": "ok",
                "module_kind": "fault",
                "tables": [],
                "affected_equipment": [],
                "severity": "info",
            }
        ],
        kpis={"fault_count": 0},
        results_summary={"modules": [{"id": "clipping", "status": "ok"}]},
    )
    assert out["configured"] is True
    assert out["source"] in {"rules+ai", "rules+zenmux"}
    assert out["ai_layer"] == "ok"
    assert out["status"] == "pass"
    assert out["error"] is None
    assert "AI integrity ·" in format_integrity_progress(out)


def test_full_check_ai_403_surfaces_failed_layer(monkeypatch):
    settings = _settings(monkeypatch, ZENMUX_API_KEY="sk-mg-v1-fake")

    class _Resp:
        status_code = 403
        text = '{"error":{"message":"access_denied"}}'

        def json(self):
            return {}

    class _Client:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def post(self, *a, **k):
            return _Resp()

    monkeypatch.setattr(httpx, "Client", _Client)
    out = run_fault_run_integrity_check(
        settings,
        results=[
            {
                "algorithm_id": "clipping",
                "status": "ok",
                "module_kind": "fault",
                "tables": [],
                "affected_equipment": [],
                "severity": "info",
            }
        ],
        kpis={"fault_count": 0},
    )
    assert out["ai_layer"] == "failed"
    assert out["configured"] is True
    assert out["status"] == "error"
    assert out["error"]
    line = format_integrity_progress(out)
    assert "failed" in line
    assert "sk-ai-v1" in line


def test_console_progress_strings_match_frontend_filters():
    """Analysis Console (useAnalysisLog) keys off these exact progress prefixes."""
    import re

    start = "AI integrity check starting…"
    assert re.match(r"^AI integrity check starting", start, re.I)
    done = format_integrity_progress(
        {
            "rules_finding_count": 0,
            "ai_layer": "failed",
            "error": "HTTP 403 management key sk-mg",
            "provider": "zenmux",
        }
    )
    assert re.match(r"^AI integrity\b", done, re.I)
    assert re.search(r"failed|rejected", done, re.I)
    complete = f"Analysis complete · {done}"
    assert re.match(r"^Analysis complete\s*·\s*AI integrity", complete, re.I)
    # Exact legacy mute must not swallow the AI-bearing completion line.
    assert complete != "Analysis complete."