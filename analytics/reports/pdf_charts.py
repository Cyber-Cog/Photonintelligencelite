"""Matplotlib → PNG helpers for PDF reports.

Renders ChartSpec figures and the energy-loss bridge as static images so the PDF
mirrors Results visuals without kaleido/Chromium. Palette matches the UI
(amber / emerald / rose / stone — no default matplotlib blue).
"""
from __future__ import annotations

import io
from datetime import datetime
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyBboxPatch, Patch  # noqa: E402
from reportlab.lib.units import cm  # noqa: E402
from reportlab.platypus import Image as RLImage  # noqa: E402

from analytics.core.result import ChartSpec  # noqa: E402
from analytics.reports.loss_bridge import BridgeModel  # noqa: E402

# UI palette (chartTheme / LossWaterfallBridge)
_STONE = "#44403c"
_STONE_MUTED = "#78716c"
_STONE_BORDER = "#d6d3d1"
_STONE_BG = "#fafaf9"
_EXPECTED = "#57534e"
_ACTUAL = "#047857"
_LOSS = "#dc2626"
_UNKNOWN = "#78716c"
_AMBER = "#d97706"
_AMBER_LINE = "#b45309"
_FAULT_BAND = (0.863, 0.149, 0.149, 0.14)  # rgba(220,38,38,0.14)
_INFO_BAND = (0.851, 0.467, 0.024, 0.12)  # rgba(217,119,6,0.12)
_PALETTE = ["#d97706", "#059669", "#dc2626", "#a16207", "#047857", "#e11d48", "#ca8a04", "#16a34a"]

_MAX_TS_POINTS = 900
_MAX_BAR_CATS = 16
_MAX_BOX_CATS = 20
_FIG_W_IN = 7.2
_CONTENT_W = 16.5 * cm


def _apply_style(ax) -> None:
    ax.set_facecolor(_STONE_BG)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color(_STONE_BORDER)
    ax.spines["bottom"].set_color(_STONE_BORDER)
    ax.tick_params(colors=_STONE_MUTED, labelsize=8)
    ax.yaxis.label.set_color(_STONE_MUTED)
    ax.xaxis.label.set_color(_STONE_MUTED)
    ax.grid(axis="y", color=_STONE_BORDER, linewidth=0.6, alpha=0.85)
    ax.set_axisbelow(True)


def _fig_to_image(fig, *, max_width: float = _CONTENT_W) -> RLImage:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=140, bbox_inches="tight", facecolor="white", edgecolor="none")
    plt.close(fig)
    buf.seek(0)
    img = RLImage(buf)
    aspect = float(img.imageHeight) / float(img.imageWidth) if img.imageWidth else 0.45
    img.drawWidth = max_width
    img.drawHeight = max_width * aspect
    # Cap height so a single chart never dominates a page awkwardly
    max_h = 11.5 * cm
    if img.drawHeight > max_h:
        scale = max_h / img.drawHeight
        img.drawWidth *= scale
        img.drawHeight = max_h
    return img


def _segment_fill(seg) -> str:
    if seg.key == "actual":
        return _ACTUAL
    if seg.key == "expected":
        return _EXPECTED
    if seg.kind == "unknown":
        return _UNKNOWN
    return _LOSS


def _truncate(label: str, max_len: int = 18) -> str:
    s = str(label)
    return s if len(s) <= max_len else s[: max_len - 1] + "…"


