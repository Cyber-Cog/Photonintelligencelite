"""AI parse-assist: Gemini proposes canonical field mappings after heuristics.

Runs alongside rule-based column detection / wide-csv reshape — never replaces them.
Only headers (+ short unmapped samples) are sent; no raw SCADA PII dumps.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Iterable

from analytics.common.aliasing import HIGH_CONFIDENCE, MEDIUM_CONFIDENCE, confidence_band
from backend.app.config import Settings
from backend.app.schemas import ColumnMappingSuggestion
from backend.app.services.gemini_client import call_gemini_json, gemini_configured

logger = logging.getLogger("pic_lite.ai_parse_assist")

# Fields Gemini may propose (must match aliases / mapping UI).
ALLOWED_CANONICAL_FIELDS = frozenset(
    {
        "timestamp",
        "ac_power_kw",
        "dc_power_kw",
        "dc_current_a",
        "dc_voltage_v",
        "poa_w_m2",
        "ghi_w_m2",
        "module_temp_c",
        "ambient_temp_c",
        "energy_kwh",
        "device_id",
        "inverter_id",
        "scb_id",
        "string_id",
        "icr_id",
        "ignore",
    }
)

_PARSE_SYSTEM = """You are a PIC Lite solar SCADA column mapper.
Given CSV/Excel header names and which are already mapped by heuristics, propose
canonical field mappings for remaining ambiguous or unmapped headers.

Allowed canonical_field values ONLY:
timestamp, ac_power_kw, dc_power_kw, dc_current_a, dc_voltage_v, poa_w_m2, ghi_w_m2,
module_temp_c, ambient_temp_c, energy_kwh, device_id, inverter_id, scb_id, string_id,
icr_id, ignore

