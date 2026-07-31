"""AI-assisted fault-run integrity checker.

Gathers structured evidence from a completed analysis, applies deterministic
consistency rules, and optionally asks a ZenMux/OpenAI-compatible endpoint to
flag display vs run contradictions. Results are stored on the job for the
Results UI — not a chatbot.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any

import httpx

from backend.app.config import Settings

logger = logging.getLogger("pic_lite.fault_run_ai_check")

_SYSTEM_PROMPT = """You are a PIC Lite fault-run integrity checker.
Given structured evidence from a solar SCADA analysis job, find contradictions between
what modules claim to have done and what Results would show.

Focus only on integrity issues such as:
- module status "ok" but empty findings while severity/loss implies faults
- Results listing a module that did not run / missing from run summary
- status "unavailable" (Needs data) while findings tables are non-empty
- KPI fault_count clearly inconsistent with fault module finding rows
- status "ok" with missing_fields still listed

Do NOT invent plant faults. Do NOT recommend operational repairs.
Return ONLY valid JSON matching:
{
  "overall": "pass" | "warn" | "fail",
  "summary": "one short sentence",
  "findings": [
    {
      "severity": "pass" | "warn" | "fail",
      "code": "short_snake_case",
      "message": "short reason",
      "module_id": "algorithm_id or null"
    }
  ]
}
Prefer few high-signal findings. If nothing looks wrong, overall=pass and findings=[].
"""


def ai_check_configured(settings: Settings) -> bool:
    return bool((settings.zenmux_api_key or "").strip())


def build_integrity_evidence(
    *,
    results: list[dict[str, Any]],
    kpis: dict[str, Any],
    results_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Compact evidence payload for rules + LLM (no raw timeseries)."""
    modules: list[dict[str, Any]] = []
    for r in results:
        tables = r.get("tables") or []
        finding_rows = sum(len(t.get("rows") or []) for t in tables if isinstance(t, dict))
        modules.append(
            {
                "id": r.get("algorithm_id"),
                "title": r.get("title"),
                "status": r.get("status"),
                "module_kind": r.get("module_kind"),
                "severity": r.get("severity"),
                "finding_rows": finding_rows,
                "table_count": len(tables),
                "affected_equipment_count": len(r.get("affected_equipment") or []),
                "loss_kwh": r.get("loss_energy_kwh"),
                "missing_fields": list(r.get("missing_fields") or []),
                "missing_config": list(r.get("missing_config") or []),
                "error": r.get("error"),
            }
        )

    summary_modules = None
    if isinstance(results_summary, dict):
        summary_modules = results_summary.get("modules")

    fault_finding_rows = sum(
        int(m.get("finding_rows") or 0)
        for m in modules
        if m.get("module_kind") == "fault" and m.get("status") == "ok"
    )

    return {
        "kpis": {
            "fault_count": kpis.get("fault_count"),
            "plant_availability_pct": kpis.get("plant_availability_pct"),
            "performance_ratio_pct": kpis.get("performance_ratio_pct"),
            "estimated_energy_loss_kwh": kpis.get("estimated_energy_loss_kwh"),
            "revenue_loss_available": kpis.get("revenue_loss_available"),
        },
        "module_count": len(modules),
        "modules": modules,
        "results_summary_modules": summary_modules,
        "fault_finding_rows_ok": fault_finding_rows,
    }


def _finding(
    severity: str,
    code: str,
    message: str,
    module_id: str | None = None,
) -> dict[str, Any]:
    return {
        "severity": severity,
        "code": code,
        "message": message,
        "module_id": module_id,
    }


