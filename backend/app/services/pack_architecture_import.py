"""Import plant architecture from Complete Analysis Pack / multi-sheet uploads."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from analytics.common.architecture_excel import try_parse_architecture_from_pack
from analytics.common.plant_config_consistency import snapshot_imported_nameplate

# Sensible Setup defaults when pack provides hierarchy but not module/timezone metadata.
_PACK_PLANT_DEFAULTS: dict = {
    "module_rating_wp": 545.0,
    "module_technology": "Mono PERC",
    "bifacial": False,
    "timezone": "Asia/Kolkata",
    "plant_type": "fixed_tilt",
    "tariff_inr_per_kwh": None,
    "pr_benchmark_pct": None,
}


def plant_config_from_architecture_file(path: Path) -> Optional[dict]:
    """Parse architecture from an xlsx path; return plant_config draft or None."""
    try:
        parsed = try_parse_architecture_from_pack(path)
    except Exception:  # noqa: BLE001
        return None
    if parsed is None or not parsed.ok:
        return None
    draft = {**_PACK_PLANT_DEFAULTS, **parsed.to_plant_config_draft()}
    if not draft.get("plant_name"):
        draft["plant_name"] = "Imported from Complete Analysis Pack"
    draft.update(snapshot_imported_nameplate(draft))
    return draft


def merge_architecture_into_job_plant(
    existing: Optional[dict],
    imported: dict,
    *,
    overwrite_architecture: bool = True,
) -> dict:
    """Merge pack-imported architecture into existing plant_config_json wrapper.

    ``existing`` is the full ``job.plant_config_json`` (``{plant, threshold_overrides}``)
    or None. Returns a full plant_config_json dict.
    """
    base_plant: dict = {}
    thresholds: dict = {}
    if existing:
        base_plant = dict(existing.get("plant") or {})
        thresholds = dict(existing.get("threshold_overrides") or {})

    plant = dict(base_plant)
    # Always take pack architecture/ratings when overwrite; fill empty plant capacities.
    if overwrite_architecture or not plant.get("architecture"):
        plant["architecture"] = imported.get("architecture") or {}
        plant["equipment_ratings"] = imported.get("equipment_ratings") or {}
        plant["architecture_imported"] = True
        if imported.get("architecture_format"):
            plant["architecture_format"] = imported["architecture_format"]
        if imported.get("strings_per_scb") is not None:
            plant["strings_per_scb"] = imported["strings_per_scb"]
        if imported.get("inverter_capacity_kw"):
            plant["inverter_capacity_kw"] = imported["inverter_capacity_kw"]
        # Freeze pack nameplates for later Setup vs Excel consistency checks.
        plant.update(snapshot_imported_nameplate(imported))

    for key in (
        "plant_name",
        "ac_capacity_mw",
        "dc_capacity_mwp",
        "module_rating_wp",
        "module_technology",
        "bifacial",
        "timezone",
        "plant_type",
        "tariff_inr_per_kwh",
        "pr_benchmark_pct",
    ):
        if key not in plant or plant[key] in (None, "", 0, 0.0):
            if imported.get(key) not in (None, "", 0, 0.0):
                plant[key] = imported[key]
            elif key in _PACK_PLANT_DEFAULTS and key not in plant:
                plant[key] = _PACK_PLANT_DEFAULTS[key]

    return {"plant": plant, "threshold_overrides": thresholds}
