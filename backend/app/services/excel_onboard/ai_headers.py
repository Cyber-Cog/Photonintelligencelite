"""Phase 5 — AI header-only assist (strict JSON, pydantic, retry ≤2). Never bulk data."""
from __future__ import annotations

import json
import logging
import time
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from backend.app.config import Settings
from backend.app.services.excel_onboard.metadata import HeaderMetadataPayload
from backend.app.services.gemini_client import call_gemini_json, gemini_configured, gemini_model_name

logger = logging.getLogger(__name__)


class ColumnMappingHint(BaseModel):
    column_name: str
    canonical_field: str | None = None
    hierarchy_level: str | None = None
    equipment_class: str | None = None
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)


class HeaderAiResponse(BaseModel):
    column_hints: list[ColumnMappingHint] = Field(default_factory=list)
    equipment_summary: list[str] = Field(default_factory=list)
    unknown_tags: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)


def run_header_ai_assist(
    settings: Settings,
    payload: HeaderMetadataPayload,
    *,
    max_retries: int = 2,
) -> dict[str, Any]:
    """Call Gemini with header metadata only. Returns meta dict; never raises."""
    meta: dict[str, Any] = {
        "attempted": False,
        "ok": False,
        "provider": "gemini",
        "model": None,
        "error": None,
        "elapsed_ms": None,
        "prompt_chars": 0,
        "response": None,
        "retries": 0,
    }
    if not gemini_configured(settings):
        meta["error"] = "not_configured"
        return meta

    prompt_obj = payload.prompt_json()
    prompt = (
        "You classify SCADA Excel column headers for solar plant analytics.\n"
        "Return STRICT JSON matching schema:\n"
        "{"
        '"column_hints":[{"column_name":"str","canonical_field":'
        '"timestamp|device_id|icr_id|inverter_id|scb_id|string_id|ac_power_kw|dc_power_kw|'
        'dc_current_a|dc_voltage_v|poa_w_m2|ghi_w_m2|module_temp_c|ambient_temp_c|energy_kwh|null",'
        '"hierarchy_level":"plant|icr|inverter|scb|string|null","equipment_class":"str|null","confidence":0.0}],'
        '"equipment_summary":["str"],"unknown_tags":["str"],"notes":["str"],"confidence":0.0'
        "}\n"
        "Rules: Do not invent measurements. Only use provided header parts. "
        "Prefer ac_power_kw for AC_ACTIVE_POWER / AC power; dc_power_kw for DC_POWER.\n"
        f"HEADER_METADATA:\n{json.dumps(prompt_obj, ensure_ascii=False)}"
    )
    meta["attempted"] = True
    meta["prompt_chars"] = len(prompt)
    logger.info(
        "excel_onboard.ai_header prompt_chars=%s columns=%s",
        meta["prompt_chars"],
        len(payload.columns),
    )

    last_err: str | None = None
    t0 = time.perf_counter()
    for attempt in range(max_retries + 1):
        meta["retries"] = attempt
        try:
            raw, model, err = call_gemini_json(
                settings,
                system="You return only valid JSON for SCADA header classification.",
                user=prompt,
            )
            meta["model"] = model or gemini_model_name(settings)
            if err:
                raise ValueError(err)
            if raw is None:
                raise ValueError("empty_json")
            parsed = HeaderAiResponse.model_validate(raw)
            meta["ok"] = True
            meta["response"] = parsed.model_dump()
            meta["elapsed_ms"] = int((time.perf_counter() - t0) * 1000)
            logger.info(
                "excel_onboard.ai_header ok elapsed_ms=%s confidence=%s hints=%s",
                meta["elapsed_ms"],
                parsed.confidence,
                len(parsed.column_hints),
            )
            return meta
        except (ValidationError, json.JSONDecodeError, TypeError, ValueError) as exc:
            last_err = f"invalid_json:{exc}"
            logger.warning("excel_onboard.ai_header retry=%s err=%s", attempt, exc)
        except Exception as exc:  # noqa: BLE001
            last_err = str(exc)
            logger.warning("excel_onboard.ai_header failed attempt=%s err=%s", attempt, exc)
            break

    meta["error"] = last_err or "failed"
    meta["elapsed_ms"] = int((time.perf_counter() - t0) * 1000)
    return meta
