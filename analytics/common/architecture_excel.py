"""Plant architecture Excel template (download) and parser (upload).

Designed for large plants (hundreds of inverters, thousands of SMBs) where the web form
is not a practical data-entry path. Columns are deliberately flat / one-row-per-SCB.
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

TEMPLATE_FILENAME = "pic_lite_plant_architecture_template.xlsx"


@dataclass
class ArchitectureParseResult:
    equipment_ratings: dict[str, float] = field(default_factory=dict)
    architecture: dict[str, dict] = field(default_factory=dict)
    inverters: list[dict] = field(default_factory=list)
    """UI-shaped list: [{inverter_id, rated_kw, scbs:[{scb_id, strings_per_scb, strings_detected}]}]"""
    row_count: int = 0
    notes: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return bool(self.architecture) and not self.errors


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
        # Prefer sheet named architecture; else first data sheet
        ws = None
        for name in wb.sheetnames:
            if name.strip().lower() == "architecture":
                ws = wb[name]
                break
        if ws is None:
            for name in wb.sheetnames:
                if name.strip().lower() != "instructions":
                    ws = wb[name]
                    break
        if ws is None:
            result.errors.append("Workbook has no data sheet.")
            return result

        rows = ws.iter_rows(values_only=True)
        try:
            header = [(_cell(c) or "").lower().replace(" ", "_") for c in next(rows)]
        except StopIteration:
            result.errors.append("Architecture sheet is empty.")
            return result

        col_idx = {name: i for i, name in enumerate(header)}
        required = ("inverter_id", "scb_id")
        for req in required:
            if req not in col_idx:
                result.errors.append(
                    f"Missing required column '{req}'. Expected columns: {', '.join(TEMPLATE_COLUMNS)}."
                )
                return result

        # Aggregate inverter → scbs preserving first-seen order
        inv_order: list[str] = []
        inv_map: dict[str, dict] = {}

        for raw in rows:
            if not raw or all(c is None or str(c).strip() == "" for c in raw):
                continue
            inv_id = _cell(raw[col_idx["inverter_id"]] if col_idx["inverter_id"] < len(raw) else None)
            scb_id = _cell(raw[col_idx["scb_id"]] if col_idx["scb_id"] < len(raw) else None)
            if not inv_id or not scb_id:
                continue

            rated = None
            if "inverter_rated_kw" in col_idx and col_idx["inverter_rated_kw"] < len(raw):
                rated = _float_or_none(raw[col_idx["inverter_rated_kw"]])
            strings = None
            if "strings_per_scb" in col_idx and col_idx["strings_per_scb"] < len(raw):
                strings = _int_or_none(raw[col_idx["strings_per_scb"]])

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

        n_inv = len(result.inverters)
        n_scb = len(result.architecture)
        n_rated = len(result.equipment_ratings)
        result.notes.append(
            f"Loaded {n_inv} inverter(s), {n_scb} SMB/SCB(s) from {result.row_count} Excel row(s)"
            + (f"; ratings for {n_rated} inverter(s)." if n_rated else ".")
        )
        return result
    finally:
        wb.close()


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
