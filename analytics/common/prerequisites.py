"""Central algorithm prerequisite map — honest “what’s missing” messaging.

Used by the orchestrator (runtime skip), validation summary (setup honesty), upload
impact preview, and dashboard ResultCard copy. Field names are canonical schema columns.

Level-aware rules (``required_at_device_type`` / ``required_at_any_device_type``) ensure
Validation / Results stay in sync: a column present only on inverter or plant rows must
not mark SCB-only algorithms as ready.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Optional

from analytics.common.module_kinds import module_kind


@dataclass(frozen=True)
class AlgorithmPrerequisite:
    algorithm_id: str
    title: str
    required_fields: tuple[str, ...] = ()
    """All of these canonical fields must be present in the upload (column-level)."""
    any_of_field_groups: tuple[tuple[str, ...], ...] = ()
    """Each group is an OR — at least one field in the group must be present."""
    required_at_device_type: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    """Fields that must be populated on rows of the given device_type (AND across types).

    Example: ``{"scb": ("dc_voltage_v",)}`` — Module Damage needs SCB-level voltage, not
    merely a ``dc_voltage_v`` column on inverter/plant rows.
    """
    required_at_any_device_type: tuple[tuple[str, tuple[str, ...]], ...] = ()
    """OR across device levels — at least one (device_type, fields) group must be fully present.

    Example: disconnected strings can use SCB or string DC current.
    """
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

DEVICE_TYPE_LABELS: dict[str, str] = {
    "scb": "SCB-level",
    "string": "string-level",
    "inverter": "inverter-level",
    "plant": "plant-level",
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
        required_at_device_type={"scb": ("dc_current_a",)},
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
        required_at_device_type={"scb": ("dc_voltage_v",)},
        requires_architecture=True,
        how_to_fix=(
            "Map SCB-level DC voltage (not inverter- or plant-only voltage). "
            "Architecture (SCB → inverter) is required to build a peer reference."
        ),
    ),
    "disconnected_strings": AlgorithmPrerequisite(
        algorithm_id="disconnected_strings",
        title="Disconnected Strings",
        required_fields=("dc_current_a",),
        any_of_field_groups=(("poa_w_m2", "ghi_w_m2"),),
        required_at_any_device_type=(
            ("scb", ("dc_current_a",)),
            ("string", ("dc_current_a",)),
        ),
        requires_architecture=True,
        how_to_fix=(
            "Map SCB or string DC current and irradiance. "
            "Provide architecture so each SCB is linked to its parent inverter and string count."
        ),
    ),
}


def label_for(field: str) -> str:
    return FIELD_LABELS.get(field, field.replace("_", " "))


def level_field_label(device_type: str, field: str) -> str:
    level = DEVICE_TYPE_LABELS.get(device_type, f"{device_type}-level")
    return f"{level} {label_for(field)}"


def _encode_level_gap(device_type: str, field: str) -> str:
    return f"{device_type}:{field}"


def _decode_level_gap(token: str) -> tuple[str, str] | None:
    if ":" not in token or " or " in token:
        return None
    dtype, _, field = token.partition(":")
    if not dtype or not field or field.startswith(" "):
        return None
    return dtype, field


def _level_fields_present(
    available_by_device_type: Mapping[str, set[str]],
    device_type: str,
    fields: tuple[str, ...],
) -> bool:
    present = available_by_device_type.get(device_type, set())
    return all(f in present for f in fields)


def _missing_level_requirements(
    spec: AlgorithmPrerequisite,
    available_by_device_type: Mapping[str, set[str]] | None,
    *,
    level_evidence: bool,
) -> list[str]:
    """Return encoded level gaps. Empty when satisfied or when level evidence is unavailable.

    When ``level_evidence`` is False (upload column preview), level gaps are not emitted
    here — callers treat those algorithms as preliminary instead of confirmed ready.
    """
    if not level_evidence or available_by_device_type is None:
        return []

    missing: list[str] = []
    for dtype, fields in spec.required_at_device_type.items():
        for f in fields:
            if f not in available_by_device_type.get(dtype, set()):
                missing.append(_encode_level_gap(dtype, f))

    if spec.required_at_any_device_type:
        if not any(
            _level_fields_present(available_by_device_type, dtype, fields)
            for dtype, fields in spec.required_at_any_device_type
        ):
            # Represent the OR of levels as one actionable gap
            parts = []
            for dtype, fields in spec.required_at_any_device_type:
                for f in fields:
                    parts.append(_encode_level_gap(dtype, f))
            missing.append(" or ".join(parts))

    return missing


def _needs_level_confirmation(spec: AlgorithmPrerequisite) -> bool:
    return bool(spec.required_at_device_type) or bool(spec.required_at_any_device_type)


def evaluate_prerequisites(
    *,
    available_fields: set[str],
    has_architecture: bool = False,
    has_equipment_ratings: bool = False,
    algorithm_ids: Optional[list[str]] = None,
    available_by_device_type: Optional[Mapping[str, set[str]]] = None,
    level_evidence: Optional[bool] = None,
) -> list[dict[str, Any]]:
    """Return readiness rows for Setup / Validation / Dashboard / Upload preview.

    Each row: algorithm_id, title, will_run, preliminary, missing_fields, missing_config,
    message, how_to_fix, module_kind.

    Pass ``available_by_device_type`` (from canonical partitions) for Validation and the
    orchestrator so SCB-only modules cannot go green on inverter/plant telemetry.
    Upload preview omits level evidence — level-sensitive modules that pass column checks
    are marked ``preliminary=True`` and ``will_run=False`` (may run after Validate).
    """
    ids = algorithm_ids or list(ALGORITHM_PREREQUISITES.keys())
    # Explicit flag wins; otherwise infer from whether per-type evidence was supplied.
    resolved_level_evidence = (
        bool(level_evidence) if level_evidence is not None else available_by_device_type is not None
    )
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

        missing_fields.extend(
            _missing_level_requirements(
                spec,
                available_by_device_type,
                level_evidence=resolved_level_evidence,
            )
        )

        missing_config: list[str] = []
        if spec.requires_architecture and not has_architecture:
            missing_config.append("plant architecture (inverter → SMB/SCB → strings)")
        if spec.requires_equipment_ratings and not has_equipment_ratings:
            missing_config.append("inverter ratings (kW)")

        column_ok = not missing_fields and not missing_config
        needs_level = _needs_level_confirmation(spec)
        preliminary = bool(needs_level and not resolved_level_evidence and column_ok)

        # Upload / column-only: do not claim confirmed will_run for level-sensitive modules.
        if preliminary:
            will_run = False
        else:
            will_run = column_ok

        parts: list[str] = []
        if missing_fields:
            labeled: list[str] = []
            for f in missing_fields:
                if " or " in f:
                    bits = []
                    for tok in f.split(" or "):
                        decoded = _decode_level_gap(tok)
                        bits.append(level_field_label(*decoded) if decoded else label_for(tok))
                    labeled.append(" / ".join(bits))
                else:
                    decoded = _decode_level_gap(f)
                    labeled.append(level_field_label(*decoded) if decoded else label_for(f))
            parts.append("Needs: " + ", ".join(labeled) + ".")
        if missing_config:
            parts.append("Needs config: " + " and ".join(missing_config) + ".")
        if parts:
            fix = spec.how_to_fix.strip()
            message = " ".join(parts) + (f" {fix}" if fix else "")
        elif preliminary:
            message = (
                f"{spec.title} may run after Validate confirms hierarchy levels "
                f"(column check only — not confirmed ready yet)."
            )
        else:
            message = f"{spec.title} has the inputs it needs and will run."
        rows.append(
            {
                "algorithm_id": aid,
                "title": spec.title,
                "will_run": will_run,
                "preliminary": preliminary,
                "missing_fields": missing_fields,
                "missing_config": missing_config,
                "message": message,
                "how_to_fix": spec.how_to_fix,
                "module_kind": module_kind(aid),
            }
        )
    return rows


def missing_fields_for_algorithm(
    algorithm_id: str,
    available_fields: set[str],
    *,
    available_by_device_type: Optional[Mapping[str, set[str]]] = None,
) -> set[str]:
    """Orchestrator-compatible check (fields + hierarchy levels when evidence provided)."""
    spec = ALGORITHM_PREREQUISITES.get(algorithm_id)
    if spec is None:
        return set()
    missing = {f for f in spec.required_fields if f not in available_fields}
    for group in spec.any_of_field_groups:
        if not any(f in available_fields for f in group):
            missing.update(group)
    if available_by_device_type is not None:
        for gap in _missing_level_requirements(
            spec, available_by_device_type, level_evidence=True
        ):
            if " or " in gap:
                for tok in gap.split(" or "):
                    decoded = _decode_level_gap(tok)
                    if decoded:
                        missing.add(decoded[1])
                    else:
                        missing.add(tok)
            else:
                decoded = _decode_level_gap(gap)
                if decoded:
                    missing.add(decoded[1])
                else:
                    missing.add(gap)
    return missing


def actionable_unavailable_message(algorithm_id: str, missing: set[str], fallback: str = "") -> str:
    spec = ALGORITHM_PREREQUISITES.get(algorithm_id)
    title = spec.title if spec else algorithm_id.replace("_", " ").title()
    if not missing:
        return fallback or f"{title} could not run on this upload."

    # Prefer level-aware wording when the algorithm declares SCB/string requirements.
    labeled_parts: list[str] = []
    remaining = set(missing)
    if spec:
        for dtype, fields in spec.required_at_device_type.items():
            for f in fields:
                if f in remaining:
                    labeled_parts.append(level_field_label(dtype, f))
                    remaining.discard(f)
        if spec.required_at_any_device_type and any(
            f in missing for _dtype, fields in spec.required_at_any_device_type for f in fields
        ):
            # One of the OR levels was required but none satisfied — describe the OR.
            or_labels = []
            for dtype, fields in spec.required_at_any_device_type:
                for f in fields:
                    or_labels.append(level_field_label(dtype, f))
                    remaining.discard(f)
            if or_labels:
                labeled_parts.append(" / ".join(or_labels))

    labeled_parts.extend(sorted(label_for(f) for f in remaining))
    labeled = ", ".join(labeled_parts)
    fix = spec.how_to_fix if spec else "Map the required columns on the Setup page and re-run."
    return f"Needs: {labeled}. {title} cannot run until these are mapped. Next step: {fix}"
