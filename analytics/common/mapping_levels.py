"""Infer hierarchy level labels for column→canonical mapping suggestions.

Mapping is still flat (file column → canonical field). Level labels tell the Setup UI
whether a measurement is Plant / ICR / Inverter / SCB / String (or row-level via
Equipment ID) so DC power at inverter is not confused with SCB/string DC power.
"""
from __future__ import annotations

from analytics.common.equipment_ids import derive_level
from analytics.common.wide_headers import parse_wide_device_column

# Canonical identity / weather fields → fixed hierarchy level
_IDENTITY_LEVEL: dict[str, tuple[str, str]] = {
    "timestamp": ("plant", "Plant"),
    "icr_id": ("icr", "ICR"),
    "inverter_id": ("inverter", "Inverter"),
    "scb_id": ("scb", "SCB / SMB"),
    "string_id": ("string", "String"),
    "device_id": ("equipment", "Equipment (row)"),
    "poa_w_m2": ("plant", "Plant / WMS"),
    "ghi_w_m2": ("plant", "Plant / WMS"),
    "module_temp_c": ("plant", "Plant / WMS"),
    "ambient_temp_c": ("plant", "Plant / WMS"),
}

_LEVEL_LABELS: dict[str, str] = {
    "plant": "Plant / WMS",
    "icr": "ICR",
    "inverter": "Inverter",
    "scb": "SCB / SMB",
    "string": "String",
    "equipment": "Equipment (row)",
    "multi": "Multi-level",
}

# Measurements that are valid at multiple hierarchy levels when that level is in play
_MULTI_LEVEL_METRICS = frozenset(
    {"ac_power_kw", "dc_power_kw", "dc_current_a", "dc_voltage_v", "energy_kwh"}
)


def level_label(level_id: str | None) -> str | None:
    if not level_id:
        return None
    return _LEVEL_LABELS.get(level_id, level_id)


def _companion_fields(column_to_canonical: dict[str, str | None]) -> set[str]:
    return {f for f in column_to_canonical.values() if f and f != "ignore"}


def infer_hierarchy_level(
    canonical_field: str | None,
    *,
    column_name: str = "",
    companion_fields: set[str] | None = None,
) -> tuple[str | None, str | None]:
    """Return (hierarchy_level, hierarchy_level_label) for a mapped column."""
    if not canonical_field or canonical_field == "ignore":
        return None, None

    if canonical_field in _IDENTITY_LEVEL:
        level, label = _IDENTITY_LEVEL[canonical_field]
        return level, label

    # Wide plant/ICR/INV-prefixed headers carry level in the column name (pre-melt).
    if column_name:
        parsed = parse_wide_device_column(column_name)
        if parsed is not None and parsed.equipment_id:
            derived = derive_level(parsed.equipment_id)
            if derived:
                return derived, level_label(derived)
            if parsed.icr_id:
                return "inverter", level_label("inverter")

    companions = companion_fields or set()

    if canonical_field not in _MULTI_LEVEL_METRICS:
        return None, None

    # Strongest companion identity wins for tidy long files.
    if "string_id" in companions:
        return "string", level_label("string")
    if "scb_id" in companions:
        return "scb", level_label("scb")
    if "inverter_id" in companions:
        return "inverter", level_label("inverter")
    if "device_id" in companions:
        # Long-form Equipment ID rows: level is per-row via device_type after standardize.
        return "equipment", level_label("equipment")
    if "icr_id" in companions and canonical_field == "ac_power_kw":
        return "inverter", level_label("inverter")

    # No companion identity — do not claim multi-level; leave badge unset until evidence exists.
    return None, None


def annotate_mapping_levels(
    suggestions: list,
) -> list:
    """Attach hierarchy_level / hierarchy_level_label onto suggestion objects in place."""
    provisional: dict[str, str | None] = {}
    for s in suggestions:
        if isinstance(s, dict):
            provisional[str(s.get("column_name") or "")] = s.get("canonical_field")
        else:
            provisional[str(getattr(s, "column_name", "") or "")] = getattr(s, "canonical_field", None)
    companions = _companion_fields(provisional)
    for s in suggestions:
        if isinstance(s, dict):
            field = s.get("canonical_field")
            col = s.get("column_name") or ""
            level, label = infer_hierarchy_level(field, column_name=col, companion_fields=companions)
            s["hierarchy_level"] = level
            s["hierarchy_level_label"] = label
        else:
            field = getattr(s, "canonical_field", None)
            col = getattr(s, "column_name", "") or ""
            level, label = infer_hierarchy_level(field, column_name=col, companion_fields=companions)
            s.hierarchy_level = level
            s.hierarchy_level_label = label
    return suggestions


def column_hierarchy_from_mapping(column_to_canonical: dict[str, str]) -> dict[str, str]:
    """Persistable map of source column → hierarchy_level (omits unknowns)."""
    companions = _companion_fields(column_to_canonical)
    out: dict[str, str] = {}
    for col, field in column_to_canonical.items():
        if not field or field == "ignore":
            continue
        level, _ = infer_hierarchy_level(field, column_name=col, companion_fields=companions)
        if level:
            out[col] = level
    return out
