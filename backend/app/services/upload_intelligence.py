"""Upload review intelligence: multi-level hierarchy signal matrix, architecture, module impact."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, Mapping, Optional

from analytics.common.plant_structure import DetectedStructure, infer_from_csv
from analytics.common.prerequisites import evaluate_prerequisites

# Professional SCADA model: identity fields stay level-specific; measurement fields
# may appear at every level where real plants measure them (not a unique partition).
# SCB/string IDs must not inherit device_id (false greens). ICR is optional.
_OPTIONAL_LEVEL_IDS = frozenset({"icr"})

# Evidence kinds for matrix chips
_EVIDENCE_CONFIRMED = "confirmed"
_EVIDENCE_MAPPED_TBD = "mapped_level_tbd"

# Upload hierarchy level_id → canonical device_type partition keys
_LEVEL_DEVICE_TYPES: dict[str, tuple[str, ...]] = {
    "plant_wms": ("plant", "wms"),
    "icr": ("icr",),
    "inverter": ("inverter",),
    "scb": ("scb",),
    "string": ("string",),
}

# (field_id, label, alternate_canonicals, kind)
# kind: "identity" = level-specific; "measurement" = valid at this level (may repeat elsewhere)
_SignalDef = tuple[str, str, tuple[str, ...], str]

_HIERARCHY_LEVELS: tuple[tuple[str, str, tuple[_SignalDef, ...]], ...] = (
    (
        "plant_wms",
        "Plant / WMS (site-wide)",
        (
            ("timestamp", "Timestamp", (), "identity"),
            ("irradiance", "Irradiance (POA or GHI)", ("poa_w_m2", "ghi_w_m2"), "measurement"),
            ("module_temp_c", "Module temperature (°C)", (), "measurement"),
            ("ambient_temp_c", "Ambient temperature (°C)", (), "measurement"),
            ("ac_power_kw", "Plant AC power (kW)", (), "measurement"),
            ("dc_power_kw", "Plant DC power (kW)", (), "measurement"),
        ),
    ),
    (
        "icr",
        "ICR (Inverter Control Room)",
        (
            ("icr_id", "ICR ID", (), "identity"),
        ),
    ),
    (
        "inverter",
        "Inverter level",
        (
            ("inverter_id", "Inverter / equipment ID", ("inverter_id", "device_id"), "identity"),
            ("ac_power_kw", "AC power (kW)", (), "measurement"),
            ("dc_power_kw", "DC power (kW)", (), "measurement"),
            ("dc_current_a", "DC current (A)", (), "measurement"),
            ("dc_voltage_v", "DC voltage (V)", (), "measurement"),
            ("energy_kwh", "Energy (kWh)", (), "measurement"),
        ),
    ),
    (
        "scb",
        "SCB / SMB level",
        (
            ("scb_id", "SCB / SMB ID", (), "identity"),
            ("dc_current_a", "DC current (A)", (), "measurement"),
            ("dc_voltage_v", "DC voltage (V)", (), "measurement"),
            ("dc_power_kw", "DC power (kW)", (), "measurement"),
        ),
    ),
    (
        "string",
        "String level",
        (
            ("string_id", "String ID", (), "identity"),
            ("dc_current_a", "DC current (A)", (), "measurement"),
            ("dc_voltage_v", "DC voltage (V)", (), "measurement"),
            ("dc_power_kw", "DC power (kW)", (), "measurement"),
        ),
    ),
)


def _field_present(field_id: str, alts: tuple[str, ...], present: set[str]) -> tuple[bool, str | None]:
    if field_id in present:
        return True, field_id
    for alt in alts:
        if alt in present:
            return True, alt
    return False, None


def _confirmed_at_level(
    field_id: str,
    alts: tuple[str, ...],
    level_id: str,
    by_device_type: Mapping[str, set[str]] | None,
) -> str | None:
    """Return the matching canonical field if populated under this level's device_type(s)."""
    if not by_device_type:
        return None
    candidates = (field_id, *alts) if alts else (field_id,)
    # Irradiance pseudo-id resolves to poa/ghi
    if field_id == "irradiance":
        candidates = ("poa_w_m2", "ghi_w_m2", "irradiance")
    for dtype in _LEVEL_DEVICE_TYPES.get(level_id, ()):
        populated = by_device_type.get(dtype) or set()
        for c in candidates:
            if c in populated:
                return c
    return None


def _normalize_by_device_type(
    by_device_type: Mapping[str, Iterable[str]] | None,
) -> dict[str, set[str]] | None:
    if not by_device_type:
        return None
    return {str(k): {str(f) for f in fields if f} for k, fields in by_device_type.items()}