Return ONLY valid JSON:
{
  "mappings": [
    {"column_name": "exact header", "canonical_field": "ac_power_kw", "confidence": 0.0, "reason": "short"}
  ]
}
Only propose mappings for columns listed as unmapped or low-confidence.
confidence 0..1. Prefer fewer high-confidence proposals. Do not invent headers.
"""

# Apply into suggestions when AI confidence clears this bar.
APPLY_CONFIDENCE = 0.85


def needs_parse_assist(suggestions: Iterable[Any], columns: list[str] | None = None) -> bool:
    """True when heuristics look thin or many headers are ambiguous/manual."""
    sug = list(suggestions)
    if not sug and columns:
        return len(columns) >= 2

    mapped = [
        s
        for s in sug
        if (getattr(s, "canonical_field", None) or (s.get("canonical_field") if isinstance(s, dict) else None))
        not in (None, "", "ignore")
    ]
    fields = {
        (getattr(s, "canonical_field", None) or (s.get("canonical_field") if isinstance(s, dict) else None))
        for s in mapped
    }
    manual_n = sum(
        1
        for s in sug
        if (getattr(s, "band", None) or (s.get("band") if isinstance(s, dict) else None)) == "manual"
        or not (
            getattr(s, "canonical_field", None) or (s.get("canonical_field") if isinstance(s, dict) else None)
        )
    )
    metric_fields = fields & {
        "ac_power_kw",
        "dc_power_kw",
        "dc_current_a",
        "dc_voltage_v",
        "poa_w_m2",
        "ghi_w_m2",
        "device_id",
        "inverter_id",
        "scb_id",
        "string_id",
        "icr_id",
    }
    # Thin: only timestamp (or nothing useful) mapped
    if "timestamp" in fields and not metric_fields and len(mapped) <= 2:
        return True
    if len(mapped) <= 1 and len(sug) >= 3:
        return True
    # Ambiguous: many manual / unmapped
    if manual_n >= 3:
        return True
    if len(sug) >= 8 and manual_n / max(len(sug), 1) >= 0.4:
        return True
    return False


def _col_field_conf(s: Any) -> tuple[str, str | None, float, str]:
    if isinstance(s, dict):
        return (
            str(s.get("column_name") or ""),
            s.get("canonical_field"),
            float(s.get("confidence") or 0.0),
            str(s.get("band") or "manual"),
        )
    return (
        str(getattr(s, "column_name", "") or ""),
        getattr(s, "canonical_field", None),
        float(getattr(s, "confidence", 0.0) or 0.0),
        str(getattr(s, "band", "manual") or "manual"),
    )


def build_parse_assist_payload(
    suggestions: Iterable[Any],
    *,
    columns: list[str] | None = None,
    original_filename: str | None = None,
) -> dict[str, Any]:
    sug = list(suggestions)
    mapped: list[dict[str, Any]] = []
    unmapped: list[str] = []
    low_conf: list[dict[str, Any]] = []
    for s in sug:
        col, field, conf, band = _col_field_conf(s)
        if not col:
            continue
        if field and field != "ignore" and conf >= MEDIUM_CONFIDENCE:
            mapped.append({"column": col, "field": field, "confidence": conf})
        elif field and field != "ignore" and conf > 0:
            low_conf.append({"column": col, "field": field, "confidence": conf, "band": band})
            unmapped.append(col)
        else:
            unmapped.append(col)

    headers = columns or [ _col_field_conf(s)[0] for s in sug ]
    return {
        "original_filename": original_filename,
        "headers": headers[:80],
        "mapped": mapped[:40],
        "low_confidence": low_conf[:20],
        "unmapped_headers": unmapped[:40],
        "allowed_fields": sorted(ALLOWED_CANONICAL_FIELDS - {"ignore"}) + ["ignore"],
    }


def propose_mappings_via_gemini(
    settings: Settings,
    *,
    suggestions: Iterable[Any],
    columns: list[str] | None = None,
    original_filename: str | None = None,
) -> tuple[list[dict[str, Any]], str | None, str | None]:
    """Returns (mapping_proposals, model, error)."""
    if not gemini_configured(settings):
        return [], None, None

    payload = build_parse_assist_payload(
        suggestions, columns=columns, original_filename=original_filename
    )
    if not payload["unmapped_headers"] and not payload["low_confidence"]:
        return [], None, None

    parsed, model, err = call_gemini_json(
        settings,
        system=_PARSE_SYSTEM,
        user=(
            "Propose canonical mappings for these PIC Lite upload headers.\n\n"
            + json.dumps(payload, default=str)[:10_000]
        ),
    )
    if err or not parsed:
        return [], model, err

    header_set = set(payload["headers"])
    already = {m["column"] for m in payload["mapped"]}
    out: list[dict[str, Any]] = []
    for item in parsed.get("mappings") or []:
        if not isinstance(item, dict):
            continue
        col = str(item.get("column_name") or "").strip()
        field = str(item.get("canonical_field") or "").strip()
        if not col or col not in header_set:
            continue
        if col in already:
            continue
        if field not in ALLOWED_CANONICAL_FIELDS:
            continue
        try:
            conf = float(item.get("confidence") or 0.0)
        except (TypeError, ValueError):
            conf = 0.0
        conf = max(0.0, min(conf, 0.99))
        out.append(
            {
                "column_name": col[:200],
                "canonical_field": field,
                "confidence": conf,
                "reason": str(item.get("reason") or "")[:120],
            }
        )
    return out[:24], model, None


def merge_ai_mappings_into_suggestions(
    suggestions: list[ColumnMappingSuggestion],
    proposals: list[dict[str, Any]],
    *,
    min_confidence: float = APPLY_CONFIDENCE,
) -> tuple[list[ColumnMappingSuggestion], int]:
    """Overlay high-confidence AI proposals onto heuristic suggestions. Returns (list, applied_n)."""
    by_col = {p["column_name"]: p for p in proposals if p.get("column_name")}
    applied = 0
    out: list[ColumnMappingSuggestion] = []
    for s in suggestions:
        p = by_col.get(s.column_name)
        if not p:
            out.append(s)
            continue
        conf = float(p.get("confidence") or 0.0)
        field = p.get("canonical_field")
        # Only fill gaps / weak heuristic bands — never overwrite exact alias (conf 1.0 auto).
        if s.confidence >= HIGH_CONFIDENCE and s.canonical_field and s.band == "auto":
            out.append(s)
            continue
        if conf < min_confidence or not field:
            out.append(s)
            continue
        if s.canonical_field and s.confidence >= conf:
            out.append(s)
            continue
        band = confidence_band(conf)
        # AI assist stays reviewable unless very high
        if band == "auto" and conf < 0.95:
            band = "confirm"
        out.append(
            ColumnMappingSuggestion(
                column_name=s.column_name,
                canonical_field=field if field != "ignore" else None,
                confidence=conf,
                band="manual" if field == "ignore" else band,
                field_type=s.field_type,
                channel_index=s.channel_index,
                group_label=s.group_label,
            )
        )
        applied += 1
    return out, applied


def run_parse_assist(
    settings: Settings,
    *,
    suggestions: list[ColumnMappingSuggestion],
    columns: list[str] | None = None,
    original_filename: str | None = None,
    force: bool = False,
) -> tuple[list[ColumnMappingSuggestion], dict[str, Any]]:
    """After heuristics: optionally call Gemini and merge. Returns (suggestions, meta)."""
    meta: dict[str, Any] = {
        "attempted": False,
        "applied": 0,
        "proposals": [],
        "model": None,
        "error": None,
        "provider": None,
    }
    if not gemini_configured(settings):
        return suggestions, meta
    if not force and not needs_parse_assist(suggestions, columns):
        return suggestions, meta

    meta["attempted"] = True
    proposals, model, err = propose_mappings_via_gemini(
        settings,
        suggestions=suggestions,
        columns=columns,
        original_filename=original_filename,
    )
    meta["model"] = model
    meta["provider"] = "gemini"
    if err:
        meta["error"] = err
        logger.warning("parse-assist Gemini failed: %s", err[:200])
        return suggestions, meta

    merged, applied = merge_ai_mappings_into_suggestions(suggestions, proposals)
    meta["applied"] = applied
    meta["proposals"] = proposals
    return merged, meta
