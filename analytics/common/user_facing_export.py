"""User-facing CSV / preview formatting for Lite downloads and Raw Data tables.

Canonical parquet keeps UTC + snake_case fields for analysis. Exports and Explorer
tables should show plant-local time and professional headers (no internal junk).
"""
from __future__ import annotations

from typing import Any, Mapping

import pandas as pd

# Canonical field → professional column header for downloads / preview.
DISPLAY_HEADERS: dict[str, str] = {
    "timestamp_utc": "Timestamp",
    "timestamp": "Timestamp",
    "device_id": "Equipment ID",
    "device_type": "Device Type",
    "inverter_id": "Inverter ID",
    "scb_id": "SCB ID",
    "string_id": "String ID",
    "icr_id": "ICR ID",
    "ac_power_kw": "AC Power (kW)",
    "dc_power_kw": "DC Power (kW)",
    "dc_current_a": "DC Current (A)",
    "dc_voltage_v": "DC Voltage (V)",
    "poa_w_m2": "POA (W/m²)",
    "ghi_w_m2": "GHI (W/m²)",
    "module_temp_c": "Module Temp (°C)",
    "ambient_temp_c": "Ambient Temp (°C)",
    "energy_kwh": "Energy (kWh)",
}

# Preferred column order for user downloads (unknown cols appended).
_DISPLAY_ORDER: tuple[str, ...] = (
    "Timestamp",
    "Equipment ID",
    "Device Type",
    "ICR ID",
    "Inverter ID",
    "SCB ID",
    "String ID",
    "AC Power (kW)",
    "DC Power (kW)",
    "DC Current (A)",
    "DC Voltage (V)",
    "POA (W/m²)",
    "GHI (W/m²)",
    "Module Temp (°C)",
    "Ambient Temp (°C)",
    "Energy (kWh)",
)

# Never show these internal / fragment columns in user downloads.
_INTERNAL_PREFIXES: tuple[str, ...] = ("__", "_fragment", "fragment_")
_INTERNAL_EXACT: frozenset[str] = frozenset(
    {
        "_source_file",
        "__index_level_0__",
    }
)


def plant_timezone_from_config(plant_config: Mapping[str, Any] | None) -> str | None:
    """Extract IANA timezone from job plant_config_json (plant.timezone or top-level)."""
    if not plant_config:
        return None
    plant = plant_config.get("plant") if isinstance(plant_config.get("plant"), dict) else plant_config
    if not isinstance(plant, dict):
        return None
    tz = plant.get("timezone")
    if tz and str(tz).strip():
        return str(tz).strip()
    return None


def _is_internal_column(name: str) -> bool:
    n = (name or "").strip()
    if not n or n in _INTERNAL_EXACT:
        return True
    lower = n.lower()
    return any(lower.startswith(p) for p in _INTERNAL_PREFIXES)


def _rename_columns(columns: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    used: set[str] = set()
    for col in columns:
        if _is_internal_column(col):
            continue
        label = DISPLAY_HEADERS.get(col, col)
        # Official pack / already-pretty names stay as-is when not in map.
        if col in DISPLAY_HEADERS:
            label = DISPLAY_HEADERS[col]
        base = label
        n = 2
        while label in used:
            label = f"{base} ({n})"
            n += 1
        used.add(label)
        out[col] = label
    return out


def _convert_timestamps_to_local(df: pd.DataFrame, timezone: str | None) -> pd.DataFrame:
    """Convert timestamp-like columns from UTC to plant local wall time (tz-naive)."""
    out = df.copy()
    tz = (timezone or "").strip() or None
    for col in list(out.columns):
        cl = str(col).lower()
        is_ts = cl in {"timestamp_utc", "timestamp", "datetime"} or (
            "time" in cl and "timezone" not in cl
        )
        if not is_ts and not pd.api.types.is_datetime64_any_dtype(out[col]):
            continue
        series = pd.to_datetime(out[col], utc=True, errors="coerce")
        if not series.notna().any():
            continue
        if tz:
            try:
                local = series.dt.tz_convert(tz)
            except (TypeError, AttributeError, ValueError):
                # Invalid tz — leave UTC wall clock rather than crashing export.
                local = series
            out[col] = local.dt.tz_localize(None)
        else:
            out[col] = series.dt.tz_localize(None)
    return out


def _drop_empty_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Drop columns that are entirely null / blank (no useful user signal)."""
    keep: list[str] = []
    for col in df.columns:
        s = df[col]
        if s.isna().all():
            continue
        if s.dtype == object or pd.api.types.is_string_dtype(s):
            if s.fillna("").astype(str).str.strip().eq("").all():
                continue
        keep.append(col)
    return df[keep] if keep else df.iloc[:, 0:0]


def _order_display_columns(columns: list[str]) -> list[str]:
    ordered = [c for c in _DISPLAY_ORDER if c in columns]
    ordered.extend(c for c in columns if c not in ordered)
    return ordered


def format_user_facing_frame(
    df: pd.DataFrame,
    *,
    timezone: str | None = None,
    drop_empty: bool = True,
) -> pd.DataFrame:
    """Prepare a canonical (or raw) frame for Lite CSV download / Raw Data preview.

    - Converts UTC timestamps to plant-local wall time when ``timezone`` is set
    - Renames canonical fields to professional headers
    - Drops internal ``__fragment_*`` / empty identity columns
    """
    if df.empty:
        return df.copy()

    # Drop internal columns first (by original name).
    cols = [c for c in df.columns if not _is_internal_column(str(c))]
    work = df[cols].copy()
    work = _convert_timestamps_to_local(work, timezone)
    rename = _rename_columns([str(c) for c in work.columns])
    work = work.rename(columns=rename)
    if drop_empty:
        work = _drop_empty_columns(work)
    work = work[_order_display_columns([str(c) for c in work.columns])]
    return work


def format_timestamp_series_local(series: pd.Series, timezone: str | None) -> list[str]:
    """Format a UTC timestamp series as plant-local ``YYYY-MM-DD HH:MM:SS`` strings."""
    ts = pd.to_datetime(series, utc=True, errors="coerce")
    tz = (timezone or "").strip() or None
    if tz:
        try:
            ts = ts.dt.tz_convert(tz)
        except (TypeError, AttributeError, ValueError):
            pass
    naive = ts.dt.tz_localize(None)
    return naive.dt.strftime("%Y-%m-%d %H:%M:%S").fillna("").tolist()