def render_waterfall(model: BridgeModel) -> RLImage | None:
    """Stacked bridge chart: invisible spacer + coloured visible segment."""
    segments = model.segments
    if not segments:
        return None
    n = len(segments)
    fig_h = max(3.2, min(5.2, 2.4 + n * 0.22))
    fig, ax = plt.subplots(figsize=(_FIG_W_IN, fig_h))
    _apply_style(ax)

    labels = [_truncate(s.label, 16) for s in segments]
    invis = [s.invisible for s in segments]
    vis = [s.visible for s in segments]
    fills = [_segment_fill(s) for s in segments]
    x = list(range(n))

    ax.bar(x, invis, color="none", edgecolor="none", width=0.62)
    ax.bar(x, vis, bottom=invis, color=fills, edgecolor=(0.11, 0.1, 0.09, 0.12), linewidth=0.6, width=0.62)

    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=28 if n > 5 else 12, ha="right", fontsize=7.5)
    ax.set_ylabel("MWh", fontsize=9)
    ax.set_xlim(-0.6, n - 0.4)
    ymax = max((s.invisible + s.visible for s in segments), default=1.0) or 1.0
    ax.set_ylim(0, ymax * 1.08)

    legend = [
        Patch(facecolor=_EXPECTED, label="Expected"),
        Patch(facecolor=_LOSS, label="Fault diagnostics"),
        Patch(facecolor=_UNKNOWN, label="Unknown"),
        Patch(facecolor=_ACTUAL, label="Actual"),
    ]
    ax.legend(handles=legend, loc="upper right", frameon=False, fontsize=7.5, ncol=2)
    fig.tight_layout()
    return _fig_to_image(fig)


def _axis_title(layout: dict, axis: str) -> str:
    ax = layout.get(axis) or {}
    if not isinstance(ax, dict):
        return ""
    title = ax.get("title")
    if isinstance(title, dict):
        return str(title.get("text") or "")
    if isinstance(title, str):
        return title
    return ""


