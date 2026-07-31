"""PIC Analyst agent — ZenMux-backed explanations for upload / validation context."""
from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.app.auth.deps import enforce_csrf, require_verified_user
from backend.app.auth.job_access import load_job_authorized
from backend.app.config import Settings, get_settings
from backend.app.database import get_db
from backend.app.models import Job, User
from backend.app.schemas import AgentChatRequest, AgentChatResponse, AgentStatusResponse
from backend.app.services.upload_intelligence import build_upload_intelligence
from backend.app.services.upload_inventory import inventory_from_job
from backend.app.services.mapping_service import read_header, suggest_mapping
from backend.app.services.storage import job_paths
from backend.app.services.zenmux_agent import ZenmuxAgentError, chat_completion, zenmux_status

router = APIRouter(prefix="/api/agent", tags=["agent"])

_SYSTEM_PROMPT = """You are PIC Analyst, a solar plant SCADA assistant inside Photon Intelligence Center Lite.

Your job:
- Explain which signals were detected or missing at plant/WMS, inverter, and SCB/string levels.
- Clarify plant architecture (inverters, SCBs, strings) when data is provided.
- Explain why specific fault/diagnostic modules may not run and what the plant owner should fix in Setup.
- Stay practical for plant owners and O&M engineers — no jargon without explanation.

Rules:
- Use only the job context JSON provided. If something is not in context, say you don't have that data yet.
- Do not invent column names, counts, or fault results.
- Keep answers concise (3–6 short paragraphs or bullet lists).
- Never ask the user to paste SCADA rows; they use the PIC Lite workflow (Upload → Setup → Validate → Analyze).
"""


def _job_upload_context(db: Session, job: Job, settings: Settings) -> dict[str, Any]:
    paths = job_paths(settings.job_root_path, job.id)
    csv_path = paths.raw_dir / "input.csv"
    columns = read_header(csv_path) if csv_path.exists() else []
    suggestions = suggest_mapping(columns) if columns else []
    plant = (job.plant_config_json or {}).get("plant") if job.plant_config_json else None
    file_inv, _ = inventory_from_job(paths, job.original_filename)
    intelligence = build_upload_intelligence(
        suggestions=suggestions,
        plant_config=plant,
        csv_path=csv_path if csv_path.exists() else None,
        file_inventory=file_inv,
    )
    return {
        "job_id": job.id,
        "state": job.state,
        "original_filename": job.original_filename,
        "hierarchy_overview": intelligence.get("hierarchy_overview"),
        "architecture_summary": intelligence.get("architecture_summary"),
        "module_impact_preview": intelligence.get("module_impact_preview"),
    }


def _job_validation_context(job: Job) -> dict[str, Any] | None:
    summary = job.validation_summary_json
    if not summary:
        return None
    return {
        "blockers": summary.get("blockers"),
        "warnings": summary.get("warnings"),
        "module_readiness": summary.get("module_readiness"),
        "interval_notes": summary.get("interval_notes"),
    }


@router.get("/status", response_model=AgentStatusResponse)
def agent_status(settings: Settings = Depends(get_settings)) -> AgentStatusResponse:
    st = zenmux_status(settings)
    return AgentStatusResponse(**st)


@router.post("/chat", response_model=AgentChatResponse)
async def agent_chat(
    body: AgentChatRequest,
    user: User = Depends(require_verified_user),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _: None = Depends(enforce_csrf),
) -> AgentChatResponse:
    if not zenmux_status(settings)["enabled"]:
        raise HTTPException(503, "PIC Analyst is not configured on this server.")

    context: dict[str, Any] = {"page": body.context or "general"}
    if body.job_id:
        job = load_job_authorized(db, body.job_id, user)
        context["upload"] = _job_upload_context(db, job, settings)
        validation = _job_validation_context(job)
        if validation:
            context["validation"] = validation

    messages: list[dict[str, str]] = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"Job context (JSON):\n{json.dumps(context, indent=2, default=str)}\n\n"
                f"User question:\n{body.message.strip()}"
            ),
        },
    ]
    if body.history:
        # Insert prior turns before the latest user message
        prior = [{"role": h.role, "content": h.content} for h in body.history if h.role in ("user", "assistant")]
        messages = [messages[0], *prior, messages[1]]

    try:
        result = await chat_completion(settings=settings, messages=messages)
    except ZenmuxAgentError as exc:
        code = exc.status_code or 502
        raise HTTPException(code if code in (401, 403, 502, 503) else 502, str(exc)) from exc

    return AgentChatResponse(
        content=result["content"],
        model=result.get("model"),
    )
