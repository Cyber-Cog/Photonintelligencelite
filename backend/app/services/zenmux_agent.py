"""ZenMux-backed PIC analyst agent (OpenAI-compatible chat completions)."""
from __future__ import annotations

import logging
from typing import Any

import httpx

from backend.app.config import Settings

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://zenmux.ai/api/v1"
DEFAULT_MODEL = "google/gemini-2.5-flash"


class ZenmuxAgentError(Exception):
    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


def zenmux_configured(settings: Settings) -> bool:
    return bool((settings.zenmux_api_key or "").strip())


def zenmux_status(settings: Settings) -> dict[str, Any]:
    return {
        "enabled": zenmux_configured(settings),
        "model": settings.zenmux_model or DEFAULT_MODEL,
        "base_url": settings.zenmux_base_url or DEFAULT_BASE_URL,
    }


async def chat_completion(
    *,
    settings: Settings,
    messages: list[dict[str, str]],
    model: str | None = None,
    max_tokens: int = 1024,
    temperature: float = 0.3,
) -> dict[str, Any]:
    """Call ZenMux OpenAI-compatible chat completions."""
    api_key = (settings.zenmux_api_key or "").strip()
    if not api_key:
        raise ZenmuxAgentError("ZenMux is not configured on this server.")

    base = (settings.zenmux_base_url or DEFAULT_BASE_URL).rstrip("/")
    url = f"{base}/chat/completions"
    payload = {
        "model": model or settings.zenmux_model or DEFAULT_MODEL,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
    except httpx.HTTPError as exc:
        logger.warning("zenmux request failed: %s", exc)
        raise ZenmuxAgentError("Could not reach ZenMux. Try again in a moment.") from exc

    if resp.status_code >= 400:
        detail = resp.text[:400]
        logger.warning("zenmux error %s: %s", resp.status_code, detail)
        if resp.status_code in (401, 403):
            hint = "Use a chat API key (sk-ai-v1-…) in ZENMUX_API_KEY."
            if api_key.startswith("sk-mg-v1"):
                hint = "This looks like a ZenMux management key (sk-mg-v1). Create a chat API key (sk-ai-v1) instead."
            raise ZenmuxAgentError(
                f"ZenMux rejected the API key. {hint}",
                status_code=resp.status_code,
            )
        raise ZenmuxAgentError(
            f"ZenMux returned an error ({resp.status_code}). Check model name and API key type.",
            status_code=resp.status_code,
        )

    data = resp.json()
    choices = data.get("choices") or []
    if not choices:
        raise ZenmuxAgentError("ZenMux returned an empty response.")
    message = choices[0].get("message") or {}
    content = (message.get("content") or "").strip()
    if not content:
        raise ZenmuxAgentError("ZenMux returned no assistant text.")
    return {
        "content": content,
        "model": data.get("model") or payload["model"],
        "usage": data.get("usage"),
    }
