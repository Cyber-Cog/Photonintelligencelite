"""Plant / architecture capacity consistency checks (OI-inspired).

Ports Operation Intelligence's ±5% AC/DC reconciliation and adds PIC Lite-specific
checks between architecture-pack nameplates, per-inverter ``equipment_ratings``,
and Setup plant-detail fields (e.g. Excel 90 kW vs plant default 100 kW).

Issues are returned as ``ValidationIssue`` so they surface on the Validation page
alongside SCADA data-quality warnings. Capacity drift is high-severity *warning*
(does not block analysis) — matching OI's activation policy — except hierarchy
gaps that make fault modules unusable (those block).
"""
from __future__ import annotations

from typing import Any, Optional

from analytics.preprocessing.validation import ValidationIssue

# Mirrors OI ``CAPACITY_TOLERANCE_PCT`` in plant_array_config.py.
CAPACITY_TOLERANCE_PCT = 5.0
# Absolute band for float noise when comparing individual inverter ratings (kW).
RATING_ABS_TOLERANCE_KW = 0.5


def _f(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if out != out:  # NaN
        return None
    return out


def _pct_drift(calculated: float, declared: float) -> float:
    if declared == 0:
        return 0.0 if calculated == 0 else 100.0
    return abs(calculated - declared) / abs(declared) * 100.0


def _ratings_differ(a: float, b: float) -> bool:
    return abs(a - b) > RATING_ABS_TOLERANCE_KW


def _warning(
    code: str,
    message: str,
    *,
    likely_cause: str,
    remediation: str,
    affected_columns: Optional[list[str]] = None,
) -> ValidationIssue:
    return ValidationIssue(
        code=code,
        severity="warning",
        message=message,
        likely_cause=likely_cause,
        blocks_analysis=False,
        affected_columns=list(affected_columns or []),
        remediation=remediation,
    )


def _blocker(
    code: str,
    message: str,
    *,
    likely_cause: str,
    remediation: str,
    affected_columns: Optional[list[str]] = None,
) -> ValidationIssue:
    return ValidationIssue(
        code=code,
        severity="blocker",
        message=message,
        likely_cause=likely_cause,
        blocks_analysis=True,
        affected_columns=list(affected_columns or []),
        remediation=remediation,
    )


def _architecture_inverter_ids(architecture: dict[str, Any]) -> set[str]:
    ids: set[str] = set()
    for entry in architecture.values():
        if not isinstance(entry, dict):
            continue
        inv = str(entry.get("inverter_id") or "").strip()
        if inv:
            ids.add(inv)
    return ids


def _sum_architecture_dc_kwp(architecture: dict[str, Any]) -> Optional[float]:
    total = 0.0
    found = False
    for entry in architecture.values():
        if not isinstance(entry, dict):
            continue
        dc = _f(entry.get("dc_capacity_kwp"))
        if dc is not None and dc > 0:
            total += dc
            found = True
    return total if found else None


def check_plant_config_consistency(plant: dict[str, Any]) -> list[ValidationIssue]:
    """Return consistency issues for a plant_config ``plant`` dict (job storage shape)."""
    issues: list[ValidationIssue] = []
    if not isinstance(plant, dict):
        return issues

    architecture = plant.get("architecture") or {}
    if not isinstance(architecture, dict):
        architecture = {}
    ratings_raw = plant.get("equipment_ratings") or {}
    if not isinstance(ratings_raw, dict):
        ratings_raw = {}
    equipment_ratings = {
        str(k).strip(): v
        for k, v in ((str(k), _f(v)) for k, v in ratings_raw.items())
        if k.strip() and v is not None and v > 0
    }

    plant_default = _f(plant.get("inverter_capacity_kw"))
    ac_mw = _f(plant.get("ac_capacity_mw"))
    dc_mwp = _f(plant.get("dc_capacity_mwp"))

    imported_ratings_raw = plant.get("imported_equipment_ratings") or {}
    if not isinstance(imported_ratings_raw, dict):
        imported_ratings_raw = {}
    imported_ratings = {
        str(k).strip(): v
        for k, v in ((str(k), _f(v)) for k, v in imported_ratings_raw.items())
        if k.strip() and v is not None and v > 0
    }
    imported_default = _f(plant.get("imported_inverter_capacity_kw"))
    imported_ac_mw = _f(plant.get("imported_ac_capacity_mw"))
    imported_dc_mwp = _f(plant.get("imported_dc_capacity_mwp"))

    # --- Hierarchy completeness ---
    # Empty architecture is a warning (plant KPIs can still run); partial/broken hierarchy blocks.
    if not architecture:
        issues.append(
            _warning(
                "architecture_missing",
                "Plant architecture is empty. Fault modules that need SMB/SCB hierarchy (disconnected strings, "
                "module damage, current clipping) cannot run.",
                likely_cause="Architecture was never imported or was cleared before Continue.",
                remediation="On Setup → Architecture, upload the pack/Excel hierarchy, re-detect from Device IDs, or apply an SMB pattern.",
                affected_columns=["architecture"],
            )
        )
    else:
        orphan_scbs = [
            scb_id
            for scb_id, entry in architecture.items()
            if isinstance(entry, dict) and not str(entry.get("inverter_id") or "").strip()
        ]
        if orphan_scbs:
            sample = ", ".join(orphan_scbs[:5])
            more = f" (+{len(orphan_scbs) - 5} more)" if len(orphan_scbs) > 5 else ""
            issues.append(
                _blocker(
                    "architecture_scb_missing_inverter",
                    f"{len(orphan_scbs)} SCB/SMB row(s) have no parent inverter_id (e.g. {sample}{more}).",
                    likely_cause="Incomplete architecture sheet or manual edit dropped the inverter link.",
                    remediation="Fix architecture Excel (SCB parent_id → inverter) or edit the equipment tree on Setup → Architecture.",
                    affected_columns=["architecture"],
                )
            )

        inv_ids = _architecture_inverter_ids(architecture)
        unrated = sorted(inv for inv in inv_ids if inv not in equipment_ratings)
        if unrated and not (plant_default and plant_default > 0):
            sample = ", ".join(unrated[:5])
            more = f" (+{len(unrated) - 5} more)" if len(unrated) > 5 else ""
            issues.append(
                _blocker(
                    "inverter_rating_missing",
                    f"{len(unrated)} inverter(s) have no AC rating and no plant default (e.g. {sample}{more}).",
                    likely_cause="Architecture lists inverters without equipment_ratings and plant default is unset.",
                    remediation="Enter Default inverter rating (kW) on Setup → Plant, or set per-inverter ratings on Architecture.",
                    affected_columns=["inverter_capacity_kw"],
                )
            )
        elif unrated and plant_default and plant_default > 0:
            sample = ", ".join(unrated[:5])
            more = f" (+{len(unrated) - 5} more)" if len(unrated) > 5 else ""
            issues.append(
                _warning(
                    "inverter_rating_uses_plant_default",
                    f"{len(unrated)} inverter(s) have no per-unit rating and will use the plant default "
                    f"{plant_default:g} kW (e.g. {sample}{more}).",
                    likely_cause="Mixed or incomplete equipment_ratings after architecture import.",
                    remediation="Confirm the plant default matches nameplate, or set each inverter rating on Architecture.",
                    affected_columns=["inverter_capacity_kw", "architecture"],
                )
            )

    # --- Plant default vs per-inverter ratings (Excel 90 vs UI 100) ---
    if plant_default and plant_default > 0 and equipment_ratings:
        mismatched = [
            (inv, kw) for inv, kw in sorted(equipment_ratings.items()) if _ratings_differ(kw, plant_default)
        ]
        if mismatched:
            sample = ", ".join(f"{inv}={kw:g} kW" for inv, kw in mismatched[:4])
            more = f" (+{len(mismatched) - 4} more)" if len(mismatched) > 4 else ""
            issues.append(
                _warning(
                    "inverter_rating_mismatch",
                    f"Default inverter rating is {plant_default:g} kW but architecture/equipment ratings differ "
                    f"({sample}{more}). Clipping and loss algorithms prefer per-inverter ratings when present.",
                    likely_cause="Plant details were edited after architecture/pack import without applying the new rating to all inverters (or vice versa).",
                    remediation="Align values: set Default inverter rating to match architecture, or use “Apply default rating to all” on Architecture, then Continue.",
                    affected_columns=["inverter_capacity_kw", "architecture"],
                )
            )

    # --- Imported pack/Excel nameplate vs current Setup values ---
    if imported_ratings or (imported_default and imported_default > 0):
        # Compare plant default to imported default / typical imported rating
        ref_default = imported_default
        if ref_default is None and imported_ratings:
            ref_default = max(imported_ratings.values())
        if (
            plant_default
            and plant_default > 0
            and ref_default
            and ref_default > 0
            and _ratings_differ(plant_default, ref_default)
        ):
            issues.append(
                _warning(
                    "imported_inverter_rating_mismatch",
                    f"Architecture pack/Excel inverter rating was {ref_default:g} kW but Plant details "
                    f"default is now {plant_default:g} kW.",
                    likely_cause="Plant default was changed after Complete Analysis Pack or architecture Excel import.",
                    remediation="Restore the pack rating, or intentionally override and apply the new rating to every inverter so analysis matches Plant details.",
                    affected_columns=["inverter_capacity_kw"],
                )
            )

        for inv, imported_kw in sorted(imported_ratings.items()):
            current = equipment_ratings.get(inv)
            if current is not None and _ratings_differ(current, imported_kw):
                issues.append(
                    _warning(
                        "imported_equipment_rating_mismatch",
                        f"Inverter {inv}: architecture pack/Excel said {imported_kw:g} kW but Setup now has {current:g} kW.",
                        likely_cause="Per-inverter rating was overwritten after import (e.g. Apply default rating to all).",
                        remediation="Confirm which nameplate is correct, then re-import architecture or edit the inverter rating on Architecture.",
                        affected_columns=["architecture"],
                    )
                )
                # One sample issue is enough when many inverters share the same overwrite
                if len(imported_ratings) > 3:
                    remaining = sum(
                        1
                        for other, ikw in imported_ratings.items()
                        if other != inv
                        and (equipment_ratings.get(other) is not None)
                        and _ratings_differ(equipment_ratings[other], ikw)
                    )
                    if remaining:
                        issues.append(
                            _warning(
                                "imported_equipment_rating_mismatch_bulk",
                                f"{remaining} additional inverter(s) also differ from imported architecture ratings.",
                                likely_cause="Bulk apply of a different plant default after pack import.",
                                remediation="Re-import architecture or systematically align all inverter ratings with the intended nameplate.",
                                affected_columns=["architecture"],
                            )
                        )
                    break

    if imported_ac_mw and imported_ac_mw > 0 and ac_mw and ac_mw > 0:
        if _pct_drift(ac_mw, imported_ac_mw) > CAPACITY_TOLERANCE_PCT:
            issues.append(
                _warning(
                    "imported_ac_capacity_mismatch",
                    f"Plant AC capacity is {ac_mw:g} MW but architecture pack/Excel had {imported_ac_mw:g} MW "
                    f"(>{CAPACITY_TOLERANCE_PCT:g}% drift).",
                    likely_cause="Plant AC was edited after pack import.",
                    remediation="Align Plant AC (MW) with the architecture plant row, or re-import the pack.",
                    affected_columns=["ac_capacity_mw"],
                )
            )

    if imported_dc_mwp and imported_dc_mwp > 0 and dc_mwp and dc_mwp > 0:
        if _pct_drift(dc_mwp, imported_dc_mwp) > CAPACITY_TOLERANCE_PCT:
            issues.append(
                _warning(
                    "imported_dc_capacity_mismatch",
                    f"Plant DC capacity is {dc_mwp:g} MWp but architecture pack/Excel had {imported_dc_mwp:g} MWp "
                    f"(>{CAPACITY_TOLERANCE_PCT:g}% drift).",
                    likely_cause="Plant DC was edited after pack import.",
                    remediation="Align Plant DC (MWp) with the architecture plant row, or re-import the pack.",
                    affected_columns=["dc_capacity_mwp"],
                )
            )

    # --- Summed inverter AC vs plant AC (±5%, OI ac_capacity_mismatch) ---
    if equipment_ratings and ac_mw and ac_mw > 0:
        summed_ac_kw = sum(equipment_ratings.values())
        # If some architecture inverters lack ratings, fill with plant default for the total check
        inv_ids = _architecture_inverter_ids(architecture)
        for inv in inv_ids:
            if inv not in equipment_ratings and plant_default and plant_default > 0:
                summed_ac_kw += plant_default
        declared_ac_kw = ac_mw * 1000.0
        drift = _pct_drift(summed_ac_kw, declared_ac_kw)
        if drift > CAPACITY_TOLERANCE_PCT:
            issues.append(
                _warning(
                    "ac_capacity_mismatch",
                    f"Summed inverter AC capacity {summed_ac_kw:.1f} kW differs from declared plant AC "
                    f"{declared_ac_kw:.1f} kW by more than {CAPACITY_TOLERANCE_PCT:g}%.",
                    likely_cause="Plant AC (MW) does not match architecture inverter ratings × count.",
                    remediation="Update Plant AC capacity or correct per-inverter ratings so totals agree within ±5%.",
                    affected_columns=["ac_capacity_mw", "architecture"],
                )
            )

    # --- Architecture SCB DC nameplates vs plant DC (±5%, OI dc_capacity_mismatch) ---
    arch_dc = _sum_architecture_dc_kwp(architecture)
    if arch_dc is not None and dc_mwp and dc_mwp > 0:
        declared_dc_kwp = dc_mwp * 1000.0
        drift = _pct_drift(arch_dc, declared_dc_kwp)
        if drift > CAPACITY_TOLERANCE_PCT:
            issues.append(
                _warning(
                    "dc_capacity_mismatch",
                    f"Summed architecture DC capacity {arch_dc:.1f} kWp differs from declared plant DC "
                    f"{declared_dc_kwp:.1f} kWp by more than {CAPACITY_TOLERANCE_PCT:g}%.",
                    likely_cause="Plant DC (MWp) does not match SCB/inverter DC nameplates from the architecture sheet.",
                    remediation="Update Plant DC capacity or fix architecture dc_capacity_kwp values so totals agree within ±5%.",
                    affected_columns=["dc_capacity_mwp", "architecture"],
                )
            )

    return issues


def snapshot_imported_nameplate(plant_or_draft: dict[str, Any]) -> dict[str, Any]:
    """Build imported_* fields from a pack/Excel draft for later reconciliation."""
    out: dict[str, Any] = {}
    ratings = plant_or_draft.get("equipment_ratings") or {}
    if isinstance(ratings, dict) and ratings:
        cleaned = {
            str(k).strip(): float(v)
            for k, v in ratings.items()
            if str(k).strip() and _f(v) is not None and _f(v) > 0
        }
        if cleaned:
            out["imported_equipment_ratings"] = cleaned
    inv = _f(plant_or_draft.get("inverter_capacity_kw"))
    if inv and inv > 0:
        out["imported_inverter_capacity_kw"] = inv
    elif out.get("imported_equipment_ratings"):
        out["imported_inverter_capacity_kw"] = max(out["imported_equipment_ratings"].values())
    ac = _f(plant_or_draft.get("ac_capacity_mw"))
    if ac and ac > 0:
        out["imported_ac_capacity_mw"] = ac
    dc = _f(plant_or_draft.get("dc_capacity_mwp"))
    if dc and dc > 0:
        out["imported_dc_capacity_mwp"] = dc
    return out


# Keys preserved across Setup Continue when the client does not resubmit them.
IMPORTED_NAMEPLATE_KEYS = (
    "imported_equipment_ratings",
    "imported_inverter_capacity_kw",
    "imported_ac_capacity_mw",
    "imported_dc_capacity_mwp",
    "architecture_imported",
    "architecture_format",
)