def build_hierarchy_levels(
    present: Iterable[str],
    *,
    show_empty_optional: bool = False,
    by_device_type: Mapping[str, Iterable[str]] | None = None,
) -> list[dict[str, Any]]:
    """Per-hierarchy signal matrix from detected canonical fields.

    Measurements that are valid at multiple levels are listed under each such level
    when present in the job mapping (not uniquely bucketed). When ``by_device_type``
    is provided, chips distinguish confirmed device_type evidence from
    column-only ``mapped_level_tbd``.

    Optional levels (ICR) are omitted when none of their signals are present.
    """
    fields = {str(f) for f in present if f}
    typed = _normalize_by_device_type(by_device_type)
    levels: list[dict[str, Any]] = []
    for level_id, title, signals in _HIERARCHY_LEVELS:
        items: list[dict[str, Any]] = []
        for field_id, label, alts, kind in signals:
            ok, via = _field_present(field_id, alts, fields)
            confirmed_via = _confirmed_at_level(field_id, alts, level_id, typed)
            if confirmed_via:
                evidence = _EVIDENCE_CONFIRMED
                present_flag = True
                via = confirmed_via
            elif ok:
                # Column/job mapping present — credit every level where the metric is valid.
                # Identities are level-specific; column match is enough. Measurements stay
                # mapped_level_tbd until device_type evidence confirms them.
                evidence = _EVIDENCE_CONFIRMED if kind == "identity" else _EVIDENCE_MAPPED_TBD
                present_flag = True
            else:
                evidence = None
                present_flag = False
                via = None
            items.append(
                {
                    "id": field_id,
                    "label": label,
                    "present": present_flag,
                    "detected_via": via,
                    "evidence": evidence,
                    "kind": kind,
                }
            )
        detected = sum(1 for i in items if i["present"])
        if level_id in _OPTIONAL_LEVEL_IDS and detected == 0 and not show_empty_optional:
            continue
        levels.append(
            {
                "level_id": level_id,
                "title": title,
                "signals": items,
                "detected_count": detected,
                "total_count": len(items),
                "optional": level_id in _OPTIONAL_LEVEL_IDS,
            }
        )
    return levels


def _present_from_suggestions(suggestions: Iterable[Any]) -> set[str]:
    present: set[str] = set()
    for s in suggestions:
        field = getattr(s, "canonical_field", None) or (s.get("canonical_field") if isinstance(s, dict) else None)
        if field and field != "ignore":
            present.add(str(field))
    if "poa_w_m2" in present or "ghi_w_m2" in present:
        present.add("poa_w_m2")
        present.add("ghi_w_m2")
    return present


