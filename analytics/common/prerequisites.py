"""Central algorithm prerequisite map — honest “what’s missing” messaging.

Used by the orchestrator (runtime skip), validation summary (setup honesty), and
dashboard ResultCard copy. Field names are canonical schema columns.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass(frozen=True)
class AlgorithmPrerequisite:
    algorithm_id: str
    title: str
    required_fields: tuple[str, ...] = ()
    """All of these canonical fields must be present in the upload."""
    any_of_field_groups: tuple[tuple[str, ...], ...] = ()
    """Each group is an OR — at least one field in the group must be present."""
    requires_architecture: bool = False
    """True when SCB→inverter (and usually strings_per_scb) mapping is needed for loss magnitude."""
    requires_equipment_ratings: bool = False
    field_labels: dict[str, str] = field(default_factory=dict)
    how_to_fix: str = ""


FIELD_LABELS: dict[str, str] = {
    "ac_power_kw": "AC power (kW)",
    "dc_power_kw": "DC power (kW)",
    "dc_current_a": "DC current (A)",
    "dc_voltage_v": "DC voltage (V)",
    "poa_w_m2": "POA irradiance (W/m²)",
    "ghi_w_m2": "GHI irradiance (W/m²)",
    "module_temp_c": "Module temperature (°C)",
    "ambient_temp_c": "Ambient temperature (°C)",
    "device_id": "Device / equipment ID",
    "inverter_id": "Inverter ID",
    "scb_id": "SCB / SMB ID",
    "string_id": "String ID",
}


ALGORITHM_PREREQUISITES: dict[str, AlgorithmPrerequisite] = {
    "kpis": AlgorithmPrerequisite(
        algorithm_id="kpis",
        title="Plant KPIs",
        required_fields=("ac_power_kw",),
        how_to_fix="Map an AC power column from the inverter report.",
    ),
    "inverter_efficiency": AlgorithmPrerequisite(
        algorithm_id="inverter_efficiency",
        title="Inverter Efficiency Loss",
        required_fields=("ac_power_kw",),
        any_of_field_groups=(("dc_power_kw", "dc_current_a"),),
        how_to_fix=(
            "Map inverter AC power plus DC power. If you only have SCB DC current (and "
            "voltage), map those instead — DC power is derived from ΣI×V per inverter."
        ),
    ),
    "box_plot": AlgorithmPrerequisite(
        algorithm_id="box_plot",
        title="Box Plot Analysis",
        required_fields=("ac_power_kw",),
        any_of_field_groups=(("dc_power_kw", "dc_current_a"),),
        how_to_fix="Same inputs as efficiency: AC power plus DC power (or SCB DC current).",
    ),
    "clipping_power": AlgorithmPrerequisite(
        algorithm_id="clipping_power",
        title="Inverter Clipping by Power",
        required_fields=("ac_power_kw",),
        any_of_field_groups=(("poa_w_m2", "ghi_w_m2"),),
        requires_equipment_ratings=True,
        how_to_fix=(
            "Map inverter AC power and plant/WMS irradiance (POA or GHI). "
            "Provide inverter ratings in equipment structure for accurate clip limits."
        ),
    ),
    "clipping_current": AlgorithmPrerequisite(
        algorithm_id="clipping_current",
        title="Inverter Clipping by Current",
        required_fields=("dc_current_a",),
        any_of_field_groups=(("poa_w_m2", "ghi_w_m2"),),
        requires_architecture=True,
        how_to_fix=(
            "Map SCB/MPPT DC current and plant/WMS irradiance (POA or GHI). "
            "Upload plant architecture (SMBs per inverter × strings per SMB) so rated current can be estimated."
        ),
    ),
    "module_damage": AlgorithmPrerequisite(
        algorithm_id="module_damage",
        title="Module Damage / Voltage Fault",
        required_fields=("dc_voltage_v",),
        requires_architecture=True,
        how_to_fix=(
            "Map SCB-level DC voltage. Architecture (SCB → inverter) is required to build a peer reference."
        ),
    ),
    "disconnected_strings": AlgorithmPrerequisite(
        algorithm_id="disconnected_strings",
        title="Disconnected Strings",
        required_fields=("dc_current_a",),
        any_of_field_groups=(("poa_w_m2", "ghi_w_m2"),),
        requires_architecture=True,
        how_to_fix=(
            "Map SCB/string DC current and irradiance. "
            "Provide architecture so each SCB is linked to its parent inverter and string count."
        ),
    ),
    "string_outlier": AlgorithmPrerequisite(
        algorithm_id="string_outlier",
        title="String Current Outlier",
        required_fields=("dc_current_a",),
        how_to_fix="Map string- or SCB-level DC current with resolvable equipment IDs.",
    ),
}


def label_for(field: str) -> str:
    return FIELD_LABELS.get(field, field.replace("_", " "))


def evaluate_prerequisites(
    *,
    available_fields: set[str],
    has_architecture: bool = False,
    has_equipment_ratings: bool = False,
    algorithm_ids: Optional[list[str]] = None,
) -> list[dict[str, Any]]:
    """Return readiness rows for Setup / Validation / Dashboard.

    Each row: algorithm_id, title, will_run, missing_fields, missing_config, message, how_to_fix.
    """
    ids = algorithm_ids or list(ALGORITHM_PREREQUISITES.keys())
    rows: list[dict[str, Any]] = []
    for aid in ids:
        spec = ALGORITHM_PREREQUISITES.get(aid)
        if spec is None:
            continue
        missing_fields: list[str] = [f for f in spec.required_fields if f not in available_fields]
        for group in spec.any_of_field_groups:
            if not any(f in available_fields for f in group):
                # Represent the whole OR group as a single actionable gap
                missing_fields.append(" or ".join(group))

        missing_config: list[str] = []
        if spec.requires_architecture and not has_architecture:
            missing_config.append("plant architecture (inverter → SMB/SCB → strings)")
        if spec.requires_equipment_ratings and not has_equipment_ratings:
            missing_config.append("inverter ratings (kW)")

        will_run = not missing_fields and not missing_config
        parts: list[str] = []
        if missing_fields:
            labeled = [label_for(f) if " or " not in f else " / ".join(label_for(x) for x in f.split(" or ")) for f in missing_fields]
            parts.append(
                "You have not provided "
                + ", ".join(labeled)
                + " — this fault cannot be computed until you upload/map it."
            )
        if missing_config:
            parts.append(
                "You have not provided "
                + " and ".join(missing_config)
                + " — configure it in Setup (Excel template, auto-detect, or pattern apply)."
            )
        message = " ".join(parts) if parts else f"{spec.title} has the inputs it needs and will run."
        rows.append(
            {
                "algorithm_id": aid,
                "title": spec.title,
                "will_run": will_run,
                "missing_fields": missing_fields,
                "missing_config": missing_config,
                "message": message,
                "how_to_fix": spec.how_to_fix,
            }
        )
    return rows


def missing_fields_for_algorithm(algorithm_id: str, available_fields: set[str]) -> set[str]:
    """Orchestrator-compatible check (fields only; config gaps are soft warnings at validation)."""
    spec = ALGORITHM_PREREQUISITES.get(algorithm_id)
    if spec is None:
        return set()
    missing = {f for f in spec.required_fields if f not in available_fields}
    for group in spec.any_of_field_groups:
        if not any(f in available_fields for f in group):
            missing.update(group)
    return missing


def actionable_unavailable_message(algorithm_id: str, missing: set[str], fallback: str = "") -> str:
    spec = ALGORITHM_PREREQUISITES.get(algorithm_id)
    title = spec.title if spec else algorithm_id.replace("_", " ").title()
    if not missing:
        return fallback or f"{title} could not run on this upload."
    labeled = ", ".join(sorted(label_for(f) for f in missing))
    fix = spec.how_to_fix if spec else "Map the required columns on the Setup page and re-run."
    return (
        f"You have not provided {labeled} — {title} cannot be computed until you upload/map it. "
        f"Next step: {fix}"
    )
