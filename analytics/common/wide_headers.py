"""Parse wide SCADA column names: plant/ICR/inverter/SCB prefixes + metric leaf.

Handles historian / trend-report exports such as:
  ESSP_20MW ICR1 Inverter 1 Active Power (kW)
  ESSP_20MW ICR1 INV1 SCB1 O/P Current (A)
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

# Standalone SCB/SMB wide columns (no INV prefix): SCB1 O/P Current (A)
_WIDE_SCB_ONLY_RE = re.compile(
    r"""^
    (?:(?P<plant>.+?)[\s_\-]+)?
    (?:SCB|SMB)[\s_\-]?(?P<scb>\d+)
    [\s_\-\.]*
    (?P<rest>.*)$
    """,
    re.IGNORECASE | re.VERBOSE,
)

# SCB/SMB + optional String/channel embedded in the metric rest after INV.
_REST_SCB_RE = re.compile(
    r"""^
    (?:SCB|SMB)[\s_\-]?(?P<scb>\d+)
    (?:[\s_\-\.]+(?:STR(?:ING)?|CH(?:ANNEL)?)[\s_\-]?(?P<strn>\d+))?
    [\s_\-\.]*
    (?P<metric>.*)$
    """,
    re.IGNORECASE | re.VERBOSE,
)

_REST_STRING_ONLY_RE = re.compile(
    r"""^
    (?:STR(?:ING)?|CH(?:ANNEL)?)[\s_\-]?(?P<strn>\d+)
    [\s_\-\.]*
    (?P<metric>.*)$
    """,
    re.IGNORECASE | re.VERBOSE,
)

_TIMESTAMP_RE = re.compile(
    r"^(?:time\s*stamp|timestamp|date\s*(?:and|&)?\s*time|date_time|datetime|plant\s*time\s*stamp|planttimestamp)$",
    re.IGNORECASE,
)

# Strip leading device tokens left in a metric leaf (SCB1 / String 3 / …).
_LEADING_DEVICE_LEAF_RE = re.compile(
    r"^(?:(?:scb|smb|str(?:ing)?|ch(?:annel)?|inv(?:erter)?|icr)\s*\d+\s*)+",
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
    scb_num: int | None = None
    string_num: int | None = None


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
    n = re.sub(r"[/\._]+", " ", n)
    n = re.sub(r"\s+", " ", n).strip()
    # Drop residual device tags so "scb1 o p current a" → "o p current a"
    n = _LEADING_DEVICE_LEAF_RE.sub("", n).strip()
    if not n:
        return "AC Power (kW)"

    if any(
        tok in n
        for tok in (
            "dc bus voltage",
            "dc voltage",
            "vdc",
            "v dc",
            "bus voltage",
            "o p voltage",
            "op voltage",
            "output voltage",
        )
    ) or n in {
        "voltage",
        "v",
        "v_dc",
    }:
        if "ac" in n and "dc" not in n and "bus" not in n and "o p" not in n and "output" not in n:
            return None
        return "DC Voltage (V)"

    # O/P Current, Output Current, DC Current, bare Current (A)
    if any(
        tok in n
        for tok in (
            "dc current",
            "idc",
            "i dc",
            "o p current",
            "op current",
            "output current",
            "scb current",
            "smb current",
        )
    ) or n in {
        "current",
        "i",
        "i_dc",
        "amps",
        "current a",
    } or (re.search(r"\bcurrent\b", n) and "ac" not in n and "power" not in n):
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


def _split_rest_devices(rest: str) -> tuple[int | None, int | None, str]:
    """Pull SCB / string numbers out of the post-INV rest; return (scb, string, metric_leaf)."""
    raw = (rest or "").strip(" _-.")
    if not raw:
        return None, None, ""
    m = _REST_SCB_RE.match(raw)
    if m:
        scb = int(m.group("scb"))
        strn = int(m.group("strn")) if m.group("strn") else None
        return scb, strn, (m.group("metric") or "").strip(" _-.")
    m2 = _REST_STRING_ONLY_RE.match(raw)
    if m2:
        return None, int(m2.group("strn")), (m2.group("metric") or "").strip(" _-.")
    return None, None, raw


def _build_equipment_id(
    *,
    icr_id: str | None,
    inv: int,
    scb: int | None = None,
    string_num: int | None = None,
) -> str:
    if icr_id:
        base = f"{icr_id}-INV-{inv:02d}"
    else:
        base = f"INV-{inv:02d}"
    if scb is not None:
        base = f"{base}-SCB-{scb:02d}"
    if string_num is not None:
        if scb is None:
            base = f"{base}-SCB-00-STR-{string_num:02d}"
        else:
            base = f"{base}-STR-{string_num:02d}"
    return base


def infer_level_from_column_name(column_name: str) -> str | None:
    """Token-based hierarchy level from a wide header (never returns multi)."""
    n = column_name or ""
    if not n.strip():
        return None
    # Specificity: string > scb > inverter > icr > plant/WMS
    has_scb = bool(re.search(r"(?:SCB|SMB)[\s_\-]?\d+", n, re.I))
    has_str = bool(re.search(r"(?:STR(?:ING)?|CH(?:ANNEL)?)[\s_\-]?\d+", n, re.I))
    has_inv = bool(re.search(r"(?:INV(?:ERTER)?)[\s_\-]?\d+", n, re.I))
    has_icr = bool(re.search(r"ICR[\s_\-]?\d+", n, re.I))
    if has_scb and has_str:
        return "string"
    if has_scb:
        return "scb"
    if has_str and not has_inv:
        return "string"
    if has_inv:
        return "inverter"
    if has_icr:
        return "icr"
    nl = n.lower()
    if any(tok in nl for tok in ("wms", "poa", "ghi", "irradiance", "plant")) and not has_inv:
        return "plant"
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
        if m is not None:
            inv = int(m.group("inv"))
            rest = m.group("rest") or ""
            scb, strn, metric_leaf = _split_rest_devices(rest)
            metric = leaf_to_metric(metric_leaf if metric_leaf or scb or strn else rest)
            if not metric:
                return None
            return WideColumnParse(
                equipment_id=_build_equipment_id(icr_id=None, inv=inv, scb=scb, string_num=strn),
                metric=metric,
                inverter_num=inv,
                scb_num=scb,
                string_num=strn,
            )
        # Standalone SCB/SMB (no INV)
        m_scb = _WIDE_SCB_ONLY_RE.match(raw)
        if not m_scb:
            return None
        scb = int(m_scb.group("scb"))
        plant = m_scb.groupdict().get("plant")
        if plant and re.search(r"(?:icr|inv(?:erter)?)\s*\d+", plant, re.I):
            return None
        metric = leaf_to_metric(m_scb.group("rest") or "")
        if not metric:
            return None
        return WideColumnParse(
            equipment_id=f"SCB-{scb:02d}",
            metric=metric,
            plant_id=plant.strip() if plant else None,
            scb_num=scb,
        )

    inv = int(m.group("inv"))
    rest = m.group("rest") or ""
    scb, strn, metric_leaf = _split_rest_devices(rest)
    metric = leaf_to_metric(metric_leaf if (metric_leaf or scb is not None or strn is not None) else rest)
    if not metric:
        return None

    groups = m.groupdict()
    icr_raw = groups.get("icr")
    plant = groups.get("plant")
    # Guard: plant must not be another inverter token mistakenly captured
    if plant and re.search(r"inv(?:erter)?\s*\d+", plant, re.I):
        return None
    icr_id = f"ICR{int(icr_raw)}" if icr_raw else None
    equipment_id = _build_equipment_id(icr_id=icr_id, inv=inv, scb=scb, string_num=strn)

    return WideColumnParse(
        equipment_id=equipment_id,
        metric=metric,
        icr_id=icr_id,
        plant_id=plant.strip() if plant else None,
        inverter_num=inv,
        scb_num=scb,
        string_num=strn,
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
