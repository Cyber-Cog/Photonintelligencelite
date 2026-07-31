"""Actionable vs non-actionable fault module categorization.

Defaults use domain judgment: field-fixable faults (disconnects, module damage,
efficiency) are actionable; clipping/limit losses are informational / non-actionable.
Superadmins can override via AppSetting; Results UI merges overrides over defaults.
"""
from __future__ import annotations

from typing import Any, Literal

from sqlalchemy.orm import Session

from analytics.common.module_kinds import FAULT_ALGORITHM_IDS

FaultCategory = Literal["actionable", "non_actionable"]

SETTING_KEY = "fault_categories"

# Human labels for admin / Results (keep in sync with algorithm titles).
FAULT_MODULE_META: dict[str, dict[str, str]] = {
    "disconnected_strings": {
        "label": "Disconnected Strings",
        "hint": "String / SCB open-circuit — field repair",
    },
    "module_damage": {
        "label": "Module Damage & Bypass Diode",
        "hint": "Voltage deviation / damaged modules — field repair",
    },
    "inverter_efficiency": {
        "label": "Inverter Efficiency Loss",
        "hint": "Low conversion efficiency — maintenance / OEM",
    },
    "clipping_power": {
        "label": "Inverter Clipping by Power",
        "hint": "Design / irradiance limit — often non-actionable",
    },
    "clipping_current": {
        "label": "Inverter Clipping by Current",
        "hint": "DC current limit — often non-actionable",
    },
}

# Sensible product defaults when no admin override is stored.
DEFAULT_ACTIONABLE: frozenset[str] = frozenset(
    {
        "disconnected_strings",
        "module_damage",
        "inverter_efficiency",
    }
)

DEFAULT_NON_ACTIONABLE: frozenset[str] = frozenset(
    {
        "clipping_power",
        "clipping_current",
    }
)


def _known_fault_ids() -> list[str]:
    # Prefer product-facing set; include any meta keys for future modules.
    ids = set(FAULT_ALGORITHM_IDS) | set(FAULT_MODULE_META)
    return sorted(ids)


def default_category_map() -> dict[str, FaultCategory]:
    out: dict[str, FaultCategory] = {}
    for aid in _known_fault_ids():
        if aid in DEFAULT_NON_ACTIONABLE:
            out[aid] = "non_actionable"
        else:
            # Unknown / new fault modules default to actionable (safer for ops).
            out[aid] = "actionable"
    return out


def _normalize_stored(raw: Any) -> dict[str, FaultCategory] | None:
    if not isinstance(raw, dict):
        return None
    categories = raw.get("categories")
    if isinstance(categories, dict) and categories:
        out: dict[str, FaultCategory] = {}
        for k, v in categories.items():
            if not isinstance(k, str):
                continue
            if v in ("actionable", "non_actionable"):
                out[k] = v  # type: ignore[assignment]
        return out or None

    actionable = raw.get("actionable")
    non_actionable = raw.get("non_actionable")
    if not isinstance(actionable, list) and not isinstance(non_actionable, list):
        return None
    out = {}
    if isinstance(non_actionable, list):
        for aid in non_actionable:
            if isinstance(aid, str) and aid.strip():
                out[aid.strip()] = "non_actionable"
    if isinstance(actionable, list):
        for aid in actionable:
            if isinstance(aid, str) and aid.strip():
                out[aid.strip()] = "actionable"
    return out or None


def resolve_category_map(db: Session | None) -> dict[str, FaultCategory]:
    """Merge defaults with optional AppSetting override."""
    merged = default_category_map()
    if db is None:
        return merged
    from backend.app.models import AppSetting

    row = db.get(AppSetting, SETTING_KEY)
    if row is None or row.value_json is None:
        return merged
    override = _normalize_stored(row.value_json)
    if not override:
        return merged
    for aid, cat in override.items():
        if aid in merged or aid in FAULT_ALGORITHM_IDS or aid in FAULT_MODULE_META:
            merged[aid] = cat
        else:
            # Allow classifying newly registered modules stored by admin.
            merged[aid] = cat
    return merged


def category_payload(db: Session | None) -> dict[str, Any]:
    cats = resolve_category_map(db)
    actionable = sorted(aid for aid, c in cats.items() if c == "actionable")
    non_actionable = sorted(aid for aid, c in cats.items() if c == "non_actionable")
    modules = []
    for aid in sorted(cats.keys()):
        meta = FAULT_MODULE_META.get(aid, {})
        modules.append(
            {
                "algorithm_id": aid,
                "label": meta.get("label") or aid.replace("_", " ").title(),
                "hint": meta.get("hint") or "",
                "category": cats[aid],
                "is_default": cats[aid]
                == default_category_map().get(aid, "actionable"),
            }
        )
    return {
        "actionable": actionable,
        "non_actionable": non_actionable,
        "categories": cats,
        "modules": modules,
    }


def save_categories(
    db: Session,
    *,
    actionable: list[str] | None = None,
    non_actionable: list[str] | None = None,
    categories: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Persist override. Every known fault id should land in exactly one bucket."""
    from backend.app.models import AppSetting

    known = set(_known_fault_ids())
    resolved: dict[str, FaultCategory] = {}

    if categories:
        for aid, cat in categories.items():
            if aid not in known and aid not in FAULT_ALGORITHM_IDS:
                continue
            if cat not in ("actionable", "non_actionable"):
                raise ValueError(f"Invalid category for {aid}: {cat}")
            resolved[aid] = cat  # type: ignore[assignment]
    else:
        for aid in non_actionable or []:
            if aid in known or aid in FAULT_ALGORITHM_IDS:
                resolved[aid] = "non_actionable"
        for aid in actionable or []:
            if aid in known or aid in FAULT_ALGORITHM_IDS:
                resolved[aid] = "actionable"

    # Fill any missing known ids from defaults so Results never drops a module.
    defaults = default_category_map()
    for aid in known:
        if aid not in resolved:
            resolved[aid] = defaults.get(aid, "actionable")

    value = {
        "actionable": sorted(a for a, c in resolved.items() if c == "actionable"),
        "non_actionable": sorted(a for a, c in resolved.items() if c == "non_actionable"),
        "categories": resolved,
    }

    row = db.get(AppSetting, SETTING_KEY)
    if row is None:
        row = AppSetting(key=SETTING_KEY, value_json=value)
        db.add(row)
    else:
        row.value_json = value
        db.add(row)
    db.commit()
    db.refresh(row)
    return category_payload(db)
