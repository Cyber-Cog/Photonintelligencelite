"""Job-scoped data preview, architecture readout, and Analytics Lab timeseries."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Iterator

import pandas as pd

from analytics.core.context import CANONICAL_COLUMNS, CanonicalDataAccess

SIGNAL_MAP: dict[str, str] = {
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

# Plant/WMS meteo — often joined onto inverter rows in canonical data, but UX lists them under WMS only.
METEO_SIGNALS = frozenset({"poa_w_m2", "ghi_w_m2", "module_temp_c", "ambient_temp_c"})

LEVEL_ID_COL = {
    "inverter": "inverter_id",
    "scb": "scb_id",
    "string": "string_id",
    "wms": "device_id",
}

LEVEL_DEVICE_TYPE = {
    "inverter": "inverter",
    "scb": "scb",
    "string": "string",
}


def _has_canonical(canonical_dir: Path) -> bool:
    return canonical_dir.exists() and any(canonical_dir.rglob("*.parquet"))


def _parquet_files(canonical_dir: Path) -> list[Path]:
    return sorted(canonical_dir.rglob("*.parquet"))


def _partition_num_rows(canonical_dir: Path) -> int:
    import pyarrow.parquet as pq

    total = 0
    for f in _parquet_files(canonical_dir):
        total += pq.ParquetFile(f).metadata.num_rows
    return total


def _iter_partition_frames(
    canonical_dir: Path,
    columns: list[str] | None = None,
) -> Iterator[pd.DataFrame]:
    """Yield partition frames without concatenating the full job into memory."""
    access = CanonicalDataAccess.from_partitions(canonical_dir)
    # Prefer per-device_type reads so we never hold the whole plant at once.
    type_dirs = list(canonical_dir.glob("device_type=*"))
    if not type_dirs:
        df = access.frame(columns=columns)
        if not df.empty:
            yield df
        return
    for d in sorted(type_dirs):
        dtype = d.name.split("=", 1)[1] if "=" in d.name else None
        types = [dtype] if dtype else None
        part = access.frame(columns=columns, device_types=types)
        if not part.empty:
            yield part


def _load_frame(
    canonical_dir: Path,
    raw_csv: Path | None = None,
    columns: list[str] | None = None,
    device_types: list[str] | None = None,
) -> pd.DataFrame:
    if _has_canonical(canonical_dir):
        access = CanonicalDataAccess.from_partitions(canonical_dir)
        return access.frame(columns=columns, device_types=device_types)
    if raw_csv is not None and raw_csv.exists():
        usecols = None
        if columns:
            header = pd.read_csv(raw_csv, nrows=0).columns.tolist()
            usecols = [c for c in columns if c in header] or None
        return pd.read_csv(raw_csv, nrows=50000, usecols=usecols, low_memory=False)
    return pd.DataFrame()


RAW_TS_CANDIDATES = (
    "timestamp_utc",
    "Timestamp",
    "timestamp",
    "DateTime",
    "datetime",
    "Date Time",
    "TIME",
    "Time",
    "Date",
)


def _parse_bound(value: str | None) -> pd.Timestamp | None:
    if not value or not str(value).strip():
        return None
    ts = pd.to_datetime(value, utc=True, errors="coerce")
    if pd.isna(ts):
        return None
    return pd.Timestamp(ts)


def _fmt_bound(ts: pd.Timestamp | None) -> str | None:
    if ts is None or pd.isna(ts):
        return None
    return ts.tz_convert("UTC").strftime("%Y-%m-%dT%H:%M:%S") if ts.tzinfo else ts.strftime("%Y-%m-%dT%H:%M:%S")


def _detect_ts_column(columns: list[str]) -> str | None:
    lower_map = {c.lower(): c for c in columns}
    for cand in RAW_TS_CANDIDATES:
        if cand in columns:
            return cand
        if cand.lower() in lower_map:
            return lower_map[cand.lower()]
    for c in columns:
        cl = c.lower()
        if "time" in cl or "date" in cl:
            return c
    return None


def _apply_time_mask(df: pd.DataFrame, ts_col: str, start: pd.Timestamp | None, end: pd.Timestamp | None) -> pd.DataFrame:
    if ts_col not in df.columns:
        return df.iloc[0:0]
    ts = pd.to_datetime(df[ts_col], utc=True, errors="coerce")
    mask = ts.notna()
    if start is not None:
        mask &= ts >= start
    if end is not None:
        mask &= ts <= end
    return df.loc[mask].copy()


def _format_preview_frame(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in out.columns:
        if pd.api.types.is_datetime64_any_dtype(out[col]):
            series = pd.to_datetime(out[col], utc=True, errors="coerce")
            out[col] = series.dt.strftime("%Y-%m-%d %H:%M:%S").fillna("")
        elif col.lower() in ("timestamp_utc", "timestamp", "datetime") or "time" in col.lower():
            series = pd.to_datetime(out[col], utc=True, errors="coerce")
            if series.notna().any():
                out[col] = series.dt.strftime("%Y-%m-%d %H:%M:%S").fillna(out[col].astype(str))
    return out.fillna("").astype(str)


def _order_columns(columns: list[str]) -> list[str]:
    ordered = [c for c in CANONICAL_COLUMNS if c in columns]
    ordered.extend(c for c in columns if c not in ordered)
    return ordered


def _time_bounds_canonical(canonical_dir: Path) -> tuple[pd.Timestamp | None, pd.Timestamp | None, str | None]:
    access = CanonicalDataAccess.from_partitions(canonical_dir)
    df = access.frame(columns=["timestamp_utc"])
    if df.empty or "timestamp_utc" not in df.columns:
        return None, None, None
    ts = pd.to_datetime(df["timestamp_utc"], utc=True, errors="coerce").dropna()
    if ts.empty:
        return None, None, "timestamp_utc"
    return ts.min(), ts.max(), "timestamp_utc"


def _time_bounds_raw(raw_csv: Path) -> tuple[pd.Timestamp | None, pd.Timestamp | None, str | None]:
    header = pd.read_csv(raw_csv, nrows=0).columns.tolist()
    ts_col = _detect_ts_column([str(c) for c in header])
    if not ts_col:
        return None, None, None
    mins: list[pd.Timestamp] = []
    maxs: list[pd.Timestamp] = []
    for chunk in pd.read_csv(raw_csv, usecols=[ts_col], chunksize=20_000, low_memory=False):
        ts = pd.to_datetime(chunk[ts_col], utc=True, errors="coerce").dropna()
        if not ts.empty:
            mins.append(ts.min())
            maxs.append(ts.max())
    if not mins:
        return None, None, ts_col
    return min(mins), max(maxs), ts_col


def _preview_payload(
    *,
    source: str,
    columns: list[str],
    rows: list[list[str]],
    total_rows: int,
    offset: int,
    limit: int,
    time_column: str | None,
    time_min: pd.Timestamp | None,
    time_max: pd.Timestamp | None,
    start: pd.Timestamp | None,
    end: pd.Timestamp | None,
    unfiltered_rows: int | None = None,
) -> dict[str, Any]:
    return {
        "source": source,
        "columns": columns,
        "rows": rows,
        "total_rows": total_rows,
        "offset": offset,
        "limit": limit,
        "time_column": time_column,
        "time_min": _fmt_bound(time_min),
        "time_max": _fmt_bound(time_max),
        "start": _fmt_bound(start),
        "end": _fmt_bound(end),
        "date_filtered": start is not None or end is not None,
        "unfiltered_rows": unfiltered_rows if unfiltered_rows is not None else total_rows,
    }


def _iter_canonical_row_groups(canonical_dir: Path) -> Iterator[pd.DataFrame]:
    import pyarrow.parquet as pq

    for f in _parquet_files(canonical_dir):
        pf = pq.ParquetFile(f)
        device_type_value = None
        for part in f.parts:
            if part.startswith("device_type="):
                device_type_value = part.split("=", 1)[1]
                break
        for rg in range(pf.num_row_groups):
            df = pf.read_row_group(rg).to_pandas()
            if device_type_value is not None and "device_type" not in df.columns:
                df["device_type"] = device_type_value
            yield df


def _preview_canonical(
    canonical_dir: Path,
    offset: int,
    limit: int,
    start: pd.Timestamp | None,
    end: pd.Timestamp | None,
) -> dict[str, Any]:
    """Paginate canonical parquet; optional start/end filter updates totals."""
    import pyarrow.parquet as pq

    files = _parquet_files(canonical_dir)
    if not files:
        return _preview_payload(
            source="none",
            columns=[],
            rows=[],
            total_rows=0,
            offset=offset,
            limit=limit,
            time_column=None,
            time_min=None,
            time_max=None,
            start=start,
            end=end,
        )

    unfiltered = sum(pq.ParquetFile(f).metadata.num_rows for f in files)
    date_filter = start is not None or end is not None

    time_min, time_max, time_column = (None, None, "timestamp_utc")
    if offset == 0 or date_filter:
        time_min, time_max, time_column = _time_bounds_canonical(canonical_dir)
        time_column = time_column or "timestamp_utc"

    schema_names = list(pq.ParquetFile(files[0]).schema_arrow.names)
    has_device_type_dir = any("device_type=" in str(f) for f in files)
    columns = [*schema_names]
    if has_device_type_dir and "device_type" not in columns:
        columns.append("device_type")
    columns = _order_columns(columns)
    ts_col = time_column or "timestamp_utc"

    matched = 0
    page_chunks: list[pd.DataFrame] = []
    page_needed = limit

    if not date_filter:
        # Fast path: offset into row groups without scanning timestamps.
        skip = offset
        for df in _iter_canonical_row_groups(canonical_dir):
            n = len(df)
            if skip >= n:
                skip -= n
                continue
            if skip:
                df = df.iloc[skip:]
                skip = 0
            if len(df) > page_needed:
                df = df.iloc[:page_needed]
            page_chunks.append(df)
            page_needed -= len(df)
            if page_needed <= 0:
                break
        total_rows = unfiltered
    else:
        for df in _iter_canonical_row_groups(canonical_dir):
            filtered = _apply_time_mask(df, ts_col, start, end)
            n = len(filtered)
            if n == 0:
                continue
            if matched + n <= offset:
                matched += n
                continue
            start_i = max(0, offset - matched)
            take = filtered.iloc[start_i : start_i + page_needed]
            if not take.empty:
                page_chunks.append(take)
                page_needed -= len(take)
            matched += n
            # Continue scanning to finish total_rows count.
        total_rows = matched
        # Finish counting remaining groups if we already filled the page.
        if page_needed <= 0:
            # matched already includes all groups visited; continue for remainder
            pass

    if not page_chunks:
        return _preview_payload(
            source="canonical",
            columns=columns,
            rows=[],
            total_rows=total_rows if date_filter else unfiltered,
            offset=offset,
            limit=limit,
            time_column=time_column,
            time_min=time_min,
            time_max=time_max,
            start=start,
            end=end,
            unfiltered_rows=unfiltered,
        )

    slice_df = pd.concat(page_chunks, ignore_index=True)
    slice_df = slice_df[[c for c in columns if c in slice_df.columns]]
    # Prefer canonical column order
    slice_df = slice_df[_order_columns([str(c) for c in slice_df.columns])]
    formatted = _format_preview_frame(slice_df)
    return _preview_payload(
        source="canonical",
        columns=[str(c) for c in formatted.columns],
        rows=formatted.values.tolist(),
        total_rows=total_rows if date_filter else unfiltered,
        offset=offset,
        limit=limit,
        time_column=time_column,
        time_min=time_min,
        time_max=time_max,
        start=start,
        end=end,
        unfiltered_rows=unfiltered,
    )


def _preview_raw(
    raw_csv: Path,
    offset: int,
    limit: int,
    start: pd.Timestamp | None,
    end: pd.Timestamp | None,
) -> dict[str, Any]:
    if not raw_csv.exists():
        return _preview_payload(
            source="none",
            columns=[],
            rows=[],
            total_rows=0,
            offset=offset,
            limit=limit,
            time_column=None,
            time_min=None,
            time_max=None,
            start=start,
            end=end,
        )

    header = [str(c) for c in pd.read_csv(raw_csv, nrows=0).columns.tolist()]
    time_min, time_max, time_column = _time_bounds_raw(raw_csv)
    date_filter = start is not None or end is not None
    unfiltered = max(0, sum(1 for _ in open(raw_csv, encoding="utf-8", errors="replace")) - 1)

    if not date_filter or not time_column:
        df = pd.read_csv(
            raw_csv,
            skiprows=range(1, offset + 1) if offset else None,
            nrows=limit,
            low_memory=False,
        )
        formatted = _format_preview_frame(df)
        return _preview_payload(
            source="raw",
            columns=[str(c) for c in formatted.columns],
            rows=formatted.values.tolist(),
            total_rows=unfiltered,
            offset=offset,
            limit=limit,
            time_column=time_column,
            time_min=time_min,
            time_max=time_max,
            start=start,
            end=end,
            unfiltered_rows=unfiltered,
        )

    matched = 0
    page_chunks: list[pd.DataFrame] = []
    page_needed = limit
    for chunk in pd.read_csv(raw_csv, chunksize=10_000, low_memory=False):
        filtered = _apply_time_mask(chunk, time_column, start, end)
        n = len(filtered)
        if n == 0:
            continue
        if matched + n <= offset:
            matched += n
            continue
        start_i = max(0, offset - matched)
        take = filtered.iloc[start_i : start_i + page_needed]
        if not take.empty:
            page_chunks.append(take)
            page_needed -= len(take)
        matched += n

    if not page_chunks:
        return _preview_payload(
            source="raw",
            columns=header,
            rows=[],
            total_rows=matched,
            offset=offset,
            limit=limit,
            time_column=time_column,
            time_min=time_min,
            time_max=time_max,
            start=start,
            end=end,
            unfiltered_rows=unfiltered,
        )

    slice_df = pd.concat(page_chunks, ignore_index=True)
    formatted = _format_preview_frame(slice_df)
    return _preview_payload(
        source="raw",
        columns=[str(c) for c in formatted.columns],
        rows=formatted.values.tolist(),
        total_rows=matched,
        offset=offset,
        limit=limit,
        time_column=time_column,
        time_min=time_min,
        time_max=time_max,
        start=start,
        end=end,
        unfiltered_rows=unfiltered,
    )


def preview_data(
    canonical_dir: Path,
    raw_csv: Path,
    offset: int = 0,
    limit: int = 100,
    start: str | None = None,
    end: str | None = None,
) -> dict[str, Any]:
    limit = max(1, min(limit, 500))
    offset = max(0, offset)
    start_ts = _parse_bound(start)
    end_ts = _parse_bound(end)
    if start_ts is not None and end_ts is not None and start_ts > end_ts:
        start_ts, end_ts = end_ts, start_ts

    if _has_canonical(canonical_dir):
        return _preview_canonical(canonical_dir, offset, limit, start_ts, end_ts)
    return _preview_raw(raw_csv, offset, limit, start_ts, end_ts)


def get_architecture_view(
    plant_config: dict | None,
    canonical_dir: Path | None = None,
) -> dict[str, Any]:
    empty = {
        "plant_name": None,
        "inverters": [],
        "summary": {"inverter_count": 0, "scb_count": 0, "string_count": 0},
        "source": "none",
        "hint": "No plant config yet. Finish Setup to save inverter → SCB mapping.",
    }
    if not plant_config:
        # Still try to infer from canonical if available.
        plant: dict[str, Any] = {}
        arch: dict = {}
        ratings: dict = {}
    else:
        plant = plant_config.get("plant") or plant_config
        if not isinstance(plant, dict):
            return {**empty, "hint": "Plant configuration is malformed for this job."}
        arch = plant.get("architecture") or {}
        ratings = plant.get("equipment_ratings") or {}
        if not isinstance(arch, dict):
            arch = {}
        if not isinstance(ratings, dict):
            ratings = {}

    inv_map: dict[str, dict] = {}
    string_total = 0
    for scb_id, entry in arch.items():
        if not isinstance(entry, dict):
            continue
        inv_id = str(entry.get("inverter_id") or "unknown")
        if inv_id not in inv_map:
            rated = ratings.get(inv_id)
            inv_map[inv_id] = {
                "inverter_id": inv_id,
                "rated_kw": float(rated) if rated is not None else None,
                "scbs": [],
            }
        strings = entry.get("strings_per_scb")
        if strings:
            try:
                string_total += int(strings)
            except (TypeError, ValueError):
                pass
        inv_map[inv_id]["scbs"].append(
            {
                "scb_id": str(scb_id),
                "strings_per_scb": strings,
                "modules_per_string": entry.get("modules_per_string"),
                "spare_flag": bool(entry.get("spare_flag")),
            }
        )

    source = "plant_config" if inv_map else "none"
    hint = None

    # Fallback: inverters from ratings with no SCB rows.
    if not inv_map and ratings:
        for inv_id, rated in ratings.items():
            inv_map[str(inv_id)] = {
                "inverter_id": str(inv_id),
                "rated_kw": float(rated) if rated is not None else None,
                "scbs": [],
            }
        source = "ratings"
        hint = "Inverter ratings found, but no SCB mapping was saved. Re-open Setup to add SCBs."

    # Fallback: infer inverter IDs from canonical partitions.
    if not inv_map and canonical_dir is not None and _has_canonical(canonical_dir):
        try:
            access = CanonicalDataAccess.from_partitions(canonical_dir)
            ids = access.equipment_ids("inverter")
            if not ids:
                df = access.frame(columns=["inverter_id"], device_types=["inverter"])
                if "inverter_id" in df.columns:
                    ids = sorted(df["inverter_id"].dropna().astype(str).unique().tolist())
            for inv_id in ids[:200]:
                inv_map[inv_id] = {"inverter_id": inv_id, "rated_kw": None, "scbs": []}
            if inv_map:
                source = "inferred"
                hint = "Architecture was not saved in Setup — showing inverters detected in the dataset."
        except Exception:  # noqa: BLE001
            pass

    inverters = sorted(inv_map.values(), key=lambda x: x["inverter_id"])
    if not inverters:
        return {
            **empty,
            "plant_name": plant.get("plant_name") if plant else None,
            "hint": hint or empty["hint"],
        }

    return {
        "plant_name": plant.get("plant_name"),
        "ac_capacity_mw": plant.get("ac_capacity_mw"),
        "dc_capacity_mwp": plant.get("dc_capacity_mwp"),
        "module_rating_wp": plant.get("module_rating_wp"),
        "timezone": plant.get("timezone"),
        "inverters": inverters,
        "summary": {
            "inverter_count": len(inverters),
            "scb_count": sum(len(i["scbs"]) for i in inverters),
            "string_count": string_total or None,
        },
        "source": source,
        "hint": hint,
    }


def list_equipment(canonical_dir: Path, raw_csv: Path, level: str) -> list[str]:
    if _has_canonical(canonical_dir):
        access = CanonicalDataAccess.from_partitions(canonical_dir)
        if level == "wms":
            try:
                wms_ids = access.equipment_ids("wms")
            except Exception:  # noqa: BLE001
                wms_ids = []
            if wms_ids:
                return wms_ids[:500]
            # Joined weather path: no WMS device rows, but POA may exist on inverter rows.
            df = access.frame(columns=["poa_w_m2", "ghi_w_m2"])
            if "poa_w_m2" in df.columns and df["poa_w_m2"].notna().any():
                return ["POA (joined)"]
            if "ghi_w_m2" in df.columns and df["ghi_w_m2"].notna().any():
                return ["GHI (joined)"]
            return []

        dtype = LEVEL_DEVICE_TYPE.get(level)
        col = LEVEL_ID_COL.get(level, "inverter_id")
        cols = list({col, "device_id", "device_type"})
        df = access.frame(columns=cols, device_types=[dtype] if dtype else None)
        if df.empty:
            return []
        if col not in df.columns:
            col = "device_id" if "device_id" in df.columns else None
        if not col:
            return []
        sub = df[df[col].notna() & (df[col].astype(str).str.len() > 0)]
        return sorted(sub[col].astype(str).unique().tolist())[:500]

    df = _load_frame(canonical_dir, raw_csv)
    if df.empty:
        return []
    for col in ("Inverter", "Equipment ID", "device_id", "Equipment", "inverter_id"):
        if col in df.columns:
            return sorted(df[col].dropna().astype(str).unique().tolist())[:500]
    return []


def list_signals(canonical_dir: Path, raw_csv: Path, level: str) -> list[dict[str, str]]:
    if _has_canonical(canonical_dir):
        access = CanonicalDataAccess.from_partitions(canonical_dir)
        # Only pull signal columns (+ ids) — not the full wide frame repeatedly.
        probe_cols = [c for c in CANONICAL_COLUMNS if c not in ("timestamp_utc",)]
        dtype = None if level == "wms" else LEVEL_DEVICE_TYPE.get(level)
        # For WMS / meteo, check weather columns on any partition (often joined onto inverter).
        df = access.frame(columns=probe_cols, device_types=[dtype] if dtype else None)
        if df.empty and level == "wms":
            df = access.frame(columns=probe_cols)
        if df.empty:
            return []
        available = [
            c
            for c in CANONICAL_COLUMNS
            if c in df.columns
            and c not in ("timestamp_utc", "device_id", "device_type", "inverter_id", "scb_id", "string_id")
            and df[c].notna().any()
        ]
        if level == "wms":
            available = [c for c in available if c in METEO_SIGNALS]
        else:
            # Keep electrical signals only; meteo stays on the WMS tab even when joined onto device rows.
            available = [c for c in available if c not in METEO_SIGNALS]
        return [{"id": s, "label": SIGNAL_MAP.get(s, s.replace("_", " "))} for s in available]

    df = _load_frame(canonical_dir, raw_csv)
    if df.empty:
        return []
    return [{"id": c, "label": c} for c in df.columns if c not in ("_source_file",)][:30]


def query_timeseries(
    canonical_dir: Path,
    raw_csv: Path,
    equipment_ids: list[str],
    signals: list[str],
    max_points: int = 3000,
    start: str | None = None,
    end: str | None = None,
) -> dict[str, Any]:
    max_points = max(100, min(max_points, 8000))
    start_ts = _parse_bound(start)
    end_ts = _parse_bound(end)
    if start_ts is not None and end_ts is not None and start_ts > end_ts:
        start_ts, end_ts = end_ts, start_ts

    if not _has_canonical(canonical_dir):
        df = _load_frame(canonical_dir, raw_csv)
        if df.empty:
            return {"series": [], "point_count": 0}
        return {
            "series": [],
            "point_count": 0,
            "note": "Timeseries explorer requires completed analysis (canonical data). Finish setup and run analysis first.",
        }

    # Load only the columns needed for the plot.
    id_cols = ["inverter_id", "scb_id", "string_id", "device_id", "device_type"]
    need = ["timestamp_utc", *id_cols, *[s for s in signals if s in SIGNAL_MAP or s in CANONICAL_COLUMNS]]
    seen: set[str] = set()
    cols: list[str] = []
    for c in need:
        if c not in seen:
            seen.add(c)
            cols.append(c)

    access = CanonicalDataAccess.from_partitions(canonical_dir)
    df = access.frame(columns=cols)
    if df.empty:
        return {"series": [], "point_count": 0}

    ts_col = "timestamp_utc"
    if ts_col not in df.columns:
        return {"series": [], "point_count": 0}

    df[ts_col] = pd.to_datetime(df[ts_col], utc=True, errors="coerce")
    df = df.dropna(subset=[ts_col])
    if start_ts is not None:
        df = df[df[ts_col] >= start_ts]
    if end_ts is not None:
        df = df[df[ts_col] <= end_ts]
    if df.empty:
        return {
            "series": [],
            "point_count": 0,
            "note": "No points in the selected date range.",
            "start": _fmt_bound(start_ts),
            "end": _fmt_bound(end_ts),
        }

    # Synthetic POA / GHI series for joined weather
    synth = {"POA (joined)": "poa_w_m2", "GHI (joined)": "ghi_w_m2"}
    series_out: list[dict[str, Any]] = []
    point_count = 0
    for label, sig in synth.items():
        if label not in equipment_ids or sig not in signals:
            continue
        if sig not in df.columns:
            continue
        sub = df[[ts_col, sig]].dropna(subset=[sig]).drop_duplicates(ts_col).sort_values(ts_col)
        if len(sub) > max_points:
            sub = sub.iloc[:: max(1, len(sub) // max_points)]
        series_out.append(
            {
                "name": SIGNAL_MAP.get(sig, sig),
                "equipment_id": label,
                "signal": sig,
                "timestamps": sub[ts_col].dt.strftime("%Y-%m-%d %H:%M:%S").tolist(),
                "values": pd.to_numeric(sub[sig], errors="coerce").round(4).tolist(),
            }
        )
        point_count += len(sub)

    real_ids = [e for e in equipment_ids if e not in synth]
    if real_ids:
        present_id_cols = [c for c in id_cols if c in df.columns and c != "device_type"]
        mask = pd.Series(False, index=df.index)
        for col in present_id_cols:
            mask |= df[col].astype(str).isin(real_ids)
        sub = df[mask].copy()
        if not sub.empty:
            sub = sub.sort_values(ts_col)
            if len(sub) > max_points * max(1, len(real_ids)):
                step = max(1, len(sub) // (max_points * max(1, len(real_ids))))
                sub = sub.iloc[::step]

            for eq in real_ids:
                for sig in signals:
                    if sig not in sub.columns:
                        continue
                    eq_mask = pd.Series(False, index=sub.index)
                    for col in present_id_cols:
                        eq_mask |= sub[col].astype(str) == eq
                    chunk = sub[eq_mask]
                    if chunk.empty:
                        continue
                    y = pd.to_numeric(chunk[sig], errors="coerce")
                    valid = y.notna()
                    if not valid.any():
                        continue
                    idx = chunk.index[valid]
                    if len(idx) > max_points:
                        step = max(1, len(idx) // max_points)
                        idx = idx[::step]
                    series_out.append(
                        {
                            "name": f"{eq} · {SIGNAL_MAP.get(sig, sig)}",
                            "equipment_id": eq,
                            "signal": sig,
                            "timestamps": chunk.loc[idx, ts_col].dt.strftime("%Y-%m-%d %H:%M:%S").tolist(),
                            "values": y.loc[idx].round(4).tolist(),
                        }
                    )
                    point_count += len(idx)

    return {
        "series": series_out,
        "point_count": point_count,
        "start": _fmt_bound(start_ts),
        "end": _fmt_bound(end_ts),
    }


def export_csv_path(canonical_dir: Path, raw_csv: Path) -> tuple[Path | None, str]:
    """Prefer raw input.csv; otherwise None (caller may stream a generated export)."""
    if raw_csv.exists():
        return raw_csv, "raw"
    if _has_canonical(canonical_dir):
        return None, "canonical"
    return None, "none"


def export_data_csv_bytes(
    canonical_dir: Path,
    raw_csv: Path,
    start: str | None = None,
    end: str | None = None,
    max_rows: int = 200_000,
) -> bytes:
    """CSV export with optional date window (row-capped)."""
    start_ts = _parse_bound(start)
    end_ts = _parse_bound(end)
    if start_ts is not None and end_ts is not None and start_ts > end_ts:
        start_ts, end_ts = end_ts, start_ts
    date_filter = start_ts is not None or end_ts is not None

    if _has_canonical(canonical_dir):
        remaining = max_rows
        chunks: list[pd.DataFrame] = []
        for part in _iter_partition_frames(canonical_dir):
            if remaining <= 0:
                break
            if date_filter and "timestamp_utc" in part.columns:
                part = _apply_time_mask(part, "timestamp_utc", start_ts, end_ts)
            if part.empty:
                continue
            take = part.iloc[:remaining]
            chunks.append(take)
            remaining -= len(take)
        if not chunks:
            return b""
        return pd.concat(chunks, ignore_index=True).to_csv(index=False).encode("utf-8")

    if not raw_csv.exists():
        return b""
    header = [str(c) for c in pd.read_csv(raw_csv, nrows=0).columns.tolist()]
    ts_col = _detect_ts_column(header)
    if not date_filter or not ts_col:
        # Full raw file (capped)
        df = pd.read_csv(raw_csv, nrows=max_rows, low_memory=False)
        return df.to_csv(index=False).encode("utf-8")

    remaining = max_rows
    chunks: list[pd.DataFrame] = []
    for chunk in pd.read_csv(raw_csv, chunksize=10_000, low_memory=False):
        if remaining <= 0:
            break
        filtered = _apply_time_mask(chunk, ts_col, start_ts, end_ts)
        if filtered.empty:
            continue
        take = filtered.iloc[:remaining]
        chunks.append(take)
        remaining -= len(take)
    if not chunks:
        return b""
    return pd.concat(chunks, ignore_index=True).to_csv(index=False).encode("utf-8")


def export_canonical_csv_bytes(canonical_dir: Path, max_rows: int = 100_000) -> bytes:
    """Build a CSV export from canonical partitions (row-capped for safety)."""
    return export_data_csv_bytes(canonical_dir, Path(), start=None, end=None, max_rows=max_rows)
