"""Plant architecture Excel template (download) and parser (upload).

Supports two sheet layouts:

1. **Flat** (Setup Method A / large plants) — one row per SCB:
   ``inverter_id, inverter_rated_kw, scb_id, strings_per_scb, notes``

2. **Hierarchy** (Complete Analysis Pack) — Plant → Inverter → SCB → String:
   ``id, parent_id, device_type, ac_capacity_kw, dc_capacity_kwp, strings_per_scb, notes``

Plant AC/DC on the hierarchy sheet use **kW / kWp**; PlantConfig stores **MW / MWp**
(÷ 1000). Inverter AC ratings land in ``equipment_ratings`` (kW).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
from typing import BinaryIO, Optional, Union

from openpyxl import Workbook, load_workbook

TEMPLATE_COLUMNS = (
    "inverter_id",
    "inverter_rated_kw",
    "scb_id",
    "strings_per_scb",
    "notes",
)

# Official hierarchy layout for Complete Analysis Pack (and multi-sheet uploads).
HIERARCHY_COLUMNS = (
    "id",
    "parent_id",
    "device_type",
    "ac_capacity_kw",
    "dc_capacity_kwp",
    "strings_per_scb",
    "notes",
)

TEMPLATE_FILENAME = "pic_lite_plant_architecture_template.xlsx"

_DEVICE_TYPE_ALIASES = {
    "plant": "plant",
    "site": "plant",
    "inverter": "inverter",
    "inv": "inverter",
    "scb": "scb",
    "smb": "scb",
    "combiner": "scb",
    "mppt": "scb",
    "string": "string",
    "str": "string",
}


@dataclass
class ArchitectureParseResult:
    equipment_ratings: dict[str, float] = field(default_factory=dict)
    architecture: dict[str, dict] = field(default_factory=dict)
    inverters: list[dict] = field(default_factory=list)
    """UI-shaped list: [{inverter_id, rated_kw, scbs:[{scb_id, strings_per_scb, strings_detected}]}]"""
    row_count: int = 0
    notes: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    # Plant-level capacities from hierarchy sheet (converted to MW / MWp).
    plant_name: Optional[str] = None
    ac_capacity_mw: Optional[float] = None
    dc_capacity_mwp: Optional[float] = None
    inverter_capacity_kw: Optional[float] = None
    strings_per_scb: Optional[int] = None
    format: Optional[str] = None  # "hierarchy" | "flat"
    source_sheet: Optional[str] = None

    @property
    def ok(self) -> bool:
        return bool(self.architecture) and not self.errors

    def to_plant_config_draft(self) -> dict:
        """Partial plant_config suitable for job.plant_config_json['plant'].

        Fills architecture + ratings + capacities when present. Callers merge with
        Setup defaults for module_technology / timezone / etc.
        """
        draft: dict = {
            "equipment_ratings": dict(self.equipment_ratings),
            "architecture": {
                scb_id: {
                    "inverter_id": entry["inverter_id"],
                    **(
                        {"strings_per_scb": entry["strings_per_scb"]}
                        if entry.get("strings_per_scb") is not None
                        else {}
                    ),
                    **(
                        {"modules_per_string": entry["modules_per_string"]}
                        if entry.get("modules_per_string") is not None
                        else {}
                    ),
                    **(
                        {"dc_capacity_kwp": entry["dc_capacity_kwp"]}
                        if entry.get("dc_capacity_kwp") is not None
                        else {}
                    ),
                }
                for scb_id, entry in self.architecture.items()
            },
            "architecture_imported": True,
            "architecture_format": self.format,
        }
        if self.plant_name:
            draft["plant_name"] = self.plant_name
        if self.ac_capacity_mw is not None and self.ac_capacity_mw > 0:
            draft["ac_capacity_mw"] = self.ac_capacity_mw
        if self.dc_capacity_mwp is not None and self.dc_capacity_mwp > 0:
            draft["dc_capacity_mwp"] = self.dc_capacity_mwp
        if self.inverter_capacity_kw is not None and self.inverter_capacity_kw > 0:
            draft["inverter_capacity_kw"] = self.inverter_capacity_kw
        elif self.equipment_ratings:
            draft["inverter_capacity_kw"] = max(self.equipment_ratings.values())
        if self.strings_per_scb is not None:
            draft["strings_per_scb"] = self.strings_per_scb
        return draft


def build_template_bytes(
    *,
    example_inverters: int = 2,
    scbs_per_inverter: int = 16,
    strings_per_scb: int = 24,
    default_rated_kw: float = 1500.0,
) -> bytes:
    """Return a filled example workbook engineers can overwrite for their plant."""
    wb = Workbook()
    ws = wb.active
    ws.title = "architecture"
    ws.append(list(TEMPLATE_COLUMNS))

    for inv_i in range(1, example_inverters + 1):
        inv_id = f"INV-{inv_i:02d}"
        for scb_i in range(1, scbs_per_inverter + 1):
            scb_id = f"{inv_id}-SCB-{scb_i:02d}"
            notes = "Example — replace with your plant IDs" if inv_i == 1 and scb_i == 1 else ""
            ws.append([inv_id, default_rated_kw, scb_id, strings_per_scb, notes])

    for col in ws.columns:
        ws.column_dimensions[col[0].column_letter].width = 22

    instr = wb.create_sheet("instructions", 0)
    instr["A1"] = "PIC Lite — Plant architecture template"
    instr["A3"] = "How to use (large plants)"
    instr["A4"] = "1. Keep the header row on the 'architecture' sheet exactly as provided."
    instr["A5"] = "2. One row per SMB/SCB. Repeat inverter_id and inverter_rated_kw on every SCB row for that inverter."
    instr["A6"] = "3. inverter_id / scb_id should match (or be mappable to) Device IDs in your SCADA export."
    instr["A7"] = "4. strings_per_scb = number of strings feeding that SMB (required for current-clipping / disconnected-string losses)."
    instr["A8"] = "5. Leave inverter_rated_kw blank only if you will use the plant-wide default rating in Setup."
    instr["A9"] = "6. Delete the example rows and paste your plant. Save as .xlsx and upload in Setup → Equipment structure."
    instr["A11"] = "Typical 300 MW plant: ~300 inverters × ~16 SMBs ≈ 4800 rows — Excel is the intended path."
    instr["A12"] = "After upload you can still apply pattern exceptions or re-download, edit offline, and upload again."
    instr["A14"] = "Hierarchy alternative (Complete Analysis Pack): columns id, parent_id, device_type,"
    instr["A15"] = "ac_capacity_kw, dc_capacity_kwp, strings_per_scb — Plant → Inverter → SCB → String."
    instr.column_dimensions["A"].width = 110

    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _cell(value) -> Optional[str]:
    if value is None:
        return None
    s = str(value).strip()
    return s if s else None


def _float_or_none(value) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        v = float(value)
        return v if v > 0 else None
    except (TypeError, ValueError):
        return None


def _int_or_none(value) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        v = int(float(value))
        return v if v >= 1 else None
    except (TypeError, ValueError):
        return None


def _normalize_header(value) -> str:
    return (_cell(value) or "").lower().replace(" ", "_").replace("-", "_")


def _normalize_device_type(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    key = value.strip().lower().replace(" ", "_").replace("-", "_")
    return _DEVICE_TYPE_ALIASES.get(key)


def _kw_to_mw(kw: Optional[float]) -> Optional[float]:
    if kw is None:
        return None
    return round(kw / 1000.0, 6)


def _detect_layout(col_idx: dict[str, int]) -> Optional[str]:
    if "id" in col_idx and "device_type" in col_idx:
        return "hierarchy"
    if "inverter_id" in col_idx and "scb_id" in col_idx:
        return "flat"
    return None


def _col(raw: tuple, col_idx: dict[str, int], name: str):
    i = col_idx.get(name)
    if i is None or i >= len(raw):
        return None
    return raw[i]


def _parse_flat(rows, col_idx: dict[str, int], result: ArchitectureParseResult) -> ArchitectureParseResult:
    inv_order: list[str] = []
    inv_map: dict[str, dict] = {}

    for raw in rows:
        if not raw or all(c is None or str(c).strip() == "" for c in raw):
            continue
        inv_id = _cell(_col(raw, col_idx, "inverter_id"))
        scb_id = _cell(_col(raw, col_idx, "scb_id"))
        if not inv_id or not scb_id:
            continue

        rated = _float_or_none(_col(raw, col_idx, "inverter_rated_kw"))
        strings = _int_or_none(_col(raw, col_idx, "strings_per_scb"))

        result.row_count += 1
        if inv_id not in inv_map:
            inv_order.append(inv_id)
            inv_map[inv_id] = {"inverter_id": inv_id, "rated_kw": rated, "scbs": {}}
        elif rated is not None and inv_map[inv_id]["rated_kw"] is None:
            inv_map[inv_id]["rated_kw"] = rated

        inv_map[inv_id]["scbs"][scb_id] = {
            "scb_id": scb_id,
            "strings_per_scb": strings,
            "strings_detected": False,
        }

        entry: dict = {"inverter_id": inv_id}
        if strings is not None:
            entry["strings_per_scb"] = strings
        result.architecture[scb_id] = entry
        if rated is not None:
            result.equipment_ratings[inv_id] = rated

    if not result.architecture:
        result.errors.append(
            "No valid architecture rows found. Each row needs inverter_id and scb_id."
        )
        return result

    for inv_id in inv_order:
        node = inv_map[inv_id]
        result.inverters.append(
            {
                "inverter_id": inv_id,
                "rated_kw": node["rated_kw"],
                "scbs": list(node["scbs"].values()),
            }
        )

    if result.equipment_ratings:
        result.inverter_capacity_kw = max(result.equipment_ratings.values())

    string_counts = [
        e["strings_per_scb"]
        for e in result.architecture.values()
        if e.get("strings_per_scb") is not None
    ]
    if string_counts:
        result.strings_per_scb = max(set(string_counts), key=string_counts.count)

    n_inv = len(result.inverters)
    n_scb = len(result.architecture)
    n_rated = len(result.equipment_ratings)
    result.notes.append(
        f"Loaded {n_inv} inverter(s), {n_scb} SMB/SCB(s) from {result.row_count} Excel row(s)"
        + (f"; ratings for {n_rated} inverter(s)." if n_rated else ".")
    )
    return result


def _parse_hierarchy(rows, col_idx: dict[str, int], result: ArchitectureParseResult) -> ArchitectureParseResult:
    """Parse Plant → Inverter → SCB → String rows into PlantConfig-shaped fields."""
    inv_order: list[str] = []
    inv_map: dict[str, dict] = {}
    # scb_id -> inverter_id resolved via parent chain
    scb_parent_inv: dict[str, str] = {}
    string_counts: list[int] = []

    for raw in rows:
        if not raw or all(c is None or str(c).strip() == "" for c in raw):
            continue
        node_id = _cell(_col(raw, col_idx, "id"))
        if not node_id:
            continue
        parent_id = _cell(_col(raw, col_idx, "parent_id"))
        dtype = _normalize_device_type(_cell(_col(raw, col_idx, "device_type")))
        ac_kw = _float_or_none(_col(raw, col_idx, "ac_capacity_kw"))
        dc_kwp = _float_or_none(_col(raw, col_idx, "dc_capacity_kwp"))
        strings = _int_or_none(_col(raw, col_idx, "strings_per_scb"))
        result.row_count += 1

        if dtype is None:
            # Infer from naming when device_type blank
            lower = node_id.lower()
            if "str" in lower.split("-")[-1] or lower.endswith("-str") or "-str-" in lower:
                dtype = "string"
            elif "scb" in lower or "smb" in lower:
                dtype = "scb"
            elif lower.startswith("inv") or "-inv-" in lower:
                dtype = "inverter"
            elif lower.startswith("plant") or lower in {"site", "plant"}:
                dtype = "plant"
            else:
                result.notes.append(f"Skipped row id={node_id!r}: unknown device_type.")
                continue

        if dtype == "plant":
            note = _cell(_col(raw, col_idx, "notes"))
            if not result.plant_name:
                result.plant_name = note or node_id
            if ac_kw is not None:
                result.ac_capacity_mw = _kw_to_mw(ac_kw)
            if dc_kwp is not None:
                result.dc_capacity_mwp = _kw_to_mw(dc_kwp)
            continue

        if dtype == "inverter":
            if node_id not in inv_map:
                inv_order.append(node_id)
                inv_map[node_id] = {"inverter_id": node_id, "rated_kw": ac_kw, "scbs": {}, "dc_kwp": dc_kwp}
            else:
                if ac_kw is not None and inv_map[node_id]["rated_kw"] is None:
                    inv_map[node_id]["rated_kw"] = ac_kw
                if dc_kwp is not None:
                    inv_map[node_id]["dc_kwp"] = dc_kwp
            if ac_kw is not None:
                result.equipment_ratings[node_id] = ac_kw
            continue

        if dtype == "scb":
            # Parent should be inverter; if parent is missing, try to resolve later.
            inv_id = parent_id
            if inv_id and inv_id in inv_map:
                pass
            elif inv_id and inv_id not in inv_map:
                # Parent declared as inverter id even if inverter row missing
                inv_order.append(inv_id)
                inv_map[inv_id] = {"inverter_id": inv_id, "rated_kw": None, "scbs": {}}
            else:
                # No parent — cannot attach
                result.notes.append(f"SCB {node_id!r} missing parent_id (inverter); skipped.")
                continue

            scb_parent_inv[node_id] = inv_id  # type: ignore[assignment]
            inv_map[inv_id]["scbs"][node_id] = {  # type: ignore[index]
                "scb_id": node_id,
                "strings_per_scb": strings,
                "strings_detected": False,
                "dc_capacity_kwp": dc_kwp,
            }
            entry: dict = {"inverter_id": inv_id}  # type: ignore[assignment]
            if strings is not None:
                entry["strings_per_scb"] = strings
                string_counts.append(strings)
            if dc_kwp is not None:
                entry["dc_capacity_kwp"] = dc_kwp
            if ac_kw is not None:
                entry["ac_capacity_kw"] = ac_kw
            result.architecture[node_id] = entry
            continue

        if dtype == "string":
            # Optional detail: bump strings_per_scb count on parent SCB when not set.
            scb_id = parent_id
            if not scb_id:
                continue
            inv_id = scb_parent_inv.get(scb_id)
            if inv_id is None:
                # Parent might be inverter (rare) — ignore string under inverter
                continue
            scb_node = inv_map.get(inv_id, {}).get("scbs", {}).get(scb_id)
            if scb_node is not None:
                scb_node["strings_detected"] = True
                # Count strings under this SCB if strings_per_scb not declared on SCB row
                counted = scb_node.setdefault("_string_ids", set())
                counted.add(node_id)
            continue

    # Finalize string counts from detected string rows when SCB omitted strings_per_scb
    for inv_id, node in inv_map.items():
        for scb_id, scb in node["scbs"].items():
            counted = scb.pop("_string_ids", None)
            if scb.get("strings_per_scb") is None and counted:
                scb["strings_per_scb"] = len(counted)
                if scb_id in result.architecture:
                    result.architecture[scb_id]["strings_per_scb"] = len(counted)
                    string_counts.append(len(counted))

    if not result.architecture:
        # Hierarchy with only plant+inverter rows is incomplete for fault modules
        if inv_map:
            result.errors.append(
                "Hierarchy sheet has inverters but no SCB rows. Add device_type=scb rows "
                "with parent_id pointing at each inverter."
            )
        else:
            result.errors.append(
                "No valid hierarchy rows found. Expected columns: "
                + ", ".join(HIERARCHY_COLUMNS)
                + "."
            )
        return result

    for inv_id in inv_order:
        node = inv_map[inv_id]
        result.inverters.append(
            {
                "inverter_id": inv_id,
                "rated_kw": node["rated_kw"],
                "scbs": [
                    {
                        "scb_id": s["scb_id"],
                        "strings_per_scb": s.get("strings_per_scb"),
                        "strings_detected": bool(s.get("strings_detected")),
                    }
                    for s in node["scbs"].values()
                ],
            }
        )

    if result.equipment_ratings and result.inverter_capacity_kw is None:
        result.inverter_capacity_kw = max(result.equipment_ratings.values())

    # Derive plant AC/DC from children when plant row omitted capacities
    if result.ac_capacity_mw is None and result.equipment_ratings:
        result.ac_capacity_mw = _kw_to_mw(sum(result.equipment_ratings.values()))
    if result.dc_capacity_mwp is None:
        inv_dc = [
            node.get("dc_kwp")
            for node in inv_map.values()
            if node.get("dc_kwp") is not None
        ]
        if inv_dc:
            result.dc_capacity_mwp = _kw_to_mw(sum(inv_dc))  # type: ignore[arg-type]
        else:
            scb_dc = [
                e["dc_capacity_kwp"]
                for e in result.architecture.values()
                if e.get("dc_capacity_kwp") is not None
            ]
            if scb_dc:
                result.dc_capacity_mwp = _kw_to_mw(sum(scb_dc))

    if string_counts:
        result.strings_per_scb = max(set(string_counts), key=string_counts.count)

    n_inv = len(result.inverters)
    n_scb = len(result.architecture)
    n_rated = len(result.equipment_ratings)
    cap_bits = []
    if result.ac_capacity_mw is not None:
        cap_bits.append(f"plant AC {result.ac_capacity_mw:g} MW")
    if result.dc_capacity_mwp is not None:
        cap_bits.append(f"DC {result.dc_capacity_mwp:g} MWp")
    result.notes.append(
        f"Loaded hierarchy: {n_inv} inverter(s), {n_scb} SMB/SCB(s) from {result.row_count} row(s)"
        + (f"; ratings for {n_rated}." if n_rated else ".")
        + ((" (" + ", ".join(cap_bits) + ")") if cap_bits else "")
    )
    return result


def parse_architecture_excel(source: Union[Path, BinaryIO, bytes]) -> ArchitectureParseResult:
    result = ArchitectureParseResult()
    try:
        if isinstance(source, bytes):
            wb = load_workbook(BytesIO(source), read_only=True, data_only=True)
        elif isinstance(source, Path):
            wb = load_workbook(source, read_only=True, data_only=True)
        else:
            wb = load_workbook(source, read_only=True, data_only=True)
    except Exception as exc:  # noqa: BLE001
        result.errors.append(f"Could not read Excel file: {exc}")
        return result

    try:
        # Prefer sheet named architecture; else first data sheet that looks like one
        ws = None
        sheet_name = None
        for name in wb.sheetnames:
            if name.strip().lower() == "architecture":
                ws = wb[name]
                sheet_name = name
                break
        if ws is None:
            for name in wb.sheetnames:
                lower = name.strip().lower()
                if lower in {"instructions", "readme", "scada", "fault_checklist"}:
                    continue
                ws = wb[name]
                sheet_name = name
                break
        if ws is None:
            result.errors.append("Workbook has no data sheet.")
            return result

        result.source_sheet = sheet_name
        rows = ws.iter_rows(values_only=True)
        try:
            header = [_normalize_header(c) for c in next(rows)]
        except StopIteration:
            result.errors.append("Architecture sheet is empty.")
            return result

        col_idx = {name: i for i, name in enumerate(header) if name}
        # Alias common synonyms
        if "inverter_rated_ac_kw" in col_idx and "inverter_rated_kw" not in col_idx:
            col_idx["inverter_rated_kw"] = col_idx["inverter_rated_ac_kw"]
        if "dc_capacity_kw" in col_idx and "dc_capacity_kwp" not in col_idx:
            col_idx["dc_capacity_kwp"] = col_idx["dc_capacity_kw"]
        if "ac_capacity" in col_idx and "ac_capacity_kw" not in col_idx:
            col_idx["ac_capacity_kw"] = col_idx["ac_capacity"]

        layout = _detect_layout(col_idx)
        if layout is None:
            result.errors.append(
                "Unrecognized architecture columns. Expected flat "
                f"({', '.join(TEMPLATE_COLUMNS)}) or hierarchy ({', '.join(HIERARCHY_COLUMNS)})."
            )
            return result

        result.format = layout
        if layout == "hierarchy":
            return _parse_hierarchy(rows, col_idx, result)
        return _parse_flat(rows, col_idx, result)
    finally:
        wb.close()


def workbook_has_architecture_sheet(source: Union[Path, BinaryIO, bytes]) -> bool:
    """True when workbook contains a sheet that looks like architecture (not SCADA-only)."""
    try:
        if isinstance(source, bytes):
            wb = load_workbook(BytesIO(source), read_only=True, data_only=True)
        elif isinstance(source, Path):
            wb = load_workbook(source, read_only=True, data_only=True)
        else:
            wb = load_workbook(source, read_only=True, data_only=True)
    except Exception:  # noqa: BLE001
        return False
    try:
        for name in wb.sheetnames:
            if name.strip().lower() == "architecture":
                return True
        return False
    finally:
        wb.close()


def try_parse_architecture_from_pack(source: Union[Path, BinaryIO, bytes]) -> Optional[ArchitectureParseResult]:
    """Parse architecture from a Complete Analysis Pack (or any multi-sheet xlsx).

    Returns None when no architecture sheet / unparsable — never raises.
    """
    if isinstance(source, (Path, bytes)) and not workbook_has_architecture_sheet(source):
        # Still attempt parse — sheet may be named differently with hierarchy headers
        pass
    parsed = parse_architecture_excel(source)
    if parsed.ok:
        return parsed
    return None


def apply_smb_pattern(
    inverter_ids: list[str],
    *,
    smbs_per_inverter: int,
    strings_per_smb: int,
    rated_kw: Optional[float] = None,
    existing: Optional[list[dict]] = None,
) -> list[dict]:
    """Build / overwrite architecture using a compact plant pattern.

    Existing SCBs for selected inverters are replaced; other inverters are preserved.
    """
    if smbs_per_inverter < 1 or strings_per_smb < 1:
        raise ValueError("smbs_per_inverter and strings_per_smb must be >= 1")

    selected = {i.strip() for i in inverter_ids if i and i.strip()}
    preserved: list[dict] = []
    if existing:
        for inv in existing:
            if inv.get("inverter_id") not in selected:
                preserved.append(inv)

    generated: list[dict] = []
    for inv_id in sorted(selected):
        scbs = []
        for i in range(1, smbs_per_inverter + 1):
            scbs.append(
                {
                    "scb_id": f"{inv_id}-SCB-{i:02d}",
                    "strings_per_scb": strings_per_smb,
                    "strings_detected": False,
                }
            )
        generated.append({"inverter_id": inv_id, "rated_kw": rated_kw, "scbs": scbs})

    # Keep non-selected first (stable), then newly patterned
    return preserved + generated


def inverters_from_plant_architecture(
    architecture: dict[str, dict],
    equipment_ratings: Optional[dict[str, float]] = None,
) -> list[dict]:
    """Rebuild UI inverter tree from stored plant_config architecture + ratings."""
    ratings = equipment_ratings or {}
    inv_order: list[str] = []
    inv_map: dict[str, dict] = {}
    for scb_id, entry in architecture.items():
        inv_id = (entry or {}).get("inverter_id")
        if not inv_id:
            continue
        if inv_id not in inv_map:
            inv_order.append(inv_id)
            inv_map[inv_id] = {
                "inverter_id": inv_id,
                "rated_kw": ratings.get(inv_id),
                "scbs": [],
            }
        inv_map[inv_id]["scbs"].append(
            {
                "scb_id": scb_id,
                "strings_per_scb": (entry or {}).get("strings_per_scb"),
                "strings_detected": False,
            }
        )
    return [inv_map[i] for i in inv_order]
