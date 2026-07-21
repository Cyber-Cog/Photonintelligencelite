"""Loads and validates the YAML config files under analytics/config/.

Loaded once per process. Environment variables only ever override deployment limits
(upload size, job timeout) — never algorithm thresholds. See docs/architecture_decisions.md §6.
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"


class DeploymentLimits(BaseModel):
    max_compressed_upload_mb: int
    max_decompressed_upload_mb: int
    job_timeout_sec: int
    job_timeout_safety_cap_sec: int
    max_rows: int
    max_columns: int
    max_decompression_ratio: int
    report_ttl_minutes: int
    poll_interval_sec: float
    analysis_window_min_days: int
    analysis_window_max_days: int


@lru_cache(maxsize=1)
def load_aliases() -> dict[str, list[str]]:
    with open(CONFIG_DIR / "aliases.yaml", "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


@lru_cache(maxsize=1)
def load_thresholds() -> dict[str, dict[str, float]]:
    with open(CONFIG_DIR / "thresholds.yaml", "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    # Strip non-numeric annotation keys (e.g. version_note strings) from numeric threshold groups
    # so downstream code can assume dict[str, float] without special-casing.
    cleaned: dict[str, dict[str, float]] = {}
    for algo_id, group in data.items():
        cleaned[algo_id] = {k: v for k, v in group.items() if isinstance(v, (int, float))}
    return cleaned


@lru_cache(maxsize=1)
def load_defaults() -> dict:
    with open(CONFIG_DIR / "defaults.yaml", "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def deployment_limits(*, free_tier: bool | None = None) -> DeploymentLimits:
    """Resolve deployment limits.

    ``free_tier`` defaults to the ``PIC_LITE_FREE_TIER`` env var (truthy) when not passed
    explicitly. Individual limits can still be overridden by dedicated env vars.
    """
    defaults = load_defaults()
    if free_tier is None:
        free_tier = os.getenv("PIC_LITE_FREE_TIER", "false").lower() in {"1", "true", "yes"}
    base = defaults["free_tier_deployment_limits"] if free_tier else defaults["deployment_limits"]
    limits = dict(base)

    env_overrides = {
        "max_compressed_upload_mb": "MAX_COMPRESSED_UPLOAD_MB",
        "max_decompressed_upload_mb": "MAX_DECOMPRESSED_UPLOAD_MB",
        "job_timeout_sec": "JOB_TIMEOUT_SEC",
        "report_ttl_minutes": "REPORT_TTL_MINUTES",
    }
    for key, env_name in env_overrides.items():
        val = os.getenv(env_name)
        if val is not None:
            limits[key] = type(limits[key])(val)

    return DeploymentLimits(**limits)


def resolve_thresholds(plant_type: str, bifacial: bool, overrides: dict | None = None) -> dict[str, dict[str, float]]:
    """Merge base thresholds with plant-type overrides and per-job overrides.

    Returns a deep copy — safe to mutate by the caller before use.
    """
    base = {k: dict(v) for k, v in load_thresholds().items()}
    defaults = load_defaults()
    facial_key = "bifacial" if bifacial else "monofacial"
    plant_overrides = (defaults.get("plant_type_overrides", {}).get(plant_type, {}) or {}).get(facial_key, {}) or {}

    for dotted_key, value in plant_overrides.items():
        algo_id, _, field_name = dotted_key.partition(".")
        base.setdefault(algo_id, {})[field_name] = value

    if overrides:
        for algo_id, group in overrides.items():
            base.setdefault(algo_id, {}).update(group)

    return base
