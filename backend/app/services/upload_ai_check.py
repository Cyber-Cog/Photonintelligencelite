"""Upload/parse-time integrity check (rules always; ZenMux when configured).

Runs after column detection / upload intelligence — visible on Upload review
without completing Analyze. Not a chatbot.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Iterable

import httpx

from analytics.common.wide_headers import count_wide_device_columns, parse_wide_device_column
from backend.app.config import Settings
from backend.app.services.fault_run_ai_check import (
    _finding,
    _overall_from_findings,
    ai_check_configured,
    merge_findings,
)

logger = logging.getLogger("pic_lite.upload_ai_check")

_UPLOAD_SYSTEM_PROMPT = """You are a PIC Lite upload/parse integrity checker for solar SCADA files.
Given detected columns, mapping suggestions, and hierarchy signal counts, find issues that
block or confuse Setup — especially unmapped obvious headers and parse failures.

Focus on:
- Only timestamp mapped while other headers look like power/current/irradiance
- Wide device×metric columns that were not reshaped
- File labeled inverter AC/DC but missing AC/DC or equipment ID after mapping
- Contradictions between claimed layout and empty signal matrix

Do NOT invent plant faults. Return ONLY valid JSON:
{
  "overall": "pass" | "warn" | "fail",
  "summary": "one short sentence",
  "findings": [
    {"severity": "pass"|"warn"|"fail", "code": "snake_case", "message": "short", "module_id": null}
  ],
  "mapping_hints": [
    {"column_name": "raw header", "canonical_field": "ac_power_kw", "confidence": 0.0}
  ]
}
Prefer few high-signal findings. mapping_hints are suggestions only (do not claim applied).
"""


def build_upload_evidence(
    *,
    columns: list[str],
    suggestions: Iterable[Any],
    hierarchy: list[dict[str, Any]] | None = None,
    architecture_summary: dict[str, Any] | None = None,
    original_filename: str | None = None,
    parse_report: dict[str, Any] | None = None,
    reshape_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    mapped: list[dict[str, Any]] = []
    unmapped: list[str] = []
    for s in suggestions:
        col = getattr(s, "column_name", None) or (s.get("column_name") if isinstance(s, dict) else None)
        field = getattr(s, "canonical_field", None) or (s.get("canonical_field") if isinstance(s, dict) else None)
        conf = getattr(s, "confidence", None) if not isinstance(s, dict) else s.get("confidence")
        if col and field and field != "ignore":
            mapped.append({"column": col, "field": field, "confidence": conf})
        elif col:
            unmapped.append(str(col))

    fields = {m["field"] for m in mapped}
    wide_n, wide_devices = count_wide_device_columns(columns)
    return {
        "original_filename": original_filename,
        "column_count": len(columns),
        "columns_sample": columns[:40],
        "mapped_fields": sorted(fields),
        "mapped_count": len(mapped),
        "unmapped_count": len(unmapped),
        "unmapped_sample": unmapped[:20],
        "wide_device_columns": wide_n,
        "wide_device_count": wide_devices,
        "hierarchy": [
            {
                "level_id": h.get("level_id"),
                "detected": h.get("detected_count"),
                "total": h.get("total_count"),
            }
            for h in (hierarchy or [])
        ],
        "architecture_detected": bool((architecture_summary or {}).get("detected")),
        "architecture_inverters": (architecture_summary or {}).get("inverter_count"),
        "parse_report": parse_report,
        "reshape_report": reshape_report,
    }


def run_upload_deterministic_checks(evidence: dict[str, Any]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    fields = set(evidence.get("mapped_fields") or [])
    cols = list(evidence.get("columns_sample") or [])
    mapped_count = int(evidence.get("mapped_count") or 0)
    wide_n = int(evidence.get("wide_device_columns") or 0)

    if "timestamp" not in fields:
        findings.append(
            _finding("fail", "missing_timestamp", "No timestamp column was mapped after parse.")
        )

    metric_fields = fields & {
        "ac_power_kw",
        "dc_power_kw",
        "dc_current_a",
        "dc_voltage_v",
        "poa_w_m2",
        "ghi_w_m2",
        "module_temp_c",
        "ambient_temp_c",
        "device_id",
        "inverter_id",
        "scb_id",
        "string_id",
        "icr_id",
    }
    if "timestamp" in fields and not metric_fields and mapped_count <= 2:
        findings.append(
            _finding(
                "fail",
                "only_timestamp_mapped",
                "Only timestamp-like columns mapped — power/current/IDs were not detected.",
            )
        )

    reshape = evidence.get("reshape_report") or {}
    if wide_n >= 4 and not reshape.get("reshaped") and "device_id" not in fields and "inverter_id" not in fields:
        findings.append(
            _finding(
                "fail",
                "wide_layout_unmelted",
                f"Detected {wide_n} wide device×metric columns but file was not reshaped to tidy long form.",
            )
        )

    # Obvious wide headers still unmapped (pre-melt path / reshape skipped)
    obvious_unmapped = 0
    for c in evidence.get("unmapped_sample") or []:
        if parse_wide_device_column(str(c)) is not None:
            obvious_unmapped += 1
    if obvious_unmapped >= 3 and "ac_power_kw" not in fields:
        findings.append(
            _finding(
                "warn",
                "obvious_wide_headers_unmapped",
                f"{obvious_unmapped}+ headers look like inverter power/current but were not mapped.",
            )
        )

    fname = (evidence.get("original_filename") or "").lower()
    if any(tok in fname for tok in ("inverter", "ac/dc", "acdc", "inv")):
        if "ac_power_kw" not in fields and "dc_power_kw" not in fields:
            findings.append(
                _finding(
                    "warn",
                    "file_type_vs_signals",
                    "Filename suggests inverter AC/DC data but AC/DC power was not detected.",
                )
            )

    if evidence.get("architecture_detected") is False and (
        "device_id" in fields or "inverter_id" in fields
    ):
        # Soft note only when IDs mapped but arch still missing (rare after melt)
        inv_n = evidence.get("architecture_inverters") or 0
        if not inv_n:
            findings.append(
                _finding(
                    "warn",
                    "ids_without_architecture_counts",
                    "Equipment ID mapped but architecture counts are still empty.",
                )
            )

    # Healthy inverter AC/DC tidy outcome
    if (
        "timestamp" in fields
        and ("device_id" in fields or "inverter_id" in fields)
        and "ac_power_kw" in fields
        and not findings
    ):
        findings.append(
            _finding(
                "pass",
                "inverter_signals_ok",
                "Timestamp, equipment ID, and AC power detected after parse.",
            )
        )

    return [f for f in findings if f.get("severity") != "pass"] + [
        f for f in findings if f.get("severity") == "pass"
    ]


def _call_zenmux_upload(
    settings: Settings,
    evidence: dict[str, Any],
    rule_findings: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str, str | None, str | None]:
    """Returns (ai_findings, mapping_hints, overall_hint, model, error)."""
    key = (settings.zenmux_api_key or "").strip()
    if not key:
        return [], [], "pass", None, None

    base = (settings.zenmux_base_url or "https://zenmux.ai/api/v1").rstrip("/")
    model = (settings.zenmux_model or "google/gemini-2.5-flash").strip()
    payload = {
        "model": model,
        "temperature": 0.1,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": _UPLOAD_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": json.dumps(
                    {"evidence": evidence, "rule_findings": rule_findings},
                    default=str,
                )[:12000],
            },
        ],
    }
    try:
        with httpx.Client(timeout=settings.zenmux_timeout_sec) as client:
            resp = client.post(
                f"{base}/chat/completions",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json=payload,
            )
            if resp.status_code >= 400:
                return [], [], "pass", model, f"ZenMux HTTP {resp.status_code}: {resp.text[:200]}"
            body = resp.json()
            content = (
                ((body.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning("upload ZenMux call failed: %s", exc)
        return [], [], "pass", model, str(exc)[:240]

    try:
        import re

        match = re.search(r"\{.*\}", content, re.DOTALL)
        data = json.loads(match.group(0) if match else content)
    except Exception:  # noqa: BLE001
        return [], [], "pass", model, "AI returned non-JSON"

    findings_in = data.get("findings") or []
    findings: list[dict[str, Any]] = []
    if isinstance(findings_in, list):
        for item in findings_in:
            if not isinstance(item, dict):
                continue
            sev = str(item.get("severity") or "warn").lower()
            if sev not in {"pass", "warn", "fail"}:
                sev = "warn"
            msg = str(item.get("message") or "").strip()[:400]
            if not msg:
                continue
            findings.append(
                _finding(sev, str(item.get("code") or "ai_upload_note")[:64], msg, None)
            )
    hints: list[dict[str, Any]] = []
    for h in data.get("mapping_hints") or []:
        if not isinstance(h, dict):
            continue
        col = h.get("column_name")
        field = h.get("canonical_field")
        if col and field:
            hints.append(
                {
                    "column_name": str(col)[:200],
                    "canonical_field": str(field)[:64],
                    "confidence": float(h.get("confidence") or 0.0),
                }
            )
    overall = str(data.get("overall") or _overall_from_findings(findings)).lower()
    if overall not in {"pass", "warn", "fail"}:
        overall = _overall_from_findings(findings)
    return findings, hints, overall, model, None


def run_upload_integrity_check(
    settings: Settings,
    *,
    columns: list[str],
    suggestions: Iterable[Any],
    hierarchy: list[dict[str, Any]] | None = None,
    architecture_summary: dict[str, Any] | None = None,
    original_filename: str | None = None,
    parse_report: dict[str, Any] | None = None,
    reshape_report: dict[str, Any] | None = None,
    use_ai: bool = True,
) -> dict[str, Any]:
    evidence = build_upload_evidence(
        columns=columns,
        suggestions=suggestions,
        hierarchy=hierarchy,
        architecture_summary=architecture_summary,
        original_filename=original_filename,
        parse_report=parse_report,
        reshape_report=reshape_report,
    )
    # Drop pass-only noise from rules for merge; keep failures/warns
    all_rules = run_upload_deterministic_checks(evidence)
    rule_findings = [f for f in all_rules if f.get("severity") != "pass"]
    checked_at = datetime.now(timezone.utc).isoformat()
    configured = ai_check_configured(settings)

    base = {
        "phase": "upload",
        "configured": configured,
        "checked_at": checked_at,
        "mapping_hints": [],
        "model": None,
        "error": None,
    }

    if not use_ai or not configured:
        overall = _overall_from_findings(rule_findings) if rule_findings else "pass"
        return {
            **base,
            "status": overall,
            "source": "rules",
            "summary": {
                "pass": "Upload parse check OK (rules).",
                "warn": "Upload parse check found warnings.",
                "fail": "Upload parse check found failures.",
            }[overall],
            "findings": rule_findings,
        }

    ai_findings, hints, ai_overall, model, error = _call_zenmux_upload(
        settings, evidence, rule_findings
    )
    if error:
        overall = _overall_from_findings(rule_findings) if rule_findings else "error"
        return {
            **base,
            "status": overall if rule_findings else "error",
            "source": "rules" if rule_findings else "none",
            "summary": (
                "AI upload check failed; showing rule findings."
                if rule_findings
                else "AI upload check failed."
            ),
            "findings": rule_findings,
            "model": model,
            "error": error,
        }

    merged = merge_findings(rule_findings, [f for f in ai_findings if f.get("severity") != "pass"])
    overall = _overall_from_findings(merged)
    if ai_overall == "fail" or (ai_overall == "warn" and overall == "pass"):
        overall = ai_overall
    return {
        **base,
        "status": overall,
        "source": "rules+ai",
        "summary": {
            "pass": "Upload parse check passed.",
            "warn": "Upload parse check found warnings.",
            "fail": "Upload parse check found failures.",
        }[overall],
        "findings": merged,
        "mapping_hints": hints[:12],
        "model": model,
    }
