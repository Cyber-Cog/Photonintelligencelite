"""Cell / header helpers and metric mapping for SCADA Excel layouts."""
from __future__ import annotations

import re

from analytics.common.complete_analysis_pack import SCADA_COLUMNS
from analytics.common.config_loader import load_aliases

_INVERTER_BLOCK_RE = re.compile(
    r"^\s*(?:INVERTER|INV)\s*[-_]?\s*(\d+)\s*$",
    re.IGNORECASE,
)
_TIMESTAMP_LEAF_RE = re.compile(
    r"date\s*(and|&)?\s*time|timestamp|date\s*time|^time$|^date$",
    re.IGNORECASE,
)
_METRIC_TOKENS = ("power", "voltage", "current", "temp", "irradiance", "energy")


def cell_to_str(value) -> str:
    if value is None:
        return ""
    return str(value).strip()


def normalize_header(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def looks_like_timestamp_header(value: str) -> bool:
    if not value or not value.strip():
        return False
    n = normalize_header(value)
    if _TIMESTAMP_LEAF_RE.search(n):
        return True
    # Alias-driven match
    aliases = load_aliases().get("timestamp", [])
    return n in {normalize_header(a) for a in aliases}


def inverter_id_from_label(label: str) -> str | None:
    m = _INVERTER_BLOCK_RE.match(label.strip())
    if not m:
        return None
    return f"INV-{int(m.group(1)):02d}"


def ffill_row(values: list[str]) -> list[str]:
    out: list[str] = []
    last = ""
    for v in values:
        if v.strip():
            last = v.strip()
            out.append(last)
        else:
            out.append(last)
    return out


def pad_matrix(rows: list[list[str]]) -> list[list[str]]:
    width = max((len(r) for r in rows), default=0)
    return [list(r) + [""] * (width - len(r)) for r in rows]


def has_metric_token(value: str) -> bool:
    n = normalize_header(value)
    return any(tok in n for tok in _METRIC_TOKENS)


def map_metric(category: str, leaf: str) -> str | None:
    """Map (category, leaf) header pair to a tidy long-form column name."""
    cat = normalize_header(category)
    leaf_n = normalize_header(leaf)
    if not leaf_n or looks_like_timestamp_header(leaf_n):
        return None

    if leaf_n in {"frequency (hz)", "frequency", "r-y", "y-b", "b-r", "efficiency", "eff", "on/off", "status"}:
        return None
    if "igbt" in leaf_n or "frequency" in leaf_n:
        return None
    if "efficiency" in leaf_n:
        return None
    if leaf_n in {"(kwh)", "cumm. (kwh)", "kwh"} or "energy" in cat:
        return None
    if "energy" in leaf_n:
        return None

    if "dc" in cat and "input" in cat:
        if "voltage" in leaf_n:
            return "DC Voltage (V)"
        if "current" in leaf_n:
            return "DC Current (A)"
        if "power" in leaf_n:
            return "DC Power (kW)"

    if "ac" in cat and "output" in cat and "voltage" not in cat:
        if "power" in leaf_n:
            return "AC Power (kW)"

    if "power" in leaf_n and ("kw" in leaf_n or leaf_n == "power"):
        if "dc" not in cat:
            return "AC Power (kW)"

    if leaf_n.startswith("temp") or "temp (" in leaf_n or leaf_n.endswith("temp"):
        if "module" in leaf_n or "panel" in leaf_n:
            return "Module Temp (C)"
        return "Ambient Temp (C)"

    # Irradiance → official pack headers (keep wide→tidy output in sync with SCADA_COLUMNS).
    if "ghi" in leaf_n or ("horizontal" in leaf_n and "irradiance" in leaf_n):
        return "GHI (W/m2)"
    if any(tok in leaf_n for tok in ("irradiance", "poa", "gti")) or "irradiance" in cat:
        return "Irradiance (W/m2)"

    return None


def sanitize_headers(headers: list[str]) -> list[str]:
    """Replace blank / Unnamed headers so mapping UI never sees silent Unnamed: N."""
    out: list[str] = []
    seen: dict[str, int] = {}
    for i, raw in enumerate(headers):
        name = (raw or "").strip()
        if not name or name.lower().startswith("unnamed"):
            name = f"Column_{i + 1}"
        if name in seen:
            seen[name] += 1
            name = f"{name}_{seen[name]}"
        else:
            seen[name] = 0
        out.append(name)
    return out


def score_header_row(row: list[str]) -> float:
    """Score a row as a likely header: timestamp-like + power/current/voltage tokens."""
    score = 0.0
    non_empty = [c for c in row if c.strip()]
    if not non_empty:
        return 0.0
    if any(looks_like_timestamp_header(c) for c in row):
        score += 3.0
    metric_hits = sum(1 for c in non_empty if has_metric_token(c))
    score += min(metric_hits, 6) * 0.5
    # Alias vocabulary boost
    alias_hits = 0
    alias_map = load_aliases()
    flat = {normalize_header(a) for aliases in alias_map.values() for a in aliases}
    for c in non_empty:
        if normalize_header(c) in flat:
            alias_hits += 1
    score += min(alias_hits, 8) * 0.25
    # Penalize title banners
    if len(non_empty) == 1 and "report" in non_empty[0].lower():
        score -= 5.0
    return score


# Must match Complete Analysis Pack headers (analytics.common.complete_analysis_pack.SCADA_COLUMNS).
TIDY_FIELDS = list(SCADA_COLUMNS)
