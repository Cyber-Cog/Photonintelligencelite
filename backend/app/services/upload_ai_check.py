"""Upload/parse-time integrity check (rules always; Gemini preferred, ZenMux fallback).

Runs after column detection / upload intelligence — visible on Upload review
without completing Analyze. Not a chatbot.
"""
from __future__ import annotations

import json
import logging
import re
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
from backend.app.services.gemini_client import call_gemini_json, gemini_configured

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
    if reshape.get("reshaped"):
        wide_melted = int(reshape.get("scb_count") or 0) + int(reshape.get("inverter_count") or 0)
        n_rows = int(reshape.get("row_count") or 0)
        findings.append(
            _finding(
                "pass",
                "wide_layout_reshaped",
                f"Reshaped wide device×metric columns into tidy long form"
                + (f" ({n_rows:,} rows" if n_rows else "")
                + (f", {reshape.get('scb_count')} SCB(s)" if reshape.get("scb_count") else "")
                + (f", {reshape.get('inverter_count')} inverter(s)" if reshape.get("inverter_count") else "")
                + (")." if n_rows or wide_melted else "."),
            )
        )
    elif (
        wide_n >= 4
        and not reshape.get("reshaped")
        and "device_id" not in fields
        and "inverter_id" not in fields
    ):
        findings.append(
            _finding(
                "fail",
                "wide_layout_unmelted",
                f"Detected {wide_n} wide device×metric columns (ICR/INV/SCB tags) that require "
                f"reshaping before hierarchy mapping — file was not melted to tidy long form.",
            )
        )

    obvious_unmapped = 0
    # After a successful melt, remaining columns are tidy — do not warn on wide leftovers.
    if not reshape.get("reshaped"):
        for c in evidence.get("unmapped_sample") or []:
            if parse_wide_device_column(str(c)) is not None:
                obvious_unmapped += 1
        if obvious_unmapped >= 3 and "ac_power_kw" not in fields and "dc_current_a" not in fields:
            findings.append(
                _finding(
                    "warn",
                    "obvious_wide_headers_unmapped",
                    f"{obvious_unmapped}+ headers look like device power/current but were not mapped "
                    f"(reshape may be required).",
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
        inv_n = evidence.get("architecture_inverters") or 0
        if not inv_n:
            findings.append(
                _finding(
                    "warn",
                    "ids_without_architecture_counts",
                    "Equipment ID mapped but architecture counts are still empty.",
                )
            )

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


def _normalize_upload_ai(
    data: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str]:
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
    return findings, hints, overall


def _call_gemini_upload(
    settings: Settings,
    evidence: dict[str, Any],
    rule_findings: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str, str | None, str | None]:
    parsed, model, err = call_gemini_json(
        settings,
        system=_UPLOAD_SYSTEM_PROMPT,
        user=json.dumps(
            {"evidence": evidence, "rule_findings": rule_findings},
            default=str,
        )[:12000],
    )
    if err or not parsed:
        return [], [], "pass", model, err or "Gemini returned empty JSON"
    findings, hints, overall = _normalize_upload_ai(parsed)
    return findings, hints, overall, model, None


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
        match = re.search(r"\{.*\}", content, re.DOTALL)
        data = json.loads(match.group(0) if match else content)
    except Exception:  # noqa: BLE001
        return [], [], "pass", model, "AI returned non-JSON"

    findings, hints, overall = _normalize_upload_ai(data if isinstance(data, dict) else {})
    return findings, hints, overall, model, None


def _call_upload_ai(
    settings: Settings,
    evidence: dict[str, Any],
    rule_findings: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str, str | None, str | None, str]:
    """Prefer Gemini; ZenMux optional fallback. Returns (…, provider)."""
    if gemini_configured(settings):
        findings, hints, overall, model, err = _call_gemini_upload(
            settings, evidence, rule_findings
        )
        if not err:
            return findings, hints, overall, model, None, "gemini"
        zkey = (settings.zenmux_api_key or "").strip()
        if zkey and not zkey.startswith("sk-mg-"):
            zf, zh, zo, zm, ze = _call_zenmux_upload(settings, evidence, rule_findings)
            if not ze:
                return zf, zh, zo, zm, None, "zenmux"
        return findings, hints, overall, model, err, "gemini"

    findings, hints, overall, model, err = _call_zenmux_upload(settings, evidence, rule_findings)
    return findings, hints, overall, model, err, "zenmux"


def _dedupe_hints(hints: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str]] = set()
    out: list[dict[str, Any]] = []
    for h in hints:
        key = (str(h.get("column_name")), str(h.get("canonical_field")))
        if key in seen:
            continue
        seen.add(key)
        out.append(h)
    return out


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
    extra_mapping_hints: list[dict[str, Any]] | None = None,
    parse_assist_meta: dict[str, Any] | None = None,
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
    all_rules = run_upload_deterministic_checks(evidence)
    rule_findings = [f for f in all_rules if f.get("severity") != "pass"]
    checked_at = datetime.now(timezone.utc).isoformat()
    configured = ai_check_configured(settings)
    assist_ok = bool(
        parse_assist_meta
        and parse_assist_meta.get("attempted")
        and not parse_assist_meta.get("error")
    )

    base: dict[str, Any] = {
        "phase": "upload",
        "configured": configured,
        "checked_at": checked_at,
        "mapping_hints": _dedupe_hints(list(extra_mapping_hints or []))[:12],
        "model": None,
        "error": None,
        "provider": None,
        "parse_assist": parse_assist_meta or None,
    }

    if not use_ai or not configured:
        overall = _overall_from_findings(rule_findings) if rule_findings else "pass"
        if assist_ok:
            return {
                **base,
                "status": overall,
                "source": "rules+gemini",
                "ai_layer": "ok",
                "rules_finding_count": len(rule_findings),
                "summary": {
                    "pass": "Upload parse check OK (rules + Gemini parse-assist).",
                    "warn": "Upload parse check found warnings (rules + Gemini parse-assist).",
                    "fail": "Upload parse check found failures (rules + Gemini parse-assist).",
                }[overall],
                "findings": rule_findings,
                "provider": "gemini",
                "model": (parse_assist_meta or {}).get("model"),
            }
        ai_layer = "not_configured" if not configured else "skipped"
        summary = {
            "pass": (
                "Upload parse check OK (rules). AI not configured."
                if not configured
                else "Upload parse check OK (rules)."
            ),
            "warn": (
                "Upload parse check found warnings. AI not configured."
                if not configured
                else "Upload parse check found warnings."
            ),
            "fail": (
                "Upload parse check found failures. AI not configured."
                if not configured
                else "Upload parse check found failures."
            ),
        }[overall]
        return {
            **base,
            "status": overall,
            "source": "rules",
            "ai_layer": ai_layer,
            "rules_finding_count": len(rule_findings),
            "summary": summary,
            "findings": rule_findings,
        }

    ai_findings, hints, ai_overall, model, error, provider = _call_upload_ai(
        settings, evidence, rule_findings
    )
    deduped = _dedupe_hints(list(extra_mapping_hints or []) + list(hints or []))

    if error:
        if assist_ok:
            overall = _overall_from_findings(rule_findings) if rule_findings else "pass"
            return {
                **base,
                "status": overall,
                "source": "rules+gemini",
                "ai_layer": "ok",
                "rules_finding_count": len(rule_findings),
                "summary": "Rules + Gemini parse-assist applied; integrity LLM failed.",
                "findings": rule_findings,
                "mapping_hints": deduped[:12],
                "model": (parse_assist_meta or {}).get("model") or model,
                "error": error,
                "provider": "gemini",
            }
        overall = _overall_from_findings(rule_findings) if rule_findings else "error"
        return {
            **base,
            "status": overall if rule_findings else "error",
            "source": "rules" if rule_findings else "none",
            "ai_layer": "failed",
            "rules_finding_count": len(rule_findings),
            "summary": (
                "AI upload check failed; showing rule findings."
                if rule_findings
                else "AI upload check failed."
            ),
            "findings": rule_findings,
            "mapping_hints": deduped[:12],
            "model": model,
            "error": error,
            "provider": provider,
        }

    merged = merge_findings(rule_findings, [f for f in ai_findings if f.get("severity") != "pass"])
    overall = _overall_from_findings(merged)
    if ai_overall == "fail" or (ai_overall == "warn" and overall == "pass"):
        overall = ai_overall
    source = f"rules+{provider}" if provider in {"gemini", "zenmux"} else "rules+ai"
    return {
        **base,
        "status": overall,
        "source": source,
        "ai_layer": "ok",
        "rules_finding_count": len(rule_findings),
        "summary": {
            "pass": f"Upload parse check passed (rules + {provider or 'AI'}).",
            "warn": "Upload parse check found warnings.",
            "fail": "Upload parse check found failures.",
        }[overall],
        "findings": merged,
        "mapping_hints": deduped[:12],
        "model": model,
        "provider": provider,
    }
