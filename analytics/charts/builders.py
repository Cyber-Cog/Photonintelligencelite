"""Plotly figure builders shared by every algorithm.

Each builder returns a ChartSpec whose `figure` is a plain-JSON Plotly figure dict
(`{"data": [...], "layout": {...}}`), consumable directly by react-plotly.js on the
frontend, and by the PDF builder (which re-renders ChartSpec statically via matplotlib).
Keeping this in one module means every chart shares consistent styling
across all 8 algorithms + KPI dashboard.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any

from analytics.core.result import ChartSpec

# Amber / emerald / rose brand palette — no blue / purple defaults.
_PALETTE = ["#d97706", "#059669", "#dc2626", "#a16207", "#047857", "#e11d48", "#ca8a04", "#16a34a"]
_BOX_LINE = "#b45309"
_BOX_FILL = "rgba(217, 119, 6, 0.28)"
_BOX_MARKER = "rgba(217, 119, 6, 0.35)"
_BASE_LAYOUT: dict[str, Any] = {
    "font": {"family": "DM Sans, Segoe UI, system-ui, sans-serif", "size": 12},
    "margin": {"l": 64, "r": 28, "t": 48, "b": 72},
    "paper_bgcolor": "rgba(0,0,0,0)",
    "plot_bgcolor": "rgba(250,250,249,0.85)",
    "hovermode": "closest",
    "legend": {"orientation": "h", "y": -0.22, "x": 0, "font": {"size": 11}},
}

# YYYY-MM-DD[ T]HH:MM[:SS] with optional fractional seconds / timezone.
_DATETIME_LIKE = re.compile(
    r"^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}(:\d{2}(\.\d+)?)?(Z|[+-]\d{2}:?\d{2})?$"
)


def to_plotly_time_x(values: list) -> list[str]:
    """Serialize timestamps as ISO-8601 strings for Plotly date axes.

    Plotly parses ``2026-01-03T06:00:00`` reliably; space-separated labels and raw
    datetime objects are normalized here so algorithms can pass either.
    """
    out: list[str] = []
    for v in values:
        if v is None or (isinstance(v, float) and v != v):  # NaN
            continue
        if hasattr(v, "to_pydatetime"):
            v = v.to_pydatetime()
        if isinstance(v, datetime):
            if v.tzinfo is not None:
                v = v.astimezone(timezone.utc).replace(tzinfo=None)
            out.append(v.strftime("%Y-%m-%dT%H:%M:%S"))
            continue
        s = str(v).strip()
        if not s or s.lower() == "nat":
            continue
        s = s.replace(" ", "T", 1)
        m = re.match(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2})?)", s)
        if not m:
            continue
        s = m.group(1)
        if len(s) == 16:  # YYYY-MM-DDTHH:MM
            s = f"{s}:00"
        out.append(s)
    return out


def _looks_like_time_x(values: list) -> bool:
    if not values:
        return False
    sample = values[0]
    if sample is None:
        return False
    if isinstance(sample, datetime) or hasattr(sample, "to_pydatetime"):
        return True
    return bool(_DATETIME_LIKE.match(str(sample).strip()))


def _parse_iso_naive(s: str) -> datetime | None:
    try:
        cleaned = s.strip().replace(" ", "T", 1)
        if cleaned.endswith("Z"):
            cleaned = cleaned[:-1]
        if len(cleaned) > 19 and cleaned[19] in "+-":
            cleaned = cleaned[:19]
        elif len(cleaned) > 19 and cleaned[19] == ".":
            cleaned = cleaned[:19]
        if len(cleaned) == 16:
            cleaned = f"{cleaned}:00"
        return datetime.strptime(cleaned[:19], "%Y-%m-%dT%H:%M:%S")
    except ValueError:
        return None


def _layout(title: str, x_title: str = "", y_title: str = "", extra: dict | None = None) -> dict:
    layout = dict(_BASE_LAYOUT)
    layout["title"] = {"text": title, "font": {"size": 14, "color": "#0f172a"}, "x": 0.01, "xanchor": "left"}
    layout["xaxis"] = {
        "title": {"text": x_title, "font": {"size": 12}},
        "gridcolor": "rgba(148,163,184,0.28)",
        "zeroline": False,
        "showline": True,
        "linecolor": "rgba(100,116,139,0.45)",
        "tickfont": {"size": 11},
    }
    layout["yaxis"] = {
        "title": {"text": y_title, "font": {"size": 12}},
        "gridcolor": "rgba(148,163,184,0.28)",
        "zeroline": False,
        "showline": True,
        "linecolor": "rgba(100,116,139,0.45)",
        "tickfont": {"size": 11},
    }
    if extra:
        # Deep-merge axis dicts so callers can override without wiping titles
        for key in ("xaxis", "yaxis", "yaxis2"):
            if key in extra and isinstance(extra[key], dict) and isinstance(layout.get(key), dict):
                merged = dict(layout[key])
                merged.update(extra[key])
                extra = {**extra, key: merged}
        layout.update(extra)
    return layout


def line_chart(
    chart_id: str,
    title: str,
    x: list,
    series: dict[str, list[float]],
    x_title: str = "Time",
    y_title: str = "Value",
) -> ChartSpec:
    """Build a time/category line chart.

    Time-like x values are normalized to ISO-8601 strings with ``xaxis.type=date``.
    Markers are always included so a single sample remains visible (Plotly ``lines``
    alone draws nothing for one point and collapses the date axis to ~2 ms).
    """
    x_vals: list = list(x)
    axis_extra: dict[str, Any] = {}
    if _looks_like_time_x(x_vals):
        x_vals = to_plotly_time_x(x_vals)
        axis_extra["xaxis"] = {"type": "date"}
        # Single timestamp → pad ±12h so autorange does not show a microsecond window.
        if len(x_vals) == 1:
            t = _parse_iso_naive(x_vals[0])
            if t is not None:
                axis_extra["xaxis"]["range"] = [
                    (t - timedelta(hours=12)).strftime("%Y-%m-%dT%H:%M:%S"),
                    (t + timedelta(hours=12)).strftime("%Y-%m-%dT%H:%M:%S"),
                ]
        elif len(set(x_vals)) == 1:
            t = _parse_iso_naive(x_vals[0])
            if t is not None:
                axis_extra["xaxis"]["range"] = [
                    (t - timedelta(hours=12)).strftime("%Y-%m-%dT%H:%M:%S"),
                    (t + timedelta(hours=12)).strftime("%Y-%m-%dT%H:%M:%S"),
                ]

    data = [
        {
            "type": "scatter",
            "mode": "lines+markers",
            "name": name,
            "x": x_vals,
            "y": y,
            "line": {"color": _PALETTE[i % len(_PALETTE)]},
            "marker": {"size": 6, "color": _PALETTE[i % len(_PALETTE)]},
        }
        for i, (name, y) in enumerate(series.items())
    ]
    return ChartSpec(
        chart_id=chart_id,
        title=title,
        chart_type="line",
        figure={"data": data, "layout": _layout(title, x_title, y_title, extra=axis_extra or None)},
    )


def bar_chart(
    chart_id: str,
    title: str,
    categories: list[str],
    values: list[float],
    x_title: str = "",
    y_title: str = "Value",
    color: str | None = None,
) -> ChartSpec:
    data = [{"type": "bar", "x": categories, "y": values, "marker": {"color": color or _PALETTE[0]}}]
    return ChartSpec(chart_id=chart_id, title=title, chart_type="bar", figure={"data": data, "layout": _layout(title, x_title, y_title)})


def box_plot_chart(
    chart_id: str,
    title: str,
    box_stats: list[dict[str, Any]],
    y_title: str = "Efficiency (%)",
    samples_by_name: dict[str, list[float]] | None = None,
) -> ChartSpec:
    """Build a Plotly box plot that actually renders for multi-inverter plants.

    Prefer ``samples_by_name`` (raw efficiency points) — Plotly computes quartiles reliably.
    Fall back to precomputed ``box_stats`` items:
    ``{"name": str, "min", "q1", "median", "q3", "max"}`` using a single categorical trace
    (PIC-style: one series, many inverters on the x-axis).
    """
    names = [str(s["name"]) for s in box_stats]
    n = len(names)
    rotate = -35 if n > 6 else 0
    bottom_margin = 110 if rotate else 72
    # Stable height — width is handled responsively on the frontend (scroll for many inverters).
    height = 400 if n > 8 else 380

    if samples_by_name:
        # Flatten to categorical box: x=inverter, y=efficiency samples (engineering-software style).
        x_vals: list[str] = []
        y_vals: list[float] = []
        for name in names:
            pts = samples_by_name.get(name) or []
            # Cap points per inverter so large jobs stay browser-friendly
            if len(pts) > 2500:
                step = max(1, len(pts) // 2500)
                pts = pts[::step]
            x_vals.extend([name] * len(pts))
            y_vals.extend(pts)
        data = [
            {
                "type": "box",
                "name": "Efficiency",
                "x": x_vals,
                "y": y_vals,
                "boxpoints": False,
                "marker": {"color": _BOX_MARKER},
                "line": {"color": _BOX_LINE, "width": 1.5},
                "fillcolor": _BOX_FILL,
                "hovertemplate": "%{x}<br>Efficiency: %{y:.2f}%<extra></extra>",
            }
        ]
    else:
        # Precomputed quartiles — one trace with parallel arrays (Plotly precomputed API).
        data = [
            {
                "type": "box",
                "name": "Efficiency",
                "x": names,
                "q1": [float(s["q1"]) for s in box_stats],
                "median": [float(s["median"]) for s in box_stats],
                "q3": [float(s["q3"]) for s in box_stats],
                "lowerfence": [float(s["min"]) for s in box_stats],
                "upperfence": [float(s["max"]) for s in box_stats],
                "boxpoints": False,
                "marker": {"color": _BOX_MARKER},
                "line": {"color": _BOX_LINE, "width": 1.5},
                "fillcolor": _BOX_FILL,
                "hovertemplate": (
                    "%{x}<br>Max: %{upperfence}<br>Q3: %{q3}<br>"
                    "<b>Median: %{median}</b><br>Q1: %{q1}<br>Min: %{lowerfence}<extra></extra>"
                ),
            }
        ]

    # Annotate whisker/box meaning like the PIC dashboard caption
    annotations = [
        {
            "text": "Whiskers: Min–Max · Box: Q1–Q3 · Line: Median (per-inverter efficiency)",
            "xref": "paper",
            "yref": "paper",
            "x": 0.5,
            "y": -0.06,
            "yshift": 0,
            "showarrow": False,
            "font": {"size": 10, "color": "#78716c"},
        }
    ]

    layout = _layout(
        title,
        "Inverter",
        y_title,
        extra={
            "height": height,
            "margin": {"l": 68, "r": 24, "t": 40, "b": bottom_margin},
            "xaxis": {
                "title": {"text": "Inverter", "font": {"size": 12}},
                "tickangle": rotate,
                "categoryorder": "array",
                "categoryarray": names,
                "automargin": True,
            },
            "yaxis": {
                "title": {"text": y_title, "font": {"size": 12}},
                "ticksuffix": "%",
                "rangemode": "tozero",
                "automargin": True,
            },
            "showlegend": False,
            "annotations": annotations,
            "hovermode": "closest",
        },
    )
    return ChartSpec(chart_id=chart_id, title=title, chart_type="box", figure={"data": data, "layout": layout})


def heatmap_chart(
    chart_id: str,
    title: str,
    x: list[str],
    y: list[str],
    z: list[list[float]],
    colorscale: str = "YlOrRd",
) -> ChartSpec:
    data = [{"type": "heatmap", "x": x, "y": y, "z": z, "colorscale": colorscale}]
    return ChartSpec(chart_id=chart_id, title=title, chart_type="heatmap", figure={"data": data, "layout": _layout(title)})


def diagnostic_line_chart(
    chart_id: str,
    title: str,
    x: list,
    series: dict[str, list[float | None]],
    fault_bands: list[dict[str, str]] | None = None,
    info_bands: list[dict[str, str]] | None = None,
    secondary_series: dict[str, list[float | None]] | None = None,
    x_title: str = "Time",
    y_title: str = "Value",
    y2_title: str = "",
    rule_text: str = "",
) -> ChartSpec:
    """Reference vs actual with optional shaded fault windows (PIC Fault Diagnostics style).

    ``fault_bands`` → red classified-fault shading. ``info_bands`` → amber context shading
    (e.g. at rating but not classified). ``secondary_series`` plot on ``yaxis2`` (right).
    """
    x_vals: list = list(x)
    if _looks_like_time_x(x_vals):
        x_vals = to_plotly_time_x(x_vals)

    data = [
        {
            "type": "scatter",
            "mode": "lines",
            "name": name,
            "x": x_vals,
            "y": y,
            "line": {"color": _PALETTE[i % len(_PALETTE)], "width": 2 if i == 0 else 1.5},
        }
        for i, (name, y) in enumerate(series.items())
    ]
    n_primary = len(data)
    for j, (name, y) in enumerate((secondary_series or {}).items()):
        data.append(
            {
                "type": "scatter",
                "mode": "lines",
                "name": name,
                "x": x_vals,
                "y": y,
                "yaxis": "y2",
                "line": {
                    "color": _PALETTE[(n_primary + j) % len(_PALETTE)],
                    "width": 1.25,
                    "dash": "dot",
                },
            }
        )

    def _band_shape(band: dict[str, str], fillcolor: str) -> dict[str, Any]:
        x0, x1 = band["start"], band["end"]
        if _looks_like_time_x([x0, x1]):
            iso = to_plotly_time_x([x0, x1])
            if len(iso) == 2:
                x0, x1 = iso[0], iso[1]
        return {
            "type": "rect",
            "xref": "x",
            "yref": "paper",
            "x0": x0,
            "x1": x1,
            "y0": 0,
            "y1": 1,
            "fillcolor": fillcolor,
            "line": {"width": 0},
        }

    shapes: list[dict[str, Any]] = []
    # Amber info bands under red fault bands so classified windows stay dominant.
    for band in info_bands or []:
        shapes.append(_band_shape(band, "rgba(217,119,6,0.10)"))
    for band in fault_bands or []:
        shapes.append(_band_shape(band, "rgba(220,38,38,0.12)"))
    annotations = []
    if rule_text:
        annotations.append(
            {
                "text": rule_text,
                "xref": "paper",
                "yref": "paper",
                "x": 0,
                "y": 1.14,
                "showarrow": False,
                "font": {"size": 10, "color": "#64748b"},
                "align": "left",
            }
        )
    extra: dict[str, Any] = {
        "shapes": shapes,
        "annotations": annotations,
        "height": 440,
        "margin": {"l": 64, "r": 56 if secondary_series else 28, "t": 64, "b": 72},
    }
    if _looks_like_time_x(x_vals):
        extra["xaxis"] = {"type": "date"}
    if secondary_series:
        extra["yaxis2"] = {
            "title": {"text": y2_title or "Irradiance (W/m²)", "font": {"size": 12}},
            "overlaying": "y",
            "side": "right",
            "showgrid": False,
            "zeroline": False,
            "tickfont": {"size": 11},
        }
    return ChartSpec(
        chart_id=chart_id,
        title=title,
        chart_type="diagnostic",
        figure={"data": data, "layout": _layout(title, x_title, y_title, extra=extra)},
    )


def timeline_chart(
    chart_id: str,
    title: str,
    events: list[dict[str, Any]],
) -> ChartSpec:
    """`events` items: {"equipment_id", "start", "end", "kind"}."""
    data = [
        {
            "type": "scatter",
            "mode": "markers",
            "name": e["kind"],
            "x": [e["start"], e["end"]],
            "y": [e["equipment_id"], e["equipment_id"]],
            "marker": {"size": 8, "color": _PALETTE[i % len(_PALETTE)]},
        }
        for i, e in enumerate(events)
    ]
    return ChartSpec(chart_id=chart_id, title=title, chart_type="timeline", figure={"data": data, "layout": _layout(title, "Time", "Equipment")})