def run_deterministic_checks(evidence: dict[str, Any]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    modules: list[dict[str, Any]] = list(evidence.get("modules") or [])
    by_id = {m.get("id"): m for m in modules if m.get("id")}

    summary_mods = evidence.get("results_summary_modules")
    if isinstance(summary_mods, list):
        summary_ids = {m.get("id") for m in summary_mods if isinstance(m, dict) and m.get("id")}
        result_ids = set(by_id)
        for mid in sorted(summary_ids - result_ids):
            findings.append(
                _finding(
                    "fail",
                    "summary_module_missing_from_results",
                    f"Run summary lists '{mid}' but results payload has no such module.",
                    mid,
                )
            )
        for mid in sorted(result_ids - summary_ids):
            if mid == "kpis":
                continue
            findings.append(
                _finding(
                    "warn",
                    "results_module_missing_from_summary",
                    f"Results show '{mid}' but the stored run summary does not list it.",
                    mid,
                )
            )
        for sm in summary_mods:
            if not isinstance(sm, dict):
                continue
            mid = sm.get("id")
            if not mid or mid not in by_id:
                continue
            claimed = sm.get("status")
            actual = by_id[mid].get("status")
            if claimed and actual and str(claimed) != str(actual):
                findings.append(
                    _finding(
                        "fail",
                        "status_mismatch_summary_vs_results",
                        f"Summary status '{claimed}' ≠ results status '{actual}'.",
                        mid,
                    )
                )

    for m in modules:
        mid = m.get("id")
        status = m.get("status")
        rows = int(m.get("finding_rows") or 0)
        missing = m.get("missing_fields") or []
        if status == "unavailable" and rows > 0:
            findings.append(
                _finding(
                    "fail",
                    "needs_data_with_findings",
                    "Module is marked Needs data but has non-empty finding tables.",
                    mid,
                )
            )
        if status == "ok" and missing:
            findings.append(
                _finding(
                    "warn",
                    "ok_with_missing_fields",
                    f"Status is ok but missing_fields still listed: {', '.join(missing[:6])}.",
                    mid,
                )
            )
        if status == "ok" and m.get("module_kind") == "fault":
            sev = (m.get("severity") or "").lower()
            loss = m.get("loss_kwh")
            if rows == 0 and (sev in {"high", "critical", "medium"} or (isinstance(loss, (int, float)) and loss > 0)):
                findings.append(
                    _finding(
                        "warn",
                        "ok_fault_empty_findings",
                        "Fault module is ok with severity/loss but empty finding tables — Results may look empty.",
                        mid,
                    )
                )
        if status == "error":
            findings.append(
                _finding(
                    "fail",
                    "module_error",
                    f"Module ended in error: {(m.get('error') or 'unknown')[:160]}",
                    mid,
                )
            )

    kpi_faults = evidence.get("kpis", {}).get("fault_count")
    fault_rows = evidence.get("fault_finding_rows_ok")
    if isinstance(kpi_faults, int) and isinstance(fault_rows, int):
        if kpi_faults > 0 and fault_rows == 0:
            findings.append(
                _finding(
                    "warn",
                    "kpi_faults_without_rows",
                    f"KPI fault_count={kpi_faults} but ok fault modules have 0 finding rows.",
                )
            )

    return findings


def _overall_from_findings(findings: list[dict[str, Any]]) -> str:
    sevs = {f.get("severity") for f in findings}
    if "fail" in sevs:
        return "fail"
    if "warn" in sevs:
        return "warn"
    return "pass"


def _extract_json_object(text: str) -> dict[str, Any] | None:
    text = (text or "").strip()
    if not text:
        return None
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        return None


def _normalize_ai_findings(raw: dict[str, Any]) -> tuple[str, str, list[dict[str, Any]]]:
    findings_in = raw.get("findings") or []
    findings: list[dict[str, Any]] = []
    if isinstance(findings_in, list):
        for item in findings_in:
            if not isinstance(item, dict):
                continue
            sev = str(item.get("severity") or "warn").lower()
            if sev not in {"pass", "warn", "fail"}:
                sev = "warn"
            code = str(item.get("code") or "ai_note")[:64]
            message = str(item.get("message") or "").strip()[:400]
            if not message:
                continue
            mid = item.get("module_id")
            findings.append(
                _finding(sev, code, message, str(mid) if mid else None)
            )
    overall = str(raw.get("overall") or _overall_from_findings(findings)).lower()
    if overall not in {"pass", "warn", "fail"}:
        overall = _overall_from_findings(findings)
    summary = str(raw.get("summary") or "").strip()[:300]
    if not summary:
        summary = {
            "pass": "AI review found no integrity issues.",
            "warn": "AI review found warnings.",
            "fail": "AI review found integrity failures.",
        }[overall]
    return overall, summary, findings


def call_zenmux_integrity(
    settings: Settings,
    evidence: dict[str, Any],
    rule_findings: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], str, str | None, str | None]:
    """Returns (ai_findings, overall_hint, model, error_message)."""
    key = (settings.zenmux_api_key or "").strip()
    if not key:
        return [], "pass", None, None

    base = (settings.zenmux_base_url or "https://zenmux.ai/api/v1").rstrip("/")
    model = (settings.zenmux_model or "google/gemini-2.5-flash").strip()
    url = f"{base}/chat/completions"
    user_payload = {
        "evidence": evidence,
        "deterministic_findings": rule_findings,
    }
    body = {
        "model": model,
        "temperature": 0.1,
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    "Check this PIC Lite fault run for integrity issues.\n\n"
                    + json.dumps(user_payload, default=str)[:48_000]
                ),
            },
        ],
    }

    try:
        with httpx.Client(timeout=settings.zenmux_timeout_sec) as client:
            resp = client.post(
                url,
                headers={
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                },
                json=body,
            )
    except httpx.HTTPError as exc:
        logger.warning("ZenMux integrity request failed: %s", exc)
        return [], "warn", model, f"AI check request failed: {exc}"

    if resp.status_code >= 400:
        detail = (resp.text or "")[:400]
        hint = ""
        if key.startswith("sk-mg-") or resp.status_code in {401, 403}:
            if key.startswith("sk-mg-"):
                hint = (
                    " This looks like a management key (sk-mg-v1-…). "
                    "Chat completions usually need a chat key (sk-ai-v1-…)."
                )
            elif resp.status_code in {401, 403}:
                hint = " If this persists, confirm you are using a chat key (sk-ai-v1-…), not a management key."
        msg = f"AI provider returned HTTP {resp.status_code}.{hint} {detail}".strip()
        logger.warning("ZenMux integrity HTTP %s: %s", resp.status_code, detail[:200])
        return [], "error", model, msg

    try:
        payload = resp.json()
        content = payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
        return [], "error", model, f"AI response could not be parsed: {exc}"

    parsed = _extract_json_object(content if isinstance(content, str) else str(content))
    if not parsed:
        return [], "error", model, "AI response did not contain valid JSON."

    overall, _summary, findings = _normalize_ai_findings(parsed)
    return findings, overall, model, None


