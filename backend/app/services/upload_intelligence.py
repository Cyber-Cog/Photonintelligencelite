"""Upload review intelligence: multi-level hierarchy signal matrix, architecture, module impact."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, Mapping, Optional

from analytics.common.plant_structure import DetectedStructure, infer_from_csv
from analytics.common.prerequisites import ALGORITHM_PREREQUISITES, evaluate_prerequisites

# Identity fields stay level-specific. Measurements may exist at multiple SCADA levels
# in real plants, but the upload matrix only lights a level when that level is in play
# (companion ID or confirmed device_type) — never because the same column exists elsewhere.
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

# Companion identity fields that put a hierarchy level "in play" for measurements.
_LEVEL_COMPANION_IDS: dict[str, tuple[str, ...]] = {
    "icr": ("icr_id",),
    "inverter": ("inverter_id", "device_id"),
    "scb": ("scb_id",),
    "string": ("string_id",),
}

_EQUIPMENT_IDENTITY_FIELDS = frozenset({"device_id", "inverter_id", "scb_id", "string_id", "icr_id"})

# Plant-native measurements (not shared AC/DC power columns)
_PLANT_NATIVE_MEASUREMENTS = frozenset({"irradiance", "module_temp_c", "ambient_temp_c"})
_PLANT_POWER_MEASUREMENTS = frozenset({"ac_power_kw", "dc_power_kw"})

# (field_id, label, alternate_canonicals, kind)
# kind: "identity" = level-specific; "measurement" = electrical / weather signal
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


def _level_has_companion_id(level_id: str, fields: set[str]) -> bool:
    companions = _LEVEL_COMPANION_IDS.get(level_id, ())
    return any(c in fields for c in companions)


def _has_equipment_identity(fields: set[str]) -> bool:
    return bool(fields & _EQUIPMENT_IDENTITY_FIELDS)


def _measurement_in_play_at_level(
    field_id: str,
    level_id: str,
    fields: set[str],
    typed: Mapping[str, set[str]] | None,
) -> bool:
    """Whether a measurement may be credited at this hierarchy level.

    Evidence ladder (without claiming cross-level presence):
    - confirmed device_type rows (handled by caller), or
    - companion level ID present (mapped_level_tbd until Validate), or
    - plant-native weather fields, or
    - plant AC/DC only when plant/WMS typed OR no equipment IDs (aggregate file).
    """
    if level_id == "plant_wms":
        if field_id in _PLANT_NATIVE_MEASUREMENTS:
            return True
        if field_id in _PLANT_POWER_MEASUREMENTS:
            if typed and any(typed.get(dt) for dt in _LEVEL_DEVICE_TYPES["plant_wms"]):
                return True
            # Aggregate plant file: power columns with no equipment identity
            return not _has_equipment_identity(fields)
        return False

    if level_id in _LEVEL_COMPANION_IDS:
        return _level_has_companion_id(level_id, fields)

    return False


def build_hierarchy_levels(
    present: Iterable[str],
    *,
    show_empty_optional: bool = False,
    by_device_type: Mapping[str, Iterable[str]] | None = None,
) -> list[dict[str, Any]]:
    """Per-hierarchy signal matrix from detected canonical fields.

    A measurement is present at a level only when that level is in play
    (companion ID or confirmed ``device_type``), not merely because the same
    canonical column exists on another level. ``mapped_level_tbd`` is used only
    when a level ID companion exists but device_type is not yet confirmed.

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
            elif kind == "identity" and ok:
                evidence = _EVIDENCE_CONFIRMED
                present_flag = True
            elif kind == "measurement" and ok and _measurement_in_play_at_level(
                field_id, level_id, fields, typed
            ):
                # Level companion / plant-native evidence without device_type yet
                evidence = _EVIDENCE_MAPPED_TBD
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


def _level_in_play_for_preview(
    device_type: str,
    present: set[str],
    architecture_summary: Mapping[str, Any],
) -> bool:
    """Whether upload evidence suggests a device level could exist for this job."""
    if device_type == "scb":
        if "scb_id" in present:
            return True
        return int(architecture_summary.get("scb_count") or 0) > 0
    if device_type == "string":
        if "string_id" in present:
            return True
        return int(architecture_summary.get("string_count") or 0) > 0
    if device_type == "inverter":
        return "device_id" in present or "inverter_id" in present or int(
            architecture_summary.get("inverter_count") or 0
        ) > 0
    return True


def _downgrade_preliminary_without_level(
    row: dict[str, Any],
    *,
    present: set[str],
    architecture_summary: Mapping[str, Any],
) -> dict[str, Any]:
    """Block SCB/string modules when that level is clearly not in play (no false may-run)."""
    if not row.get("preliminary"):
        return row
    spec = ALGORITHM_PREREQUISITES.get(row["algorithm_id"])
    if spec is None:
        return row

    if spec.required_at_any_device_type:
        any_types = {dtype for dtype, _fields in spec.required_at_any_device_type}
        if any(_level_in_play_for_preview(t, present, architecture_summary) for t in any_types):
            return row
        gap_token = " or ".join(
            f"{dtype}:{f}"
            for dtype, fields in spec.required_at_any_device_type
            for f in fields
        )
        level_names = " / ".join(sorted(any_types))
    elif spec.required_at_device_type:
        needed = set(spec.required_at_device_type.keys())
        if all(_level_in_play_for_preview(t, present, architecture_summary) for t in needed):
            return row
        gap_token = None
        level_names = ", ".join(sorted(needed))
    else:
        return row

    missing = list(row.get("missing_fields") or [])
    if spec.required_at_any_device_type:
        if gap_token and gap_token not in missing:
            missing.append(gap_token)
    else:
        for dtype, fields in spec.required_at_device_type.items():
            for f in fields:
                token = f"{dtype}:{f}"
                if token not in missing:
                    missing.append(token)

    return {
        **row,
        "preliminary": False,
        "will_run": False,
        "missing_fields": missing,
        "message": (
            f"Needs {level_names}-level telemetry — not detected in this upload "
            f"(inverter-only columns are not enough). {spec.how_to_fix}".strip()
        ),
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
    When SCB/string is clearly absent (0 count, no level ID), those modules are blocked
    rather than shown as “may run”.
    """
    present = _present_from_suggestions(suggestions)
    plant = plant_config or {}
    has_arch = bool(architecture_summary.get("detected")) or bool(plant.get("architecture"))
    has_ratings = bool(
        plant.get("equipment_ratings")
        or plant.get("inverter_capacity_kw")
        or plant.get("imported_inverter_capacity_kw")
    )
    rows = [
        _downgrade_preliminary_without_level(
            r, present=present, architecture_summary=architecture_summary
        )
        for r in evaluate_prerequisites(
            available_fields=present,
            has_architecture=has_arch,
            has_equipment_ratings=has_ratings,
            level_evidence=False,
        )
    ]
    blocked = [r for r in rows if not r["will_run"] and not r.get("preliminary")]
    may_run = [r for r in rows if r.get("preliminary")]
    ready = [r for r in rows if r["will_run"]]
    return {
        "preview_note": (
            "Preliminary — based on detected columns and which hierarchy levels are in play. "
            "Validate confirms device_type (e.g. SCB vs inverter voltage) before Results. "
            "Algorithms still require the correct level — inverter DC does not satisfy SCB modules."
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
            # Same measurement id can appear under several levels — report once
            if sid and sid in seen_ids and sig.get("kind") == "measurement":
                continue
            if sid:
                seen_ids.add(sid)
            missing.append(f"{prefix}: {sig.get('label', sid)}")
    return missing
