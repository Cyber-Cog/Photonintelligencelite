"""Parse wide SCADA column names: plant/ICR/inverter prefixes + metric leaf.

Handles historian / trend-report exports such as:
  ESSP_20MW ICR1 Inverter 1 Active Power (kW)
  INV1_Pac
  Inverter_02_DC Current (A)
  PlantA ICR-2 INV3 Active Power (kW)

Used by CSV reshape and Excel wide_single_header so both paths stay aligned.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from analytics.common.config_loader import load_aliases

# Prefer plant? + ICR + Inverter + metric (ICR must not be swallowed as plant).
_WIDE_WITH_ICR_RE = re.compile(
    r"""^
    (?:(?P<plant>.+?)[\s_\-]+)?
    ICR[\s_\-]?(?P<icr>\d+)[\s_\-]+
    (?:INV(?:ERTER)?[\s_\-\.]*)(?P<inv>\d+)
    [\s_\-\.]*
    (?P<rest>.*)$
    """,
    re.IGNORECASE | re.VERBOSE,
)

# Plant? + Inverter + metric (no ICR).
_WIDE_INV_ONLY_RE = re.compile(
    r"""^
    (?:(?P<plant>.+?)[\s_\-]+)?
    (?:INV(?:ERTER)?[\s_\-\.]*)(?P<inv>\d+)
    [\s_\-\.]*
    (?P<rest>.*)$
    """,
    re.IGNORECASE | re.VERBOSE,
)

# Compact OEM: INV01.Pac / INV_1.Pdc (dot or underscore before short metric)
_COMPACT_INV_METRIC_RE = re.compile(
    r"^(?:INV(?:ERTER)?[\s_\-\.]*)(?P<inv>\d+)[\s_\-\.]*(?P<rest>.+)$",
    re.IGNORECASE,
)

_TIMESTAMP_RE = re.compile(
    r"^(?:time\s*stamp|timestamp|date\s*(?:and|&)?\s*time|date_time|datetime|plant\s*time\s*stamp|planttimestamp)$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class WideColumnParse:
    """One wide device+metric column."""

    equipment_id: str
    metric: str  # Official pack-style header e.g. "AC Power (kW)"
    icr_id: str | None = None
    plant_id: str | None = None
    inverter_num: int = 0


def normalize_header(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip().lower())


def looks_like_timestamp_header(value: str) -> bool:
    n = normalize_header(value)
    if not n:
        return False
    if _TIMESTAMP_RE.match(n.replace(" ", "")) or _TIMESTAMP_RE.match(n):
        return True
    if "planttimestamp" in n.replace(" ", "") or n in {"timestamp", "date", "time", "datetime"}:
        return True
    aliases = load_aliases().get("timestamp", [])
    return n in {normalize_header(a) for a in aliases}


def leaf_to_metric(leaf: str) -> str | None:
    """Map metric leaf (after device prefix) → tidy pack-style column name."""
    n = normalize_header(leaf)
    n = n.strip(" _-.")
    # Drop trailing unit-only noise already in parens via normalize; keep tokens.
    n = re.sub(r"[()\[\]{}]", " ", n)
    n = re.sub(r"\s+", " ", n).strip()
    if not n:
        return "AC Power (kW)"

    if any(tok in n for tok in ("dc bus voltage", "dc voltage", "vdc", "v dc")) or n in {
        "voltage",
        "v",
        "v_dc",
    }:
        if "ac" in n and "dc" not in n:
            return None
        return "DC Voltage (V)"
    if any(tok in n for tok in ("dc current", "idc", "i dc")) or n in {
        "current",
        "i",
        "i_dc",
        "amps",
    }:
        return "DC Current (A)"
    if "dc power" in n or n in {"pdc", "p_dc", "p dc"}:
        return "DC Power (kW)"
    if any(
        tok in n
        for tok in (
            "active power",
            "ac power",
            "pac",
            "p_ac",
            "p ac",
            "output power",
            "real power",
            "power kw",
            "power (kw)",
        )
    ) or n in {"p", "power", "kw", "pac"}:
        return "AC Power (kW)"
    if "ghi" in n or ("horizontal" in n and "irradiance" in n):
        return "GHI (W/m2)"
    if any(tok in n for tok in ("irradiance", "poa", "gti")):
        return "Irradiance (W/m2)"
    if "module" in n and "temp" in n:
        return "Module Temp (C)"
    if "temp" in n:
        return "Ambient Temp (C)"
    if "power" in n and "dc" not in n:
        return "AC Power (kW)"
    return None


def parse_wide_device_column(header: str) -> WideColumnParse | None:
    """Parse a wide device+metric header, or None if not that shape."""
    raw = (header or "").strip()
    if not raw or looks_like_timestamp_header(raw):
        return None

    m = _WIDE_WITH_ICR_RE.match(raw)
    if m is None:
        m = _WIDE_INV_ONLY_RE.match(raw)
    if m is None:
        m = _COMPACT_INV_METRIC_RE.match(raw)
        if not m:
            return None
        inv = int(m.group("inv"))
        rest = m.group("rest") or ""
        metric = leaf_to_metric(rest)
        if not metric:
            return None
        return WideColumnParse(
            equipment_id=f"INV-{inv:02d}",
            metric=metric,
            inverter_num=inv,
        )

    inv = int(m.group("inv"))
    rest = m.group("rest") or ""
    metric = leaf_to_metric(rest)
    if not metric:
        return None

    groups = m.groupdict()
    icr_raw = groups.get("icr")
    plant = groups.get("plant")
    # Guard: plant must not be another inverter token mistakenly captured
    if plant and re.search(r"inv(?:erter)?\s*\d+", plant, re.I):
        return None
    icr_id = f"ICR{int(icr_raw)}" if icr_raw else None
    if icr_id:
        equipment_id = f"{icr_id}-INV-{inv:02d}"
    else:
        equipment_id = f"INV-{inv:02d}"

    return WideColumnParse(
        equipment_id=equipment_id,
        metric=metric,
        icr_id=icr_id,
        plant_id=plant.strip() if plant else None,
        inverter_num=inv,
    )


def count_wide_device_columns(headers: list[str]) -> tuple[int, int]:
    """Return (mapped_wide_cols, unique_equipment_ids)."""
    parsed = [parse_wide_device_column(h) for h in headers]
    hits = [p for p in parsed if p is not None]
    devices = {p.equipment_id for p in hits}
    return len(hits), len(devices)


def metric_suffix_for_aliasing(header: str) -> str | None:
    """If header is a wide prefixed column, return the metric leaf for alias scoring."""
    p = parse_wide_device_column(header)
    if p is None:
        return None
    return p.metric