def _suggestions_to_mapping(suggestions: Iterable[Any]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for s in suggestions:
        col = getattr(s, "column_name", None) or (s.get("column_name") if isinstance(s, dict) else None)
        field = getattr(s, "canonical_field", None) or (s.get("canonical_field") if isinstance(s, dict) else None)
        if col and field and field != "ignore":
            mapping[str(col)] = str(field)
    return mapping


def _counts_from_structure(structure: DetectedStructure) -> tuple[int, int, int]:
    n_inv = len(structure.inverters)
    n_scb = sum(len(inv.scbs) for inv in structure.inverters.values())
    n_str = sum(
        scb.strings_per_scb or len(scb.string_ids)
        for inv in structure.inverters.values()
        for scb in inv.scbs.values()
    )
    return n_inv, n_scb, n_str


def _counts_from_plant_architecture(plant: Mapping[str, Any]) -> tuple[int, int, int]:
    arch = plant.get("architecture") or {}
    inverters: set[str] = set()
    scbs = 0
    strings = 0
    for _scb_id, entry in arch.items():
        if not isinstance(entry, dict):
            continue
        scbs += 1
        inv = entry.get("inverter_id")
        if inv:
            inverters.add(str(inv))
        sps = entry.get("strings_per_scb")
        if sps is not None:
            try:
                strings += int(sps)
            except (TypeError, ValueError):
                pass
    for inv in plant.get("inverters") or []:
        if isinstance(inv, dict) and inv.get("inverter_id"):
            inverters.add(str(inv["inverter_id"]))
    return len(inverters), scbs, strings


def build_architecture_summary(
    *,
    plant_config: Mapping[str, Any] | None,
    csv_path: Path | None,
    suggestions: Iterable[Any],
) -> dict[str, Any]:
    """Architecture snapshot for Upload review — pack import preferred, else CSV inference."""
    plant = plant_config or {}
    inv_n, scb_n, str_n = _counts_from_plant_architecture(plant)
    notes: list[str] = []
    source = "not_detected"
    detected = False

    if scb_n > 0 or inv_n > 0:
        detected = True
        source = "pack_import" if plant.get("architecture_imported") else "saved_config"
        notes.append(
            f"From plant configuration: {inv_n} inverter(s), {scb_n} SCB(s)"
            + (f", {str_n} string slot(s)" if str_n else "")
            + "."
        )
    elif csv_path and csv_path.exists():
        mapping = _suggestions_to_mapping(suggestions)
        structure = infer_from_csv(csv_path, mapping)
        inv_n, scb_n, str_n = _counts_from_structure(structure)
        if structure.detected:
            detected = True
            source = structure.source or "detected_from_ids"
        notes.extend(structure.notes or [])

    return {
        "detected": detected,
        "source": source,
        "inverter_count": inv_n,
        "scb_count": scb_n,
        "string_count": str_n,
        "notes": notes[:4],
    }


def build_module_impact_preview(
    *,
    suggestions: Iterable[Any],
    plant_config: Mapping[str, Any] | None,
    architecture_summary: Mapping[str, Any],
) -> dict[str, Any]:
    """Preview which fault/diagnostic modules may not run based on detected columns.

    Column-only preview cannot confirm hierarchy levels — level-sensitive modules
    (Module Damage, clipping by current, …) are never counted as confirmed ready here.
    """
    present = _present_from_suggestions(suggestions)
    plant = plant_config or {}
    has_arch = bool(architecture_summary.get("detected")) or bool(plant.get("architecture"))
    has_ratings = bool(
        plant.get("equipment_ratings")
        or plant.get("inverter_capacity_kw")
        or plant.get("imported_inverter_capacity_kw")
    )
    rows = evaluate_prerequisites(
        available_fields=present,
        has_architecture=has_arch,
        has_equipment_ratings=has_ratings,
        level_evidence=False,
    )
    blocked = [r for r in rows if not r["will_run"] and not r.get("preliminary")]
    may_run = [r for r in rows if r.get("preliminary")]
    ready = [r for r in rows if r["will_run"]]
    return {
        "preview_note": (
            "Preliminary — based on detected column names only. "
            "Validate confirms hierarchy levels (e.g. SCB vs inverter voltage) before Results. "
            "Measurements may appear at multiple levels; algorithms still require the correct device_type."
        ),
        "ready_count": len(ready),
        "may_run_count": len(may_run),
        "blocked_count": len(blocked),
        "may_run_modules": [
            {
                "algorithm_id": r["algorithm_id"],
                "title": r["title"],
                "message": r["message"],
                "missing_fields": r.get("missing_fields") or [],
                "missing_config": r.get("missing_config") or [],
            }
            for r in may_run
        ],
        "blocked_modules": [
            {
                "algorithm_id": r["algorithm_id"],
                "title": r["title"],
                "message": r["message"],
                "missing_fields": r.get("missing_fields") or [],
                "missing_config": r.get("missing_config") or [],
            }
            for r in blocked
        ],
    }


def enrich_file_inventory_item(
    item: dict[str, Any],
    *,
    by_device_type: Mapping[str, Iterable[str]] | None = None,
) -> dict[str, Any]:
    """Ensure per-file hierarchy matrix exists (rebuild from signals_present when missing)."""
    if not item.get("hierarchy_levels"):
        present = item.get("signals_present") or []
        item["hierarchy_levels"] = build_hierarchy_levels(present, by_device_type=by_device_type)
    return item


def build_upload_intelligence(
    *,
    suggestions: Iterable[Any],
    plant_config: Mapping[str, Any] | None,
    csv_path: Path | None,
    file_inventory: list[dict[str, Any]] | None = None,
    by_device_type: Mapping[str, Iterable[str]] | None = None,
) -> dict[str, Any]:
    """Job-level upload intelligence bundle for API responses."""
    present = _present_from_suggestions(suggestions)
    arch = build_architecture_summary(
        plant_config=plant_config,
        csv_path=csv_path,
        suggestions=suggestions,
    )
    impact = build_module_impact_preview(
        suggestions=suggestions,
        plant_config=plant_config,
        architecture_summary=arch,
    )
    inventory = [
        enrich_file_inventory_item(dict(f), by_device_type=by_device_type) for f in (file_inventory or [])
    ]
    return {
        "hierarchy_overview": build_hierarchy_levels(present, by_device_type=by_device_type),
        "architecture_summary": arch,
        "module_impact_preview": impact,
        "file_inventory": inventory,
    }


def hierarchy_missing_labels(levels: list[dict[str, Any]]) -> list[str]:
    """Flat list of missing signal labels across hierarchy levels (deduped by signal id)."""
    missing: list[str] = []
    seen_ids: set[str] = set()
    for level in levels:
        prefix = level.get("title", "")
        for sig in level.get("signals") or []:
            if sig.get("present"):
                continue
            sid = str(sig.get("id") or "")
            # Measurements listed at multiple levels — report once
            if sid and sid in seen_ids and sig.get("kind") == "measurement":
                continue
            if sid:
                seen_ids.add(sid)
            missing.append(f"{prefix}: {sig.get('label', sid)}")
    return missing