def merge_findings(*groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[Any, ...]] = set()
    out: list[dict[str, Any]] = []
    for group in groups:
        for f in group:
            key = (f.get("code"), f.get("module_id"), f.get("message"))
            if key in seen:
                continue
            seen.add(key)
            out.append(f)
    return out


def skipped_result(*, reason: str = "AI check not configured") -> dict[str, Any]:
    """Visible skipped payload — UI must still show rules + AI status, not hide the panel."""
    return {
        "status": "pass",
        "configured": False,
        "source": "rules",
        "ai_layer": "not_configured",
        "rules_finding_count": 0,
        "summary": f"Rules passed. {reason}.",
        "findings": [],
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "model": None,
        "error": None,
        "phase": "results",
    }


def _short_ai_failure_reason(error: str | None) -> str:
    err = (error or "failed").strip()
    low = err.lower()
    if "sk-mg" in low or "management key" in low:
        return "AI key rejected — use sk-ai-v1"
    if "http 403" in low or "http 401" in low:
        return "AI key rejected"
    if "not configured" in low:
        return "AI not configured"
    # Keep short for console / progress_message (500 char column).
    return err[:72].rstrip(" .") or "failed"


def format_integrity_progress(check: dict[str, Any]) -> str:
    """One-line LIVE console / progress_message for Analyze."""
    rules_n = int(check.get("rules_finding_count") or 0)
    if "rules_finding_count" not in check:
        rules_n = sum(
            1 for f in (check.get("findings") or []) if (f.get("severity") or "") != "pass"
        )
    ai_layer = str(check.get("ai_layer") or "unknown")
    if ai_layer == "ok":
        zen = "ZenMux: ok"
    elif ai_layer == "not_configured":
        zen = "ZenMux: skipped (AI not configured)"
    elif ai_layer == "skipped":
        zen = "ZenMux: skipped"
    elif ai_layer == "failed":
        zen = f"ZenMux: failed ({_short_ai_failure_reason(check.get('error'))})"
    else:
        zen = f"ZenMux: {ai_layer}"
    return f"AI integrity · rules: {rules_n} finding(s) · {zen}"


