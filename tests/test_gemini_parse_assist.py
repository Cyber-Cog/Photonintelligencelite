"""Tests for Gemini client + AI parse-assist (mocked HTTP)."""
from __future__ import annotations

import json

import httpx
import pytest

from backend.app.config import Settings
from backend.app.schemas import ColumnMappingSuggestion
from backend.app.services.ai_parse_assist import (
    merge_ai_mappings_into_suggestions,
    needs_parse_assist,
    run_parse_assist,
)
from backend.app.services.gemini_client import call_gemini_json, extract_json_object
from backend.app.services.upload_ai_check import run_upload_integrity_check


def _settings(monkeypatch: pytest.MonkeyPatch, **env) -> Settings:
    monkeypatch.setenv("DATABASE_URL", "sqlite+pysqlite:///:memory:")
    monkeypatch.setenv("SESSION_SECRET", "test")
    if "ZENMUX_API_KEY" not in env:
        monkeypatch.setenv("ZENMUX_API_KEY", "")
    if "GEMINI_API_KEY" not in env:
        monkeypatch.setenv("GEMINI_API_KEY", "")
    for k, v in env.items():
        monkeypatch.setenv(k, "" if v is None else str(v))
    return Settings(_env_file=None)


def test_extract_json_object_fenced():
    assert extract_json_object('{"a": 1}') == {"a": 1}
    assert extract_json_object('note\n{"b": 2}\n') == {"b": 2}


def test_needs_parse_assist_thin_mapping():
    sug = [
        ColumnMappingSuggestion(column_name="Time", canonical_field="timestamp", confidence=1.0, band="auto"),
        ColumnMappingSuggestion(column_name="Weird P", canonical_field=None, confidence=0.0, band="manual"),
        ColumnMappingSuggestion(column_name="Weird I", canonical_field=None, confidence=0.0, band="manual"),
        ColumnMappingSuggestion(column_name="Weird V", canonical_field=None, confidence=0.0, band="manual"),
    ]
    assert needs_parse_assist(sug) is True


def test_merge_high_confidence_only():
    sug = [
        ColumnMappingSuggestion(column_name="InvP", canonical_field=None, confidence=0.0, band="manual"),
        ColumnMappingSuggestion(
            column_name="DateTime", canonical_field="timestamp", confidence=1.0, band="auto"
        ),
    ]
    merged, n = merge_ai_mappings_into_suggestions(
        sug,
        [
            {"column_name": "InvP", "canonical_field": "ac_power_kw", "confidence": 0.92},
            {"column_name": "DateTime", "canonical_field": "ambient_temp_c", "confidence": 0.99},
        ],
    )
    assert n == 1
    by = {s.column_name: s for s in merged}
    assert by["InvP"].canonical_field == "ac_power_kw"
    assert by["DateTime"].canonical_field == "timestamp"  # exact heuristic kept


def test_merge_ai_ignore_does_not_blank_heuristic():
    sug = [
        ColumnMappingSuggestion(
            column_name="ESSP ICR1 Inverter 1 Active Power (kW)",
            canonical_field="ac_power_kw",
            confidence=0.95,
            band="confirm",
        ),
    ]
    merged, n = merge_ai_mappings_into_suggestions(
        sug,
        [
            {
                "column_name": "ESSP ICR1 Inverter 1 Active Power (kW)",
                "canonical_field": "ignore",
                "confidence": 0.99,
            }
        ],
    )
    assert n == 0
    assert merged[0].canonical_field == "ac_power_kw"

def test_call_gemini_json_mocked(monkeypatch):
    settings = _settings(monkeypatch, GEMINI_API_KEY="AQ.test")

    class _Resp:
        status_code = 200
        text = ""

        def json(self):
            return {
                "candidates": [
                    {"content": {"parts": [{"text": '{"ok": true, "n": 1}'}]}}
                ]
            }

    class _Client:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def post(self, url, params=None, **k):
            assert "generateContent" in str(url)
            assert params and "key" in params
            return _Resp()

    monkeypatch.setattr(httpx, "Client", _Client)
    data, model, err = call_gemini_json(settings, system="sys", user="user")
    assert err is None
    assert data == {"ok": True, "n": 1}
    assert model == "gemini-flash-latest"


def test_run_parse_assist_merges(monkeypatch):
    settings = _settings(monkeypatch, GEMINI_API_KEY="AQ.test")
    sug = [
        ColumnMappingSuggestion(column_name="TS", canonical_field="timestamp", confidence=1.0, band="auto"),
        ColumnMappingSuggestion(column_name="P_AC", canonical_field=None, confidence=0.0, band="manual"),
        ColumnMappingSuggestion(column_name="InvID", canonical_field=None, confidence=0.0, band="manual"),
        ColumnMappingSuggestion(column_name="Noise", canonical_field=None, confidence=0.0, band="manual"),
    ]

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
                                            "mappings": [
                                                {
                                                    "column_name": "P_AC",
                                                    "canonical_field": "ac_power_kw",
                                                    "confidence": 0.91,
                                                    "reason": "AC power",
                                                },
                                                {
                                                    "column_name": "InvID",
                                                    "canonical_field": "inverter_id",
                                                    "confidence": 0.88,
                                                },
                                            ]
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

        def post(self, *a, **k):
            return _Resp()

    monkeypatch.setattr(httpx, "Client", _Client)
    out, meta = run_parse_assist(
        settings,
        suggestions=sug,
        columns=[s.column_name for s in sug],
        original_filename="inverter.xlsx",
    )
    assert meta["attempted"] is True
    assert meta["provider"] == "gemini"
    assert meta["error"] is None
    assert meta["applied"] >= 1
    by = {s.column_name: s for s in out}
    assert by["P_AC"].canonical_field == "ac_power_kw"


def test_upload_integrity_gemini_source(monkeypatch):
    settings = _settings(monkeypatch, GEMINI_API_KEY="AQ.test")

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
                                            "mapping_hints": [],
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

        def post(self, *a, **k):
            return _Resp()

    monkeypatch.setattr(httpx, "Client", _Client)
    sug = [
        ColumnMappingSuggestion(
            column_name="Timestamp", canonical_field="timestamp", confidence=1.0, band="auto"
        ),
        ColumnMappingSuggestion(
            column_name="Device", canonical_field="device_id", confidence=1.0, band="auto"
        ),
        ColumnMappingSuggestion(
            column_name="AC Power (kW)", canonical_field="ac_power_kw", confidence=1.0, band="auto"
        ),
    ]
    out = run_upload_integrity_check(
        settings,
        columns=[s.column_name for s in sug],
        suggestions=sug,
        original_filename="tidy.csv",
    )
    assert out["ai_layer"] == "ok"
    assert out["provider"] == "gemini"
    assert out["source"] == "rules+gemini"
