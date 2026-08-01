"""Upload review intelligence: multi-level hierarchy signal matrix, architecture, module impact."""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from analytics.common.equipment_ids import derive_level
from analytics.common.plant_structure import DetectedStructure, infer_from_csv
from analytics.common.prerequisites import ALGORITHM_PREREQUISITES, evaluate_prerequisites
from analytics.common.wide_headers import parse_wide_device_column

# Identity fields stay level-specific. Measurements may exist at multiple SCADA levels
# in real plants, but the upload matrix only lights a level when that level is in play
# (companion ID, wide-header provenance, or confirmed device_type) — never because the
# same canonical column exists elsewhere. SCB/string IDs must not inherit device_id
# (false greens). ICR is optional.
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

# Wide historian headers (pre-melt) imply identity companions for matrix gating only.
_WIDE_LEVEL_TO_COMPANION: dict[str, str] = {
    "inverter": "device_id",
    "scb": "scb_id",
    "string": "string_id",
    "icr": "icr_id",
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


def _column_names_from_suggestions(suggestions: Iterable[Any] | None) -> list[str]:
    cols: list[str] = []
    for s in suggestions or []:
        col = getattr(s, "column_name", None) or (s.get("column_name") if isinstance(s, dict) else None)
        if col:
            cols.append(str(col))
    return cols


def companion_boosts_from_reshape(reshape_report: Mapping[str, Any] | None) -> set[str]:
    """After a successful wide melt, tidy Equipment ID rows imply level companions."""
    if not reshape_report or not reshape_report.get("reshaped"):
        return set()
    boosts: set[str] = set()
    if int(reshape_report.get("scb_count") or 0) > 0 or reshape_report.get("scb_ids"):
        boosts.add("scb_id")
        boosts.add("device_id")
    if int(reshape_report.get("string_count") or 0) > 0:
        boosts.add("string_id")
    if int(reshape_report.get("inverter_count") or 0) > 0 or reshape_report.get("inverters_found"):
        boosts.add("device_id")
    if reshape_report.get("icr_ids"):
        boosts.add("icr_id")
    # WMS melt notes / columns → plant-native fields stay in play for Plant / WMS chips.
    mapped = {str(c) for c in (reshape_report.get("columns_mapped") or [])}
    warnings = " ".join(str(w) for w in (reshape_report.get("warnings") or []))
    if (
        reshape_report.get("wms_ids")
        or "GHI (W/m2)" in mapped
        or "Irradiance (W/m2)" in mapped
        or "WMS" in warnings
    ):
        boosts.add("device_id")
    return boosts


def infer_by_device_type_from_csv(csv_path: Path | None) -> dict[str, set[str]] | None:
    """Partition tidy long-form columns by Equipment ID → device_type.

    After wide INV+WMS melts, GHI/POA live on ``device_type=wms`` rows while AC/DC
    live on inverters. Upload hierarchy uses this to mark Plant/WMS irradiance as
    confirmed (not merely column-mapped).
    """
    if csv_path is None or not Path(csv_path).exists():
        return None
    try:
        import pandas as pd

        from analytics.common.complete_analysis_pack import OFFICIAL_COLUMN_TO_CANONICAL

        df = pd.read_csv(csv_path, nrows=80_000, low_memory=False)
    except Exception:
        return None

    eq_col = next(
        (c for c in ("Equipment ID", "equipment_id", "device_id") if c in df.columns),
        None,
    )
    if eq_col is None or df.empty:
        return None

    col_to_canon: dict[str, str] = {}
    for col in df.columns:
        if col == eq_col:
            col_to_canon[col] = "device_id"
        elif col in OFFICIAL_COLUMN_TO_CANONICAL:
            col_to_canon[col] = OFFICIAL_COLUMN_TO_CANONICAL[col]
        elif col in {"ICR ID", "icr_id"}:
            col_to_canon[col] = "icr_id"
        elif col in {"Timestamp", "timestamp", "timestamp_utc"}:
            col_to_canon[col] = "timestamp"

    if len(col_to_canon) <= 1:
        return None

    by_type: dict[str, set[str]] = {}
    for eid, group in df.groupby(eq_col, sort=False):
        level = derive_level(eid)
        if level is None:
            el = str(eid).strip().lower()
            if el in {"wms", "plant"} or el.endswith("-wms") or el.startswith("wms"):
                level = "wms"
            else:
                level = "inverter"
        populated = by_type.setdefault(level, set())
        populated.add("device_id")
        for col, canon in col_to_canon.items():
            if canon == "device_id":
                continue
            if canon == "timestamp":
                populated.add("timestamp")
                continue
            if col not in group.columns:
                continue
            series = group[col]
            if canon in {"icr_id", "scb_id", "string_id", "inverter_id"}:
                if series.fillna("").astype(str).str.strip().ne("").any():
                    populated.add(canon)
                continue
            numeric = pd.to_numeric(series, errors="coerce")
            if numeric.notna().any():
                populated.add(canon)

    return by_type or None


def companion_boosts_from_wide_columns(column_names: Iterable[str] | None) -> set[str]:
    """Synthetic identity companions implied by wide device×metric headers (pre-melt).

    Example: ``ESSP_20MW ICR1 Inverter 1 DC Current (A)`` → boosts ``device_id`` + ``icr_id``
    so inverter measurements light at upload suggestion time without waiting for melt.
    SCB-tagged headers (``… INV1 SCB1 O/P Current``) boost ``scb_id``.
    """
    boosts: set[str] = set()
    for col in column_names or []:
        parsed = parse_wide_device_column(str(col))
        if parsed is None or not parsed.equipment_id:
            continue
        level = derive_level(parsed.equipment_id)
        companion = _WIDE_LEVEL_TO_COMPANION.get(level or "")
        if companion:
            boosts.add(companion)
        if parsed.icr_id:
            boosts.add("icr_id")
        # Parent inverter is implied when SCB/string columns carry INV tokens.
        if level in {"scb", "string"} and parsed.inverter_num:
            boosts.add("device_id")
    return boosts


def architecture_counts_from_wide_columns(
    column_names: Iterable[str] | None,
) -> tuple[int, int, int, list[str]]:
    """Count unique INV/SCB/string ids encoded in wide column headers."""
    invs: set[str] = set()
    scbs: set[str] = set()
    strings: set[str] = set()
    icrs: set[str] = set()
    for col in column_names or []:
        parsed = parse_wide_device_column(str(col))
        if parsed is None or not parsed.equipment_id:
            continue
        level = derive_level(parsed.equipment_id)
        if level == "inverter":
            invs.add(parsed.equipment_id)
        elif level == "scb":
            scbs.add(parsed.equipment_id)
        elif level == "string":
            strings.add(parsed.equipment_id)
        if parsed.icr_id:
            icrs.add(parsed.icr_id)
    notes: list[str] = []
    if invs or scbs or strings:
        parts = []
        if invs:
            parts.append(f"{len(invs)} inverter(s)")
        if scbs:
            parts.append(f"{len(scbs)} SCB(s)")
        if strings:
            parts.append(f"{len(strings)} string(s)")
        if icrs:
            parts.append(f"{len(icrs)} ICR(s)")
        notes.append("From wide column headers: " + ", ".join(parts) + ".")
    return len(invs), len(scbs), len(strings), notes


def _measurement_in_play_at_level(
    field_id: str,
    level_id: str,
    fields: set[str],
    typed: Mapping[str, set[str]] | None,
) -> bool:
    """Whether a measurement may be credited at this hierarchy level.

    Evidence ladder (without claiming cross-level presence):
    - confirmed device_type rows (handled by caller), or
    - companion level ID present — including wide-header boosts (mapped_level_tbd), or
    - plant-native weather fields, or
    - plant AC/DC only when plant/WMS typed OR no equipment IDs (aggregate file).
    """
    # When device_type partitions are known (e.g. post-SCB melt), do not light
    # inverter metrics from a shared device_id companion alone.
    if typed:
        dtypes = _LEVEL_DEVICE_TYPES.get(level_id, ())
        if dtypes and not any(typed.get(d) for d in dtypes):
            if level_id == "plant_wms":
                pass  # plant rules below
            else:
                return False

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
    column_names: Iterable[str] | None = None,
    reshape_report: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Per-hierarchy signal matrix from detected canonical fields.

    A measurement is present at a level only when that level is in play
    (companion ID, wide-header provenance, or confirmed ``device_type``), not merely
    because the same canonical column exists on another level. ``mapped_level_tbd``
    is used when a level is implied but device_type is not yet confirmed.

    Optional levels (ICR) are omitted when none of their signals are present.
    """
    fields = {str(f) for f in present if f}
    wide_boosts = companion_boosts_from_wide_columns(column_names)
    reshape_boosts = companion_boosts_from_reshape(reshape_report)
    play_fields = fields | wide_boosts | reshape_boosts
    typed = _normalize_by_device_type(by_device_type)
    # After SCB melt without typed partitions, credit measurements on SCB from reshape.
    if not typed and reshape_report and int(reshape_report.get("scb_count") or 0) > 0:
        if "device_id" in play_fields or "scb_id" in play_fields:
            typed = {"scb": set(fields)}
    levels: list[dict[str, Any]] = []
    for level_id, title, signals in _HIERARCHY_LEVELS:
        items: list[dict[str, Any]] = []
        for field_id, label, alts, kind in signals:
            ok, via = _field_present(field_id, alts, fields)
            ok_play, via_play = _field_present(field_id, alts, play_fields)
            confirmed_via = _confirmed_at_level(field_id, alts, level_id, typed)
            if confirmed_via:
                evidence = _EVIDENCE_CONFIRMED
                present_flag = True
                via = confirmed_via
            elif kind == "identity" and ok:
                evidence = _EVIDENCE_CONFIRMED
                present_flag = True
            elif kind == "identity" and ok_play and not ok:
                # Wide-header / reshape implied identity (e.g. SCB melt → scb_id)
                evidence = _EVIDENCE_MAPPED_TBD
                present_flag = True
                via = via_play or "wide_header"
            elif kind == "measurement" and ok and _measurement_in_play_at_level(
                field_id, level_id, play_fields, typed
            ):
                # Level companion / wide provenance / plant-native without device_type yet
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
    reshape_report: Mapping[str, Any] | None = None,
    column_names: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Architecture snapshot for Upload review — pack import preferred, else CSV / wide headers."""
    plant = plant_config or {}
    inv_n, scb_n, str_n = _counts_from_plant_architecture(plant)
    notes: list[str] = []
    source = "not_detected"
    detected = False
    cols = list(column_names) if column_names is not None else _column_names_from_suggestions(suggestions)

    if scb_n > 0 or inv_n > 0:
        detected = True
        source = "pack_import" if plant.get("architecture_imported") else "saved_config"
        notes.append(
            f"From plant configuration: {inv_n} inverter(s), {scb_n} SCB(s)"
            + (f", {str_n} string slot(s)" if str_n else "")
            + "."
        )
    elif reshape_report and reshape_report.get("reshaped"):
        invs = list(reshape_report.get("inverters_found") or [])
        scbs_from_report = list(reshape_report.get("scb_ids") or [])
        inv_n = int(reshape_report.get("inverter_count") or 0) or len(invs)
        scb_n = int(reshape_report.get("scb_count") or 0) or len(scbs_from_report)
        str_n = int(reshape_report.get("string_count") or 0)
        # Classify equipment ids when older reshape reports lack scb_count.
        if scb_n == 0 and invs:
            from analytics.common.equipment_ids import derive_level as _derive

            scb_ids = [e for e in invs if _derive(e) == "scb"]
            inv_ids = [e for e in invs if _derive(e) == "inverter"]
            if scb_ids:
                scb_n = len(scb_ids)
                if not inv_ids:
                    # Parent inverters implied by SCB ids
                    from analytics.common.equipment_ids import extract_parent_inverter as _parent

                    parents = {p for e in scb_ids if (p := _parent(e))}
                    inv_n = len(parents) or inv_n
                else:
                    inv_n = len(inv_ids)
        if inv_n > 0 or scb_n > 0:
            detected = True
            source = "wide_reshape"
            icr_n = len(reshape_report.get("icr_ids") or [])
            notes.append(
                f"From wide reshape: {inv_n} inverter(s)"
                + (f", {scb_n} SCB(s)" if scb_n else "")
                + (f", {icr_n} ICR(s)" if icr_n else "")
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

    if not detected:
        w_inv, w_scb, w_str, w_notes = architecture_counts_from_wide_columns(cols)
        if w_inv > 0 or w_scb > 0 or w_str > 0:
            detected = True
            source = "wide_headers"
            inv_n, scb_n, str_n = w_inv, w_scb, w_str
            notes = list(w_notes)

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
    column_names: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Rebuild per-file hierarchy matrix from signals_present + wide column provenance."""
    cols = list(column_names) if column_names is not None else list(item.get("column_names") or [])
    present = item.get("signals_present") or []
    item["hierarchy_levels"] = build_hierarchy_levels(
        present, by_device_type=by_device_type, column_names=cols or None
    )
    return item


def build_upload_intelligence(
    *,
    suggestions: Iterable[Any],
    plant_config: Mapping[str, Any] | None,
    csv_path: Path | None,
    file_inventory: list[dict[str, Any]] | None = None,
    by_device_type: Mapping[str, Iterable[str]] | None = None,
    reshape_report: Mapping[str, Any] | None = None,
    column_names: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Job-level upload intelligence bundle for API responses."""
    sug_list = list(suggestions)
    present = _present_from_suggestions(sug_list)
    cols = list(column_names) if column_names is not None else _column_names_from_suggestions(sug_list)
    typed = by_device_type
    if typed is None:
        typed = infer_by_device_type_from_csv(csv_path)
    # Ensure plant/WMS weather fields from typed partitions count as present for chips.
    if typed:
        for dtype in ("plant", "wms"):
            for field in typed.get(dtype) or ():
                if field and field != "ignore":
                    present.add(str(field))
        if "poa_w_m2" in present or "ghi_w_m2" in present:
            present.add("poa_w_m2")
            present.add("ghi_w_m2")
    arch = build_architecture_summary(
        plant_config=plant_config,
        csv_path=csv_path,
        suggestions=sug_list,
        reshape_report=reshape_report,
        column_names=cols,
    )
    impact = build_module_impact_preview(
        suggestions=sug_list,
        plant_config=plant_config,
        architecture_summary=arch,
    )
    inventory = [
        enrich_file_inventory_item(
            dict(f), by_device_type=typed, column_names=f.get("column_names")
        )
        for f in (file_inventory or [])
    ]
    return {
        "hierarchy_overview": build_hierarchy_levels(
            present,
            by_device_type=typed,
            column_names=cols,
            reshape_report=reshape_report,
        ),
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
