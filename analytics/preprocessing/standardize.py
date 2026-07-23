"""Standardization: map vendor columns to the fixed canonical schema.

After this stage, no algorithm ever needs to know the original vendor column names.
See docs/architecture_decisions.md §1.
"""
from __future__ import annotations

import pandas as pd

from analytics.common.equipment_ids import (
    derive_level,
    extract_parent_inverter,
    extract_parent_scb,
    resolve_inverter_from_architecture,
)
from analytics.core.context import CANONICAL_COLUMNS, ResolvedMapping
from analytics.preprocessing.timestamps import parse_timestamp_series

NUMERIC_CANONICAL_FIELDS = {
    "ac_power_kw",
    "dc_power_kw",
    "dc_current_a",
    "dc_voltage_v",
    "poa_w_m2",
    "ghi_w_m2",
    "module_temp_c",
    "ambient_temp_c",
    "energy_kwh",
}

def _unit_scale(source_column: str, canonical_field: str) -> float:
    """Convert MW/MWh vendor units to kW/kWh when column names imply megawatt scale."""
    name = source_column.lower().replace(" ", "").replace("_", "")
    if canonical_field == "energy_kwh" and "mwh" in name:
        return 1000.0
    if canonical_field in ("ac_power_kw", "dc_power_kw") and name.endswith("mw") and "mwh" not in name:
        return 1000.0
    if canonical_field in ("ac_power_kw", "dc_power_kw") and "plantac" in name:
        return 1000.0
    if canonical_field == "dc_power_kw" and "plantdc" in name:
        return 1000.0
    return 1.0


def _inverse_mapping(column_to_canonical: dict[str, str]) -> dict[str, list[str]]:
    inv: dict[str, list[str]] = {}
    for col, field in column_to_canonical.items():
        if not field or field == "ignore":
            continue
        inv.setdefault(field, []).append(col)
    return inv


def _coalesced_series(raw_df: pd.DataFrame, source_cols: list[str], canonical_field: str) -> pd.Series:
    """Build one canonical column from multiple vendor columns (first non-null wins left-to-right)."""
    if not source_cols:
        return pd.Series([pd.NA] * len(raw_df), index=raw_df.index)
    series_list: list[pd.Series] = []
    for col in source_cols:
        if col not in raw_df.columns:
            continue
        scale = _unit_scale(col, canonical_field)
        s = pd.to_numeric(raw_df[col], errors="coerce")
        if scale != 1.0:
            s = s * scale
        series_list.append(s)
    if not series_list:
        return pd.Series([pd.NA] * len(raw_df), index=raw_df.index)
    out = series_list[0]
    for s in series_list[1:]:
        out = out.where(out.notna(), s)
    return out


def standardize(
    raw_df: pd.DataFrame,
    mapping: ResolvedMapping,
    timestamp_column: str,
    *,
    architecture: dict | None = None,
) -> pd.DataFrame:
    """Rename, coerce, and derive equipment hierarchy fields.

    When ``architecture`` is provided (SCB/SMB → inverter map from Setup), missing
    ``inverter_id`` values are backfilled so SCB-level algorithms (disconnected strings,
    clipping by current) can run on OEM ids like ``SMB-01`` that do not embed a parent INV.
    """
    inverse = _inverse_mapping(mapping.column_to_canonical)

    df = pd.DataFrame(index=raw_df.index)
    df["timestamp_utc"] = parse_timestamp_series(raw_df[timestamp_column])
    df = df.dropna(subset=["timestamp_utc"]).copy()
    raw_df = raw_df.loc[df.index]

    for field_name in CANONICAL_COLUMNS:
        if field_name == "timestamp_utc":
            continue
        sources = inverse.get(field_name, [])
        if field_name in NUMERIC_CANONICAL_FIELDS:
            df[field_name] = _coalesced_series(raw_df, sources, field_name)
        elif sources:
            col = sources[0]
            df[field_name] = raw_df[col] if col in raw_df.columns else pd.NA
        else:
            df[field_name] = pd.NA

    if df["device_id"].isna().all():
        for candidate in ("inverter_id", "scb_id", "string_id"):
            if candidate in df.columns and not df[candidate].isna().all():
                df["device_id"] = df[candidate]
                break

    df["device_id"] = df["device_id"].astype("string")

    needs_level = df["device_type"].isna()
    if needs_level.any():
        df.loc[needs_level, "device_type"] = df.loc[needs_level, "device_id"].map(
            lambda x: derive_level(x) or "plant"
        )

    is_string_row = df["device_type"] == "string"
    if is_string_row.any() and df.loc[is_string_row, "string_id"].isna().all():
        df.loc[is_string_row, "string_id"] = df.loc[is_string_row, "device_id"]

    is_scb_row = df["device_type"] == "scb"
    if is_scb_row.any() and df.loc[is_scb_row, "scb_id"].isna().all():
        df.loc[is_scb_row, "scb_id"] = df.loc[is_scb_row, "device_id"]

    needs_parent_scb = df["string_id"].notna() & df["scb_id"].isna()
    if needs_parent_scb.any():
        df.loc[needs_parent_scb, "scb_id"] = df.loc[needs_parent_scb, "string_id"].map(extract_parent_scb)

    needs_parent_inv = df["scb_id"].notna() & df["inverter_id"].isna()
    if needs_parent_inv.any():
        df.loc[needs_parent_inv, "inverter_id"] = df.loc[needs_parent_inv, "scb_id"].map(extract_parent_inverter)

    # Architecture backfill for standalone SMB/SCB ids (no INV embedded in the name).
    if architecture:
        still_missing = df["scb_id"].notna() & df["inverter_id"].isna()
        if still_missing.any():
            df.loc[still_missing, "inverter_id"] = df.loc[still_missing, "scb_id"].map(
                lambda sid: resolve_inverter_from_architecture(sid, architecture)
            )

    is_inverter_row = df["device_type"] == "inverter"
    if is_inverter_row.any() and df.loc[is_inverter_row, "inverter_id"].isna().all():
        df.loc[is_inverter_row, "inverter_id"] = df.loc[is_inverter_row, "device_id"]

    return df[CANONICAL_COLUMNS].reset_index(drop=True)