def _pack_result(
    *,
    status: str,
    configured: bool,
    source: str,
    ai_layer: str,
    rules_finding_count: int,
    summary: str,
    findings: list[dict[str, Any]],
    checked_at: str,
    model: str | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    return {
        "status": status,
        "configured": configured,
        "source": source,
        "ai_layer": ai_layer,
        "rules_finding_count": rules_finding_count,
        "summary": summary,
        "findings": findings,
        "checked_at": checked_at,
        "model": model,
        "error": error,
        "phase": "results",
    }


def run_fault_run_integrity_check(
    settings: Settings,
    *,
    results: list[dict[str, Any]],
    kpis: dict[str, Any],
    results_summary: dict[str, Any] | None = None,
    use_ai: bool = True,
) -> dict[str, Any]:
    """Full integrity check: rules always; AI when configured and use_ai."""
    evidence = build_integrity_evidence(
        results=results,
        kpis=kpis,
        results_summary=results_summary,
    )
    rule_findings = run_deterministic_checks(evidence)
    rules_n = len(rule_findings)
    checked_at = datetime.now(timezone.utc).isoformat()

    configured = ai_check_configured(settings)
    if not use_ai or not configured:
        overall = _overall_from_findings(rule_findings) if rule_findings else "pass"
        if not configured:
            ai_layer = "not_configured"
            summary = {
                "pass": "Rules passed. AI not configured.",
                "warn": "Rules found warnings. AI not configured.",
                "fail": "Rules found failures. AI not configured.",
            }[overall]
        else:
            ai_layer = "skipped"
            summary = {
                "pass": "Run integrity OK (rules only).",
                "warn": "Run integrity rules found warnings.",
                "fail": "Run integrity rules found failures.",
            }[overall]
        return _pack_result(
            status=overall,
            configured=configured,
            source="rules",
            ai_layer=ai_layer,
            rules_finding_count=rules_n,
            summary=summary,
            findings=rule_findings,
            checked_at=checked_at,
        )

    ai_findings, ai_overall, model, error = call_zenmux_integrity(settings, evidence, rule_findings)
    if error:
        # Keep rule findings even when AI fails.
        overall = _overall_from_findings(rule_findings) if rule_findings else "error"
        return _pack_result(
            status=overall if rule_findings else "error",
            configured=True,
            source="rules" if rule_findings else "none",
            ai_layer="failed",
            rules_finding_count=rules_n,
            summary=(
                "AI check failed; showing rule-based findings."
                if rule_findings
                else f"AI check failed — {_short_ai_failure_reason(error)}."
            ),
            findings=rule_findings,
            checked_at=checked_at,
            model=model,
            error=error,
        )

    merged = merge_findings(rule_findings, [f for f in ai_findings if f.get("severity") != "pass"])
    overall = _overall_from_findings(merged)
    # Prefer AI overall if stricter
    if ai_overall == "fail" or (ai_overall == "warn" and overall == "pass"):
        overall = ai_overall

    return _pack_result(
        status=overall,
        configured=True,
        source="rules+ai",
        ai_layer="ok",
        rules_finding_count=rules_n,
        summary={
            "pass": "Run integrity check passed (rules + AI).",
            "warn": "Run integrity check found warnings.",
            "fail": "Run integrity check found failures.",
        }[overall],
        findings=merged,
        checked_at=checked_at,
        model=model,
    )
