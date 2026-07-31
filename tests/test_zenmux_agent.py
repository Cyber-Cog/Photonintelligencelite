"""Tests for ZenMux agent service."""
from __future__ import annotations

import pytest

from backend.app.config import Settings
from backend.app.services.zenmux_agent import ZenmuxAgentError, zenmux_configured, zenmux_status


def test_zenmux_not_configured_by_default():
    settings = Settings(_env_file=None, zenmux_api_key=None)
    assert zenmux_configured(settings) is False
    assert zenmux_status(settings)["enabled"] is False


@pytest.mark.asyncio
async def test_chat_requires_api_key():
    from backend.app.services.zenmux_agent import chat_completion

    settings = Settings(_env_file=None, zenmux_api_key=None)
    with pytest.raises(ZenmuxAgentError, match="not configured"):
        await chat_completion(settings=settings, messages=[{"role": "user", "content": "hi"}])
