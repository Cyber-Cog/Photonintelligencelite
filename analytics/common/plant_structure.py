"""Infer inverter → SCB → string plant architecture from SCADA equipment IDs.

Used during onboarding so the Setup UI can show a compact, editable structure instead of
asking for plant-wide-only guesses. Algorithms already consume ``equipment_ratings`` and
``architecture`` on ``PlantConfig``; this module only *discovers* candidates from data.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional

import pandas as pd

from analytics.common.equipment_ids import (
    _as_clean_id,
    derive_level,
    extract_parent_inverter,
    extract_parent_scb,
)

# Hierarchy keys we can pull from a mapped CSV without full standardization.
_HIERARCHY_CANONICALS = ("device_id", "inverter_id", "scb_id", "string_id")


@dataclass
class ScbNode:
    scb_id: str
    strings_per_scb: Optional[int] = None
    strings_detected: bool = False
    string_ids: set[str] = field(default_factory=set)


@dataclass
class InverterNode:
    inverter_id: str
    scbs: dict[str, ScbNode] = field(default_factory=dict)


@dataclass
class DetectedStructure:
    inverters: dict[str, InverterNode] = field(default_factory=dict)
    unique_id_count: int = 0
    source: Optional[str] = None
    notes: list[str] = field(default_factory=list)

    @property
    def detected(self) -> bool:
        return bool(self.inverters)

    def to_api_dict(self) -> dict:
        inv_list = []
        for inv_id in sorted(self.inverters):
            inv = self.inverters[inv_id]
            scbs = []
            for scb_id in sorted(inv.scbs):
                scb = inv.scbs[scb_id]
                scbs.append(
                    {
                        "scb_id": scb.scb_id,
                        "strings_per_scb": scb.strings_per_scb,
                        "strings_detected": scb.strings_detected,
                    }
                )
            inv_list.append({"inverter_id": inv_id, "scbs": scbs})
        return {
            "detected": self.detected,
            "source": self.source,
            "unique_id_count": self.unique_id_count,
            "inverters": inv_list,
            "notes": list(self.notes),
        }

    def to_architecture(self, modules_per_string: Optional[int] = None) -> dict[str, dict]:
        """Build PlantConfig.architecture; omit string count when unknown (algorithms fall back)."""
        arch: dict[str, dict] = {}
        for inv in self.inverters.values():
            for scb in inv.scbs.values():
                entry: dict = {"inverter_id": inv.inverter_id}
                if scb.strings_per_scb is not None:
                    entry["strings_per_scb"] = scb.strings_per_scb
                if modules_per_string is not None:
                    entry["modules_per_string"] = modules_per_string
                arch[scb.scb_id] = entry
        return arch


def _ensure_inverter(structure: DetectedStructure, inverter_id: str) -> InverterNode:
    node = structure.inverters.get(inverter_id)
    if node is None:
        node = InverterNode(inverter_id=inverter_id)
        structure.inverters[inverter_id] = node
    return node


def _ensure_scb(inv: InverterNode, scb_id: str) -> ScbNode:
    node = inv.scbs.get(scb_id)
    if node is None:
        node = ScbNode(scb_id=scb_id)
        inv.scbs[scb_id] = node
    return node


def ingest_equipment_id(structure: DetectedStructure, equipment_id) -> None:
    """Fold one equipment ID into the hierarchy (INV / SCB / STR)."""
    eid = _as_clean_id(equipment_id)
    if eid is None:
        return
    level = derive_level(eid)
    if level == "string":
        scb_id = extract_parent_scb(eid)
        inv_id = extract_parent_inverter(scb_id or eid)
        if not inv_id or not scb_id:
            return
        scb = _ensure_scb(_ensure_inverter(structure, inv_id), scb_id)
        scb.string_ids.add(eid)
    elif level == "scb":
        inv_id = extract_parent_inverter(eid)
        if not inv_id:
            return
        _ensure_scb(_ensure_inverter(structure, inv_id), eid)
    elif level == "inverter":
        _ensure_inverter(structure, eid)


def finalize_string_counts(structure: DetectedStructure) -> None:
    for inv in structure.inverters.values():
        for scb in inv.scbs.values():
            if scb.string_ids:
                scb.strings_per_scb = len(scb.string_ids)
                scb.strings_detected = True


def infer_from_ids(ids: Iterable) -> DetectedStructure:
    structure = DetectedStructure(source="equipment_ids")
    seen: set[str] = set()
    for raw in ids:
        eid = _as_clean_id(raw)
        if eid is None or eid in seen:
            continue
        seen.add(eid)
        ingest_equipment_id(structure, eid)
    structure.unique_id_count = len(seen)
    finalize_string_counts(structure)
    if structure.detected:
        n_inv = len(structure.inverters)
        n_scb = sum(len(i.scbs) for i in structure.inverters.values())
        n_str = sum(1 for i in structure.inverters.values() for s in i.scbs.values() if s.strings_detected)
        structure.notes.append(
            f"Detected {n_inv} inverter(s), {n_scb} SCB(s)"
            + (f", string counts for {n_str} SCB(s) from IDs" if n_str else "")
            + "."
        )
    else:
        structure.notes.append(
            "Could not parse inverter/SCB hierarchy from equipment IDs. "
            "IDs must look like INV-01, INV-01-SCB-01, INV-01-SCB-01-STR-01 (or similar). "
            "Next: Excel template or pattern apply — do not enter thousands of rows in the web form."
        )
    return structure


def infer_from_hierarchy_columns(
    *,
    inverter_ids: Optional[Iterable] = None,
    scb_ids: Optional[Iterable] = None,
    string_ids: Optional[Iterable] = None,
) -> DetectedStructure:
    """Build structure when SCADA has separate inverter / SCB / string columns."""
    structure = DetectedStructure(source="hierarchy_columns")
    seen: set[str] = set()

    for raw in inverter_ids or ():
        eid = _as_clean_id(raw)
        if eid:
            seen.add(eid)
            _ensure_inverter(structure, eid)

    for raw in scb_ids or ():
        eid = _as_clean_id(raw)
        if not eid:
            continue
        seen.add(eid)
        inv_id = extract_parent_inverter(eid)
        if inv_id:
            _ensure_scb(_ensure_inverter(structure, inv_id), eid)
        else:
            # Orphan SCB without parseable parent — still track under a synthetic bucket
            # only if we already have that exact inverter listed separately; otherwise skip.
            pass

    for raw in string_ids or ():
        eid = _as_clean_id(raw)
        if not eid:
            continue
        seen.add(eid)
        scb_id = extract_parent_scb(eid)
        inv_id = extract_parent_inverter(scb_id or eid)
        if inv_id and scb_id:
            scb = _ensure_scb(_ensure_inverter(structure, inv_id), scb_id)
            scb.string_ids.add(eid)

    structure.unique_id_count = len(seen)
    finalize_string_counts(structure)
    if structure.detected:
        structure.notes.append(
            f"Built hierarchy from separate ID columns ({structure.unique_id_count} unique values)."
        )
    else:
        structure.notes.append("Separate ID columns did not yield a usable inverter/SCB tree.")
    return structure


def _mapped_source_columns(column_to_canonical: dict[str, str]) -> dict[str, str]:
    """canonical_field -> source column name (first wins)."""
    out: dict[str, str] = {}
    for src, canon in column_to_canonical.items():
        if canon in _HIERARCHY_CANONICALS and canon not in out and canon != "ignore":
            out[canon] = src
    return out


def infer_from_csv(
    csv_path: Path,
    column_to_canonical: dict[str, str],
    *,
    max_unique_scan_rows: int = 500_000,
) -> DetectedStructure:
    """Peek at mapped hierarchy columns in the uploaded CSV and infer equipment structure."""
    mapped = _mapped_source_columns(column_to_canonical)
    if not mapped:
        empty = DetectedStructure()
        empty.notes.append(
            "Structure not detected: no Device ID / Inverter ID / SCB ID / String ID column is mapped. "
            "Next: on Setup, map an equipment ID column, then click Re-detect — "
            "or download the Excel architecture template / apply an SMB pattern."
        )
        return empty

    usecols = list(dict.fromkeys(mapped.values()))
    try:
        df = pd.read_csv(csv_path, usecols=usecols, nrows=max_unique_scan_rows, dtype=str)
    except Exception as exc:  # noqa: BLE001
        empty = DetectedStructure()
        empty.notes.append(
            f"Structure not detected: could not read mapped equipment columns ({exc}). "
            "Next: confirm the upload is a long/tidy CSV (wide INVERTER REPORT Excel should auto-melt on upload), "
            "or enter architecture via Excel template."
        )
        return empty

    # Rename source → canonical for easier branching
    rename = {src: canon for canon, src in mapped.items()}
    df = df.rename(columns=rename)

    if "device_id" in df.columns:
        structure = infer_from_ids(df["device_id"].tolist())
        structure.source = "device_id"
        if not structure.detected:
            n_unique = structure.unique_id_count
            structure.notes = [
                f"Structure not detected from {n_unique} unique Device ID value(s). "
                "IDs did not match INV…/SCB…/STR… naming that PIC Lite can parse. "
                "Next: download the Excel template and fill inverter_id / scb_id / strings_per_scb, "
                "or use pattern apply (N SMBs × M strings) then edit exceptions in Excel."
            ]
        return structure

    structure = infer_from_hierarchy_columns(
        inverter_ids=df["inverter_id"].tolist() if "inverter_id" in df.columns else None,
        scb_ids=df["scb_id"].tolist() if "scb_id" in df.columns else None,
        string_ids=df["string_id"].tolist() if "string_id" in df.columns else None,
    )
    if not structure.detected:
        mapped_cols = ", ".join(sorted(mapped.keys()))
        structure.notes = [
            f"Structure not detected from hierarchy columns ({mapped_cols}). "
            "Mapped ID columns were empty or could not be linked (SCB needs a parseable parent inverter). "
            "Next: use Excel template upload or pattern apply."
        ]
    return structure


def normalize_plant_type(plant_type: str) -> str:
    """Map UI / alias values onto keys used in analytics/config/defaults.yaml."""
    key = (plant_type or "fixed_tilt").strip().lower().replace("-", "_").replace(" ", "_")
    if key in {"tracker", "single_axis_tracker", "single_axis", "sat"}:
        return "tracker"
    return "fixed_tilt" if key in {"fixed_tilt", "fixed", "fixedtilt"} else plant_type
