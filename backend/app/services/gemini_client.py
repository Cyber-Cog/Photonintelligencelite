"""Google AI Studio / Generative Language API client (server-side only).

Uses REST ``generativelanguage.googleapis.com`` with ``GEMINI_API_KEY``.
Never log or return the raw key.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

import httpx

from backend.app.config import Settings

logger = logging.getLogger("pic_lite.gemini_client")

DEFAULT_MODEL = "gemini-2.0-flash"
_BASE = "https://generativelanguage.googleapis.com/v1beta"


def gemini_configured(settings: Settings) -> bool:
    return bool((settings.gemini_api_key or "").strip())


def gemini_model_name(settings: Settings) -> str:
    return (settings.gemini_model or DEFAULT_MODEL).strip() or DEFAULT_MODEL


def _redact_key(key: str) -> str:
    k = (key or "").strip()
    if len(k) <= 8:
        return "***"
    return f"{k[:6]}…{k[-4:]}"


def extract_json_object(text: str) -> dict[str, Any] | None:
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


def call_gemini_generate(
    settings: Settings,
    *,
    system: str,
    user: str,
    json_mode: bool = True,
    temperature: float = 0.1,
) -> tuple[str | None, str | None, str | None]:
    """Returns (text_content, model, error_message)."""
    key = (settings.gemini_api_key or "").strip()
    if not key:
        return None, None, "GEMINI_API_KEY not configured"

    model = gemini_model_name(settings)
    url = f"{_BASE}/models/{model}:generateContent"
    body: dict[str, Any] = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": user}]}],
        "generationConfig": {
            "temperature": temperature,
        },
    }
    if json_mode:
        body["generationConfig"]["responseMimeType"] = "application/json"

    timeout = float(settings.gemini_timeout_sec or 45.0)
    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(
                url,
                params={"key": key},
                headers={"Content-Type": "application/json"},
                json=body,
            )
    except httpx.HTTPError as exc:
        logger.warning("Gemini request failed (%s): %s", _redact_key(key), exc)
        return None, model, f"Gemini request failed: {exc}"

    if resp.status_code >= 400:
        detail = (resp.text or "")[:300]
        logger.warning(
            "Gemini HTTP %s (%s): %s",
            resp.status_code,
            _redact_key(key),
            detail[:160],
        )
        return None, model, f"Gemini HTTP {resp.status_code}: {detail}"

    try:
        payload = resp.json()
        parts = (
            ((payload.get("candidates") or [{}])[0].get("content") or {}).get("parts") or []
        )
        text = "".join(str(p.get("text") or "") for p in parts if isinstance(p, dict))
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
        return None, model, f"Gemini response could not be parsed: {exc}"

    if not text.strip():
        return None, model, "Gemini returned empty content"
    return text, model, None


def call_gemini_json(
    settings: Settings,
    *,
    system: str,
    user: str,
    temperature: float = 0.1,
) -> tuple[dict[str, Any] | None, str | None, str | None]:
    """Returns (parsed_json, model, error_message)."""
    text, model, err = call_gemini_generate(
        settings,
        system=system,
        user=user,
        json_mode=True,
        temperature=temperature,
    )
    if err:
        return None, model, err
    parsed = extract_json_object(text or "")
    if not parsed:
        return None, model, "Gemini response did not contain valid JSON"
    return parsed, model, None