def _parse_time(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    s = str(value).strip()
    if not s:
        return None
    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%d",
    ):
        try:
            return datetime.strptime(s.replace("Z", "").split("+")[0][:26], fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00").replace("+00:00", ""))
    except ValueError:
        return None


def _downsample(xs: list, ys: list, max_points: int = _MAX_TS_POINTS) -> tuple[list, list]:
    n = len(xs)
    if n <= max_points or n == 0:
        return xs, ys
    step = max(1, n // max_points)
    return xs[::step], ys[::step]


def _trace_color(trace: dict, index: int) -> str:
    line = trace.get("line") or {}
    if isinstance(line, dict) and isinstance(line.get("color"), str) and line["color"].startswith("#"):
        return line["color"]
    marker = trace.get("marker") or {}
    if isinstance(marker, dict):
        c = marker.get("color")
        if isinstance(c, str) and c.startswith("#"):
            return c
    return _PALETTE[index % len(_PALETTE)]


def _band_facecolor(shape: dict) -> tuple:
    fill = str(shape.get("fillcolor") or "")
    if "217,119,6" in fill or "217, 119, 6" in fill:
        return _INFO_BAND
    return _FAULT_BAND


def _shade_fault_bands(ax, layout: dict, x_are_dates: bool) -> None:
    shapes = layout.get("shapes") or []
    if not isinstance(shapes, list):
        return
    for shape in shapes:
        if not isinstance(shape, dict) or shape.get("type") != "rect":
            continue
        x0, x1 = shape.get("x0"), shape.get("x1")
        if x0 is None or x1 is None:
            continue
        facecolor = _band_facecolor(shape)
        if x_are_dates:
            t0, t1 = _parse_time(x0), _parse_time(x1)
            if t0 is None or t1 is None:
                continue
            ax.axvspan(t0, t1, facecolor=facecolor, edgecolor="none", zorder=0)
        else:
            # Categorical / string x — try index match later; skip if not numeric
            try:
                ax.axvspan(float(x0), float(x1), facecolor=facecolor, edgecolor="none", zorder=0)
            except (TypeError, ValueError):
                # Match string timestamps against converted dates already on axis
                t0, t1 = _parse_time(x0), _parse_time(x1)
                if t0 and t1:
                    ax.axvspan(t0, t1, facecolor=facecolor, edgecolor="none", zorder=0)


def _shade_bands_on_string_axis(ax, layout: dict, xs: list) -> None:
    """Shade fault intervals when x is categorical time strings."""
    shapes = layout.get("shapes") or []
    if not isinstance(shapes, list) or not xs:
        return
    index = {str(v): i for i, v in enumerate(xs)}
    # Also index by truncated/normalized forms
    for shape in shapes:
        if not isinstance(shape, dict) or shape.get("type") != "rect":
            continue
        x0, x1 = str(shape.get("x0", "")), str(shape.get("x1", ""))
        i0 = index.get(x0)
        i1 = index.get(x1)
        if i0 is None:
            # fuzzy: prefix match on date-hour
            for k, i in index.items():
                if x0[:16] and k.startswith(x0[:16]):
                    i0 = i
                    break
        if i1 is None:
            for k, i in index.items():
                if x1[:16] and k.startswith(x1[:16]):
                    i1 = i
                    break
        if i0 is None or i1 is None:
            t0, t1 = _parse_time(x0), _parse_time(x1)
            if t0 and t1:
                # find nearest indices by parsing all xs once
                parsed = [_parse_time(v) for v in xs]
                valid = [(i, t) for i, t in enumerate(parsed) if t is not None]
                if not valid:
                    continue
                i0 = min(valid, key=lambda p: abs((p[1] - t0).total_seconds()))[0]
                i1 = min(valid, key=lambda p: abs((p[1] - t1).total_seconds()))[0]
            else:
                continue
        if i1 < i0:
            i0, i1 = i1, i0
        ax.axvspan(i0 - 0.5, i1 + 0.5, facecolor=_FAULT_BAND, edgecolor="none", zorder=0)


def _numeric_ys(values: list) -> list[float]:
    out: list[float] = []
    for v in values:
        if v is None:
            continue
        try:
            out.append(float(v))
        except (TypeError, ValueError):
            continue
    return out


def _is_near_empty_numeric(ys: list[float], *, min_abs: float = 1e-9) -> bool:
    """True when there is nothing meaningful to plot (empty or all ~zero)."""
    if not ys:
        return True
    return all(abs(v) < min_abs or v != v for v in ys)  # noqa: PLR0124 — NaN check


def _render_bar(chart: ChartSpec) -> RLImage | None:
    data = chart.figure.get("data") or []
    if not data:
        return None
    layout = chart.figure.get("layout") or {}
    fig, ax = plt.subplots(figsize=(_FIG_W_IN, 3.4))
    _apply_style(ax)

    plotted = False
    for i, raw in enumerate(data[:3]):
        if not isinstance(raw, dict):
            continue
        xs = list(raw.get("x") or [])[:_MAX_BAR_CATS]
        ys_raw = list(raw.get("y") or [])[:_MAX_BAR_CATS]
        if not xs or not ys_raw:
            continue
        n = min(len(xs), len(ys_raw))
        xs, ys = xs[:n], [float(v) if v is not None else 0.0 for v in ys_raw[:n]]
        if _is_near_empty_numeric(ys):
            continue
        color = _trace_color(raw, i)
        # If marker.color is a list, use first / cycle
        marker = raw.get("marker") or {}
        if isinstance(marker, dict) and isinstance(marker.get("color"), list):
            colors = [c if isinstance(c, str) else color for c in marker["color"][:n]]
            ax.bar(range(n), ys, color=colors, width=0.65, edgecolor="none")
        else:
            ax.bar(range(n), ys, color=color, width=0.65, edgecolor="none", label=raw.get("name") or None)
        ax.set_xticks(range(n))
        ax.set_xticklabels([_truncate(str(x), 14) for x in xs], rotation=28 if n > 5 else 0, ha="right" if n > 5 else "center", fontsize=7.5)
        plotted = True

    if not plotted:
        plt.close(fig)
        return None

    y_title = _axis_title(layout, "yaxis") or "Value"
    ax.set_ylabel(y_title, fontsize=9)
    fig.tight_layout()
    return _fig_to_image(fig)


def _render_line_or_diagnostic(chart: ChartSpec) -> RLImage | None:
    data = chart.figure.get("data") or []
    layout = chart.figure.get("layout") or {}
    if not data:
        return None

    fig, ax = plt.subplots(figsize=(_FIG_W_IN, 3.6 if chart.chart_type == "diagnostic" else 3.3))
    _apply_style(ax)

    # Determine shared x from first series with data
    primary_x: list = []
    for raw in data:
        if isinstance(raw, dict) and raw.get("x"):
            primary_x = list(raw["x"])
            break
    if not primary_x:
        plt.close(fig)
        return None

    parsed = [_parse_time(v) for v in primary_x]
    use_dates = sum(1 for t in parsed if t is not None) >= max(3, len(primary_x) // 2)

    plotted = 0
    ax2 = None
    for i, raw in enumerate(data[:8]):
        if not isinstance(raw, dict):
            continue
        xs = list(raw.get("x") or [])
        ys = list(raw.get("y") or [])
        if not xs or not ys:
            continue
        n = min(len(xs), len(ys))
        xs, ys = xs[:n], ys[:n]
        ys_f = [float(v) if v is not None else float("nan") for v in ys]
        if not any(v == v for v in ys_f):  # all NaN
            continue
        color = _trace_color(raw, i)
        name = str(raw.get("name") or f"Series {i + 1}")
        width = 2.0 if i == 0 else 1.5
        on_y2 = str(raw.get("yaxis") or "").endswith("2")
        target = ax
        if on_y2:
            if ax2 is None:
                ax2 = ax.twinx()
                ax2.tick_params(axis="y", labelsize=7, colors=_STONE_MUTED)
                ax2.spines["top"].set_visible(False)
            target = ax2
            width = 1.25

        if use_dates:
            txs = [_parse_time(v) for v in xs]
            pairs = [(t, y) for t, y in zip(txs, ys_f) if t is not None]
            if not pairs:
                continue
            txs2, ys2 = zip(*pairs)
            txs2, ys2 = _downsample(list(txs2), list(ys2))
            target.plot(txs2, ys2, color=color, linewidth=width, label=name, linestyle=":" if on_y2 else "-")
        else:
            xs_d, ys_d = _downsample(xs, ys_f)
            target.plot(range(len(xs_d)), ys_d, color=color, linewidth=width, label=name, linestyle=":" if on_y2 else "-")
        plotted += 1

    if plotted == 0:
        plt.close(fig)
        return None

    if use_dates:
        _shade_fault_bands(ax, layout, x_are_dates=True)
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d %H:%M"))
        fig.autofmt_xdate(rotation=25, ha="right")
    else:
        _shade_bands_on_string_axis(ax, layout, primary_x)
        # Sparse tick labels
        n = len(primary_x)
        step = max(1, n // 8)
        ticks = list(range(0, n, step))
        ax.set_xticks(ticks)
        ax.set_xticklabels([_truncate(str(primary_x[i]), 12) for i in ticks], rotation=25, ha="right", fontsize=7)

    y_title = _axis_title(layout, "yaxis") or "Value"
    ax.set_ylabel(y_title, fontsize=9)
    if ax2 is not None:
        y2_title = _axis_title(layout, "yaxis2") or "Irradiance (W/m²)"
        ax2.set_ylabel(y2_title, fontsize=8, color=_STONE_MUTED)
    if chart.chart_type == "diagnostic":
        handles, labels = ax.get_legend_handles_labels()
        if ax2 is not None:
            h2, l2 = ax2.get_legend_handles_labels()
            handles, labels = handles + h2, labels + l2
        if handles:
            ax.legend(handles, labels, loc="upper right", frameon=False, fontsize=7.5)
        # Tiny caption for fault / info bands
        ax.text(
            0.0,
            1.02,
            "Red = classified fault · Amber = at rating (not classified)",
            transform=ax.transAxes,
            fontsize=7,
            color=_STONE_MUTED,
            va="bottom",
        )
    elif plotted > 1:
        ax.legend(loc="best", frameon=False, fontsize=7.5)

    fig.tight_layout()
    return _fig_to_image(fig)


def _render_box(chart: ChartSpec) -> RLImage | None:
    data = chart.figure.get("data") or []
    layout = chart.figure.get("layout") or {}
    if not data:
        return None
    trace = data[0] if isinstance(data[0], dict) else {}
    names = list(trace.get("x") or [])
    if not names:
        return None

    fig, ax = plt.subplots(figsize=(_FIG_W_IN, 3.5))
    _apply_style(ax)

    # Precomputed quartiles
    if "q1" in trace and "median" in trace:
        cats = names[:_MAX_BOX_CATS]
        q1 = [float(v) for v in (trace.get("q1") or [])[: len(cats)]]
        med = [float(v) for v in (trace.get("median") or [])[: len(cats)]]
        q3 = [float(v) for v in (trace.get("q3") or [])[: len(cats)]]
        lo = [float(v) for v in (trace.get("lowerfence") or trace.get("min") or q1)[: len(cats)]]
        hi = [float(v) for v in (trace.get("upperfence") or trace.get("max") or q3)[: len(cats)]]
        n = min(len(cats), len(q1), len(med), len(q3), len(lo), len(hi))
        if n == 0:
            plt.close(fig)
            return None
        stats = []
        for i in range(n):
            stats.append(
                {
                    "label": _truncate(str(cats[i]), 12),
                    "whislo": lo[i],
                    "q1": q1[i],
                    "med": med[i],
                    "q3": q3[i],
                    "whishi": hi[i],
                    "fliers": [],
                }
            )
        bp = ax.bxp(stats, showfliers=False, patch_artist=True)
        for patch in bp.get("boxes", []):
            patch.set_facecolor((0.851, 0.467, 0.024, 0.28))
            patch.set_edgecolor(_AMBER_LINE)
        for med_line in bp.get("medians", []):
            med_line.set_color(_AMBER_LINE)
    else:
        # Sample-based: x categorical, y samples
        ys = list(trace.get("y") or [])
        if not ys or len(ys) != len(names):
            # Flattened categorical form: many rows per category
            from collections import defaultdict

            buckets: dict[str, list[float]] = defaultdict(list)
            for x, y in zip(names, ys if ys else []):
                if y is None:
                    continue
                try:
                    buckets[str(x)].append(float(y))
                except (TypeError, ValueError):
                    continue
            order = list(dict.fromkeys(str(x) for x in names))[:_MAX_BOX_CATS]
            series = [buckets[c] for c in order if buckets[c]]
            labels = [_truncate(c, 12) for c in order if buckets[c]]
            if not series:
                plt.close(fig)
                return None
            bp = ax.boxplot(series, tick_labels=labels, showfliers=False, patch_artist=True)
            for patch in bp["boxes"]:
                patch.set_facecolor((0.851, 0.467, 0.024, 0.28))
                patch.set_edgecolor(_AMBER_LINE)
            for med in bp["medians"]:
                med.set_color(_AMBER_LINE)
        else:
            plt.close(fig)
            return None

    ax.tick_params(axis="x", labelrotation=28 if len(ax.get_xticklabels()) > 6 else 0, labelsize=7.5)
    y_title = _axis_title(layout, "yaxis") or "Value"
    ax.set_ylabel(y_title, fontsize=9)
    fig.tight_layout()
    return _fig_to_image(fig)


def _render_timeline(chart: ChartSpec) -> RLImage | None:
    data = chart.figure.get("data") or []
    if not data:
        return None
    fig, ax = plt.subplots(figsize=(_FIG_W_IN, 2.8))
    _apply_style(ax)
    equip_order: list[str] = []
    for i, raw in enumerate(data[:40]):
        if not isinstance(raw, dict):
            continue
        xs = list(raw.get("x") or [])
        ys = list(raw.get("y") or [])
        if len(xs) < 2 or not ys:
            continue
        eq = str(ys[0])
        if eq not in equip_order:
            equip_order.append(eq)
        y = equip_order.index(eq)
        t0, t1 = _parse_time(xs[0]), _parse_time(xs[1] if len(xs) > 1 else xs[0])
        color = _trace_color(raw, i)
        if t0 and t1:
            ax.plot([t0, t1], [y, y], color=color, linewidth=4, solid_capstyle="round")
            ax.scatter([t0, t1], [y, y], color=color, s=18, zorder=3)
        else:
            ax.plot([0, 1], [y, y], color=color, linewidth=4)

    if not equip_order:
        plt.close(fig)
        return None
    ax.set_yticks(range(len(equip_order)))
    ax.set_yticklabels([_truncate(e, 22) for e in equip_order], fontsize=8)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d"))
    fig.autofmt_xdate(rotation=25, ha="right")
    ax.set_xlabel("Time", fontsize=9)
    fig.tight_layout()
    return _fig_to_image(fig)


def chart_has_plottable_data(chart: ChartSpec) -> bool:
    """Cheap pre-check: ChartSpec carries at least one non-empty trace."""
    data = chart.figure.get("data") or []
    if not data:
        return False
    ctype = (chart.chart_type or "").lower()
    for raw in data:
        if not isinstance(raw, dict):
            continue
        if raw.get("q1") and raw.get("median"):
            return True
        if raw.get("z"):
            return True
        xs = list(raw.get("x") or [])
        ys = list(raw.get("y") or [])
        if ctype == "bar":
            nums = _numeric_ys(ys)
            if xs and nums and not _is_near_empty_numeric(nums):
                return True
            continue
        if xs and ys and any(v is not None for v in ys):
            return True
        if ys and any(v is not None for v in ys):
            return True
    return False


def render_chart_spec(chart: ChartSpec) -> RLImage | None:
    """Render a ChartSpec to a ReportLab Image, or None if data is empty/unsupported."""
    ctype = (chart.chart_type or "").lower()
    if not chart_has_plottable_data(chart):
        return None

    try:
        if ctype == "bar":
            return _render_bar(chart)
        if ctype in ("line", "diagnostic", "scatter"):
            return _render_line_or_diagnostic(chart)
        if ctype == "box":
            return _render_box(chart)
        if ctype == "timeline":
            return _render_timeline(chart)
        # Fallback: try line-like if x/y present
        data = chart.figure.get("data") or []
        if any(isinstance(t, dict) and t.get("y") for t in data):
            return _render_line_or_diagnostic(chart)
    except Exception:  # noqa: BLE001 — never fail the whole PDF for one chart
        plt.close("all")
        return None
    return None


def render_kpi_strip_figure(cards: list[tuple[str, str, str | None]]) -> RLImage | None:
    """Draw a row of metric cards as a figure (label, value, optional tone: good|bad|None)."""
    if not cards:
        return None
    n = len(cards)
    fig_w = min(7.4, 1.1 + n * 1.15)
    fig, ax = plt.subplots(figsize=(fig_w, 1.15))
    ax.set_xlim(0, n)
    ax.set_ylim(0, 1)
    ax.axis("off")
    fig.patch.set_facecolor("white")

    for i, (label, value, tone) in enumerate(cards):
        x0 = i + 0.06
        box = FancyBboxPatch(
            (x0, 0.08),
            0.88,
            0.84,
            boxstyle="round,pad=0.02,rounding_size=0.08",
            linewidth=0.8,
            edgecolor=_STONE_BORDER,
            facecolor="white",
            transform=ax.transData,
            clip_on=False,
        )
        ax.add_patch(box)
        val_color = _ACTUAL if tone == "good" else (_LOSS if tone == "bad" else _STONE)
        ax.text(i + 0.5, 0.72, label.upper(), ha="center", va="center", fontsize=5.5, color=_STONE_MUTED, fontweight="bold")
        ax.text(i + 0.5, 0.38, value, ha="center", va="center", fontsize=11, color=val_color, fontweight="semibold")

    fig.tight_layout(pad=0.15)
    return _fig_to_image(fig, max_width=_CONTENT_W)
