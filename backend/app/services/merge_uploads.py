"""Merge multiple SCADA CSV exports into one analysis-ready table.

Naive row-concat breaks when files are plant-level (weather/WMS) vs inverter-level.
This module joins plant/meteo columns onto inverter rows by timestamp, and merges
duplicate plant-level exports side-by-side.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

TIMESTAMP_CANDIDATES = ("Timestamp", "timestamp", "DateTime", "Date Time", "datetime")


def _read_csv(path: Path, nrows: int | None = None) -> pd.DataFrame:
    return pd.read_csv(path, nrows=nrows, low_memory=False)


def _timestamp_col(df: pd.DataFrame) -> str | None:
    for c in TIMESTAMP_CANDIDATES:
        if c in df.columns:
            return c
    return None


def _norm_cols(df: pd.DataFrame) -> set[str]:
    return {str(c).strip().lower().replace("_", "") for c in df.columns}


def _classify(df: pd.DataFrame) -> str:
    cols = _norm_cols(df)
    if "inverter" in cols or any("inverter" in c for c in df.columns):
        return "inverter"
    if any(x in cols for x in ("plantacmw", "plantdcmw", "gridvoltagekv")):
        return "plant"
    if any(x in cols for x in ("poawm2", "poa", "ambienttempc")):
        return "weather"
    return "other"


def _merge_plant_level(dfs: list[pd.DataFrame]) -> pd.DataFrame | None:
    if not dfs:
        return None
    ts = _timestamp_col(dfs[0])
    if not ts:
        return pd.concat(dfs, ignore_index=True)

    out = dfs[0].copy()
    for df in dfs[1:]:
        ts2 = _timestamp_col(df)
        if not ts2:
            continue
        # Drop columns already present (except timestamp) to avoid _x/_y suffix noise
        new_cols = [c for c in df.columns if c == ts2 or c not in out.columns]
        if len(new_cols) <= 1:
            continue
        out = out.merge(df[new_cols], left_on=ts, right_on=ts2, how="outer")
        if ts2 != ts and ts2 in out.columns:
            out = out.drop(columns=[ts2])
    return out


def merge_csv_files(sources: list[Path], dest: Path, manifest_path: Path | None = None) -> tuple[int, list[str]]:
    """Join plant/weather onto inverter rows by timestamp when possible."""
    if not sources:
        raise ValueError("No source files to merge.")

    loaded: list[tuple[str, pd.DataFrame, str]] = []
    names: list[str] = []
    for p in sources:
        if not p.exists():
            continue
        df = _read_csv(p)
        if df.empty:
            continue
        df["_source_file"] = p.name
        kind = _classify(df)
        loaded.append((kind, df, p.name))
        names.append(p.name)

    if not loaded:
        raise ValueError("All uploaded files were empty.")

    inverter_dfs = [df for k, df, _ in loaded if k == "inverter"]
    plant_dfs = [df for k, df, _ in loaded if k in ("plant", "weather", "other")]

    if inverter_dfs and plant_dfs:
        inv = pd.concat(inverter_dfs, ignore_index=True)
        ts_inv = _timestamp_col(inv)
        plant_merged = _merge_plant_level(plant_dfs)
        ts_plant = _timestamp_col(plant_merged) if plant_merged is not None else None
        if ts_inv and ts_plant and plant_merged is not None:
            # Only bring plant columns not already on inverter export
            extra = [c for c in plant_merged.columns if c not in inv.columns or c == ts_plant]
            merged = inv.merge(plant_merged[extra], left_on=ts_inv, right_on=ts_plant, how="left")
            if ts_plant != ts_inv and ts_plant in merged.columns:
                merged = merged.drop(columns=[ts_plant])
        else:
            merged = inv
    elif inverter_dfs:
        merged = pd.concat(inverter_dfs, ignore_index=True)
    elif plant_dfs:
        merged = _merge_plant_level(plant_dfs) or pd.concat(plant_dfs, ignore_index=True)
    else:
        merged = pd.concat([df for _, df, _ in loaded], ignore_index=True)

    # Drop exact duplicate rows
    ts = _timestamp_col(merged)
    id_cols = [c for c in ("Inverter", "inverter_id", "Equipment ID", "device_id") if c in merged.columns]
    if ts and id_cols:
        merged = merged.drop_duplicates(subset=[ts, id_cols[0]], keep="first")
    elif ts:
        merged = merged.drop_duplicates(subset=[ts], keep="first")

    merged.to_csv(dest, index=False)
    if manifest_path:
        manifest_path.write_text(
            json.dumps({"sources": names, "row_count": len(merged), "merge_strategy": "timestamp_join"}, indent=2),
            encoding="utf-8",
        )
    return len(merged), names
