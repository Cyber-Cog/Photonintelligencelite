"""PDF report generation.

Uses ReportLab (docs/PRD.md §25) plus matplotlib for static chart images that mirror
the Results UI: KPI strip, energy-loss bridge, ChartSpec bar/line/box/diagnostic/
timeline figures (including red fault-band shading). Interactive Plotly zoom is not
embedded — that remains a dashboard feature.
"""
from __future__ import annotations

import io
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from analytics.core.result import ChartSpec, ResultObject, ResultStatus
from analytics.reports.loss_bridge import BridgeModel, build_loss_bridge
from analytics.reports.owner_brief import OwnerBrief, build_owner_brief
from analytics.reports.pdf_charts import (
    chart_has_plottable_data,
    render_chart_spec,
    render_waterfall,
)
from analytics.reports.report_data import ReportContext

_STYLES = getSampleStyleSheet()
# Amber / emerald / stone — match Results UI (no blue).
_AMBER = colors.HexColor("#b45309")
_AMBER_DARK = colors.HexColor("#92400e")
_AMBER_SOFT = colors.HexColor("#fffbeb")
_EMERALD = colors.HexColor("#047857")
_ROSE = colors.HexColor("#dc2626")
_STONE = colors.HexColor("#44403c")
_STONE_MUTED = colors.HexColor("#78716c")
_STONE_BORDER = colors.HexColor("#d6d3d1")
_STONE_SOFT = colors.HexColor("#f5f5f4")
_ROW_BG = colors.HexColor("#fafaf9")
_TITLE_STYLE = ParagraphStyle(
    "PicTitle",
    parent=_STYLES["Title"],
    textColor=_STONE,
    fontSize=20,
    leading=24,
    spaceAfter=4,
)
_COVER_SUB = ParagraphStyle(
    "PicCoverSub",
    parent=_STYLES["BodyText"],
    textColor=_STONE_MUTED,
    fontSize=10,
    leading=13,
    spaceAfter=2,
)
_H2_STYLE = ParagraphStyle(
    "PicH2",
    parent=_STYLES["Heading2"],
    textColor=_AMBER_DARK,
    fontSize=13,
    spaceBefore=16,
    spaceAfter=8,
    borderPadding=2,
)
_H3_STYLE = ParagraphStyle(
    "PicH3",
    parent=_STYLES["Heading3"],
    textColor=_STONE,
    fontSize=11,
    spaceBefore=10,
    spaceAfter=4,
)
_BODY_STYLE = ParagraphStyle("PicBody", parent=_STYLES["BodyText"], leading=14, textColor=_STONE, fontSize=9)
_MUTED_STYLE = ParagraphStyle("PicMuted", parent=_STYLES["BodyText"], textColor=_STONE_MUTED, fontSize=8, leading=11)
_CAPTION_STYLE = ParagraphStyle(
    "PicCaption",
    parent=_STYLES["BodyText"],
    textColor=_STONE_MUTED,
    fontSize=8,
    leading=10,
    spaceBefore=2,
    spaceAfter=6,
)
_KPI_LABEL = ParagraphStyle("KpiLabel", parent=_STYLES["Normal"], textColor=_STONE_MUTED, fontSize=7, leading=9, alignment=1)
_KPI_VALUE = ParagraphStyle("KpiValue", parent=_STYLES["Normal"], textColor=_STONE, fontSize=11, leading=13, alignment=1, fontName="Helvetica-Bold")
_KPI_VALUE_GOOD = ParagraphStyle("KpiValueGood", parent=_KPI_VALUE, textColor=_EMERALD)
_KPI_VALUE_BAD = ParagraphStyle("KpiValueBad", parent=_KPI_VALUE, textColor=_ROSE)
_STATUS_HEALTHY = ParagraphStyle(
    "PicStatusHealthy",
    parent=_STYLES["Normal"],
    textColor=_EMERALD,
    fontSize=12,
    leading=15,
    fontName="Helvetica-Bold",
    spaceBefore=4,
    spaceAfter=2,
)
_STATUS_ATTENTION = ParagraphStyle(
    "PicStatusAttention",
    parent=_STATUS_HEALTHY,
    textColor=_AMBER_DARK,
)
_STATUS_CRITICAL = ParagraphStyle(
    "PicStatusCritical",
    parent=_STATUS_HEALTHY,
    textColor=_ROSE,
)
_BRIEF_LABEL = ParagraphStyle(
    "PicBriefLabel",
    parent=_STYLES["Normal"],
    textColor=_AMBER_DARK,
    fontSize=9,
    leading=11,
    fontName="Helvetica-Bold",
    spaceBefore=8,
    spaceAfter=3,
)
_BRIEF_ITEM = ParagraphStyle(
    "PicBriefItem",
    parent=_STYLES["BodyText"],
    textColor=_STONE,
    fontSize=9,
    leading=12,
    leftIndent=4,
    spaceAfter=3,
)
_BRIEF_IMPACT = ParagraphStyle(
    "PicBriefImpact",
    parent=_STYLES["BodyText"],
    textColor=_ROSE,
    fontSize=8,
    leading=10,
    leftIndent=12,
    spaceAfter=4,
)

_TABLE_HEADER_BG = _AMBER_DARK
_MAX_TABLE_ROWS = 25
_CONTENT_W = 16.5 * cm
_MARGIN = 1.8 * cm

# Recommendation lines that add noise without operational value
_NOISE_REC_FRAGMENTS = (
    "no dc current clipping",
    "no power clipping events",
    "no sustained voltage-deviation",
    "no distributional outliers",
    "tight and consistent across inverters",
    "this is a v1 algorithm",
    "treat magnitudes as directional",
    "no events detected",
    "no inverter showed",
    "no scb/mppt showed",
)


def _styled_table(header: list[str], rows: list[list], col_widths: list[float] | None = None) -> Table:
    data = [header] + rows
    t = Table(data, colWidths=col_widths, hAlign="LEFT", repeatRows=1)
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), _TABLE_HEADER_BG),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8.0),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, _ROW_BG]),
                ("GRID", (0, 0), (-1, -1), 0.4, _STONE_BORDER),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    return t


def _fmt(value: Any, decimals: int = 2, suffix: str = "") -> str:
    if value is None:
        return "Not available"
    try:
        return f"{value:.{decimals}f}{suffix}"
    except (TypeError, ValueError):
        return str(value)


def _cell(value: Any, decimals: int = 2) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:.{decimals}f}"
    return str(value)


def _time_window(result: ResultObject) -> str:
    ev = result.evidence
    if ev.time_range_start and ev.time_range_end:
        return f"{ev.time_range_start[:16]} → {ev.time_range_end[:16]}"
    if ev.time_range_start:
        return str(ev.time_range_start)[:16]
    return "—"


def _analysis_date_range(results: list[ResultObject]) -> str | None:
    starts: list[str] = []
    ends: list[str] = []
    for r in results:
        if r.evidence.time_range_start:
            starts.append(str(r.evidence.time_range_start)[:10])
        if r.evidence.time_range_end:
            ends.append(str(r.evidence.time_range_end)[:10])
    if starts and ends:
        return f"{min(starts)} – {max(ends)}"
    if starts:
        return min(starts)
    return None


def _col_index(columns: list[str], *candidates: str) -> int | None:
    lower = {c.lower(): i for i, c in enumerate(columns)}
    for cand in candidates:
        if cand.lower() in lower:
            return lower[cand.lower()]
    return None


def _has_table_rows(r: ResultObject) -> bool:
    return any(t.rows for t in r.tables)


def _plottable_charts(r: ResultObject) -> list[ChartSpec]:
    return [c for c in list(r.charts) + list(r.evidence_charts) if chart_has_plottable_data(c)]


def _has_real_findings(r: ResultObject) -> bool:
    """Confirmed issues: loss, affected equipment, or non-empty finding tables with severity."""
    if r.status != ResultStatus.OK:
        return False
    if (r.loss_energy_kwh or 0) > 0:
        return True
    if r.affected_equipment:
        return True
    sev = (r.severity or "").lower()
    if sev in ("low", "medium", "high", "critical") and _has_table_rows(r):
        return True
    return False


def _has_meaningful_metrics(r: ResultObject) -> bool:
    """Non-trivial metrics worth a detail section (e.g. efficiency distributions)."""
    if not r.metrics:
        return False
    for key, val in r.metrics.items():
        lk = key.lower()
        if "count" in lk and (val or 0) > 0:
            # Skip pure "analyzed N units / 0 outliers" noise unless other signals exist
            if "outlier" in lk or "clip" in lk or "fault" in lk or "affected" in lk:
                return True
        if "efficiency" in lk or "loss" in lk:
            return True
    return False


def _worth_detail_section(r: ResultObject) -> bool:
    """Include in Fault-wise Analysis only when there is real content for the reader."""
    if r.status != ResultStatus.OK:
        return False
    if _has_real_findings(r):
        return True
    # Diagnostic modules (box plot / efficiency) with plottable charts + meaningful metrics
    if _plottable_charts(r) and (_has_meaningful_metrics(r) or _has_table_rows(r)):
        # Still skip pure "nothing detected" info cards with empty tables
        if (r.severity or "").lower() == "info" and not _has_table_rows(r) and not (r.loss_energy_kwh or 0):
            return False
        return True
    return False


def _is_noise_recommendation(text: str) -> bool:
    low = text.lower().strip()
    if not low:
        return True
    if any(frag in low for frag in _NOISE_REC_FRAGMENTS):
        return True
    if low.startswith("no ") and ("detected" in low or "showed" in low or "require action" in low):
        return True
    return False


def _actionable_recommendations(recs: list[str], *, limit: int = 3) -> list[str]:
    out: list[str] = []
    for rec in recs:
        if _is_noise_recommendation(rec):
            continue
        out.append(rec)
        if len(out) >= limit:
            break
    return out


def _fault_rows_from_results(results: list[ResultObject]) -> list[list[str]]:
    """Flatten OK findings into unified fault rows for the PDF table."""
    rows: list[list[str]] = []
    for r in results:
        if r.status != ResultStatus.OK:
            continue
        window = _time_window(r)
        severity = r.severity or "—"
        if not r.tables:
            if (r.loss_energy_kwh or 0) > 0 or r.affected_equipment:
                equip = ", ".join(r.affected_equipment[:3]) if r.affected_equipment else "—"
                if len(r.affected_equipment) > 3:
                    equip += "…"
                rows.append(
                    [
                        r.title,
                        equip,
                        severity,
                        _fmt(r.loss_energy_kwh, 2) if r.loss_energy_kwh is not None else "—",
                        window,
                        "Confirmed",
                    ]
                )
            continue
        # Only emit fault rows for modules with real findings (skip distribution-only tables)
        if not _has_real_findings(r):
            continue
        for table in r.tables:
            eq_i = _col_index(table.columns, "SCB", "SCB/MPPT", "Inverter", "Unit", "Equipment")
            loss_i = _col_index(table.columns, "Loss (kWh)", "Estimated loss (kWh)", "Loss")
            inv_i = _col_index(table.columns, "Inverter")
            kind_i = _col_index(table.columns, "Fault kind")
            for raw in table.rows:
                equipment = _cell(raw[eq_i]) if eq_i is not None and eq_i < len(raw) else "—"
                if inv_i is not None and inv_i != eq_i and inv_i < len(raw) and eq_i is not None:
                    pass
                loss = _cell(raw[loss_i], 2) if loss_i is not None and loss_i < len(raw) else _fmt(r.loss_energy_kwh, 2)
                fault_type = r.title
                if kind_i is not None and kind_i < len(raw) and raw[kind_i]:
                    fault_type = f"{r.title} ({raw[kind_i]})"
                rows.append([fault_type, equipment, severity, loss, window, "Confirmed"])
    return rows


def _status_style(status: str) -> ParagraphStyle:
    if status == "Critical":
        return _STATUS_CRITICAL
    if status == "Healthy":
        return _STATUS_HEALTHY
    return _STATUS_ATTENTION


def _fmt_impact_kwh(kwh: float | None) -> str | None:
    if kwh is None or kwh <= 0:
        return None
    return f"Impact ≈ {kwh:,.1f} kWh estimated loss"


def _cover_banner(ctx: ReportContext, brief: OwnerBrief) -> Table:
    """Page-1 owner executive brief: plant, status, top problems, next steps."""
    date_range = _analysis_date_range(ctx.run.results)
    meta_bits = [
        f"Job <b>{ctx.job_id}</b>",
        f"Generated {ctx.generated_at}",
    ]
    if date_range:
        meta_bits.append(f"Analysis window <b>{date_range}</b>")
    meta = " · ".join(meta_bits)

    inner: list[list] = [
        [Paragraph("Photon Intelligence Center Lite · Solar Performance Analysis", _MUTED_STYLE)],
        [Paragraph(ctx.plant.plant_name, _TITLE_STYLE)],
        [Paragraph(f"Status: {brief.status}", _status_style(brief.status))],
        [Paragraph(brief.status_detail, _COVER_SUB)],
        [Paragraph(meta, _COVER_SUB)],
    ]

    if brief.problems:
        inner.append([Paragraph("Top problems", _BRIEF_LABEL)])
        for i, p in enumerate(brief.problems, start=1):
            inner.append([Paragraph(f"{i}. {p.problem}", _BRIEF_ITEM)])
            impact = _fmt_impact_kwh(p.impact_kwh)
            if impact:
                inner.append([Paragraph(impact, _BRIEF_IMPACT)])
    else:
        inner.append([Paragraph("Top problems", _BRIEF_LABEL)])
        inner.append(
            [
                Paragraph(
                    "No confirmed performance problems in this run. KPIs and diagnostics follow below.",
                    _BRIEF_ITEM,
                )
            ]
        )

    if brief.next_steps:
        inner.append([Paragraph("What to do next", _BRIEF_LABEL)])
        for step in brief.next_steps:
            inner.append([Paragraph(f"&bull; {step}", _BRIEF_ITEM)])

    t = Table(inner, colWidths=[_CONTENT_W])
    n = len(inner)
    style_cmds = [
        ("BACKGROUND", (0, 0), (-1, -1), _AMBER_SOFT),
        ("BOX", (0, 0), (-1, -1), 1.2, _AMBER),
        ("LEFTPADDING", (0, 0), (-1, -1), 14),
        ("RIGHTPADDING", (0, 0), (-1, -1), 14),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        # Brand row
        ("TOPPADDING", (0, 0), (0, 0), 12),
        ("BOTTOMPADDING", (0, 0), (0, 0), 2),
        # Plant name
        ("TOPPADDING", (0, 1), (0, 1), 4),
        ("BOTTOMPADDING", (0, 1), (0, 1), 2),
        # Status + detail + meta
        ("TOPPADDING", (0, 2), (0, 4), 2),
        ("BOTTOMPADDING", (0, 2), (0, 4), 2),
        # Last row breathing room
        ("BOTTOMPADDING", (0, n - 1), (0, n - 1), 12),
        ("TOPPADDING", (0, 5), (0, n - 1), 1),
        ("BOTTOMPADDING", (0, 5), (0, n - 2), 1),
    ]
    t.setStyle(TableStyle(style_cmds))
    return t


def _kpi_strip(ctx: ReportContext) -> list:
    """Styled KPI metric cards (2 rows × 4) mirroring the Results strip."""
    k = ctx.run.kpis
    loss = k.get("estimated_energy_loss_kwh")
    revenue = k.get("revenue_loss_inr")
    revenue_txt = (
        _fmt(revenue, 0)
        if k.get("revenue_loss_available") and revenue is not None
        else "—"
    )
    gap = 0.2 * cm
    card_w = (_CONTENT_W - 3 * gap) / 4

    def _row(cards: list) -> Table:
        t = Table([cards], colWidths=[card_w] * 4)
        t.setStyle(
            TableStyle(
                [
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ]
            )
        )
        return t

    def _cards(specs: list[tuple[str, str, str | None]]) -> list:
        out = []
        for label, value, tone in specs:
            value_style = _KPI_VALUE
            if tone == "good":
                value_style = _KPI_VALUE_GOOD
            elif tone == "bad":
                value_style = _KPI_VALUE_BAD
            cell = Table(
                [[Paragraph(label, _KPI_LABEL)], [Paragraph(value, value_style)]],
                colWidths=[card_w],
            )
            cell.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, -1), colors.white),
                        ("BOX", (0, 0), (-1, -1), 0.6, _STONE_BORDER),
                        ("TOPPADDING", (0, 0), (-1, -1), 7),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                        ("LEFTPADDING", (0, 0), (-1, -1), 3),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ]
                )
            )
            out.append(cell)
        return out

    row1_specs: list[tuple[str, str, str | None]] = [
        ("Availability %", _fmt(k.get("plant_availability_pct"), 1), None),
        ("Performance ratio %", _fmt(k.get("performance_ratio_pct"), 1), "good"),
        ("Specific yield kWh/kWp", _fmt(k.get("specific_yield_kwh_per_kwp"), 2), None),
        ("Total AC energy kWh", _fmt(k.get("total_ac_energy_kwh"), 0), None),
    ]
    row2_specs: list[tuple[str, str, str | None]] = [
        ("Energy loss kWh", _fmt(loss, 1) if loss is not None else "—", "bad" if (loss or 0) > 0 else None),
        ("Revenue loss ₹", revenue_txt, "bad" if k.get("revenue_loss_available") else None),
        ("Faults detected", str(k.get("fault_count", 0)), "bad" if (k.get("fault_count") or 0) > 0 else "good"),
        (
            "Modules with findings",
            f"{sum(1 for r in ctx.run.results if _has_real_findings(r))}/{len(ctx.run.results)}",
            None,
        ),
    ]

    story_bits: list = []
    story_bits.append(_row(_cards(row1_specs)))
    story_bits.append(Spacer(1, 4))
    story_bits.append(_row(_cards(row2_specs)))
    return story_bits


def _bridge_summary_cards(bridge: BridgeModel) -> Table | None:
    if bridge.mode != "bridge":
        return None
    pr_pct = (bridge.actual_mwh / bridge.expected_mwh * 100.0) if bridge.expected_mwh > 0 else None
    specs = [
        ("Expected", f"{_fmt(bridge.expected_mwh, 3)} MWh", None),
        ("Actual", f"{_fmt(bridge.actual_mwh, 3)} MWh", "good"),
        ("PR", f"{_fmt(pr_pct, 1)}%" if pr_pct is not None else "—", None),
        ("Unknown", f"{_fmt(bridge.unknown_mwh, 3)} MWh", None),
    ]
    gap = 0.2 * cm
    card_w = (_CONTENT_W - 3 * gap) / 4
    cells = []
    for label, value, tone in specs:
        vs = _KPI_VALUE_GOOD if tone == "good" else _KPI_VALUE
        cell = Table(
            [[Paragraph(label, _KPI_LABEL)], [Paragraph(value, vs)]],
            colWidths=[card_w],
        )
        cell.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), _STONE_SOFT),
                    ("BOX", (0, 0), (-1, -1), 0.5, _STONE_BORDER),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ]
            )
        )
        cells.append(cell)
    t = Table([cells], colWidths=[card_w] * 4)
    t.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
    return t


def _append_charts(story: list, charts: list[ChartSpec], *, max_charts: int = 4, caption_prefix: str = "") -> int:
    """Embed ChartSpec figures; return count rendered. Skips empty/unrenderable specs."""
    rendered = 0
    for chart in charts:
        if rendered >= max_charts:
            break
        if not chart_has_plottable_data(chart):
            continue
        img = render_chart_spec(chart)
        if img is None:
            continue
        title = chart.title or chart.chart_id
        block = [
            Paragraph(f"{caption_prefix}{title}" if caption_prefix else title, _CAPTION_STYLE),
            img,
            Spacer(1, 6),
        ]
        story.append(KeepTogether(block))
        rendered += 1
    return rendered


def _append_result_section(story: list, r: ResultObject, *, include_finding_tables: bool) -> None:
    """Per-module detail. Finding tables are omitted when already covered by All Faults."""
    header_bits = [
        Paragraph(
            f"{r.title}"
            + (f"  <font size=8 color='#78716c'>· {r.severity}</font>" if r.severity else ""),
            _H3_STYLE,
        ),
        Paragraph(r.summary, _BODY_STYLE),
    ]

    meta_bits = []
    if r.loss_energy_kwh is not None and (r.loss_energy_kwh or 0) > 0:
        meta_bits.append(f"Loss: {_fmt(r.loss_energy_kwh, 2)} kWh")
    if r.loss_revenue is not None and (r.loss_revenue or 0) > 0:
        meta_bits.append(f"Revenue: ₹{_fmt(r.loss_revenue, 0)}")
    if r.affected_equipment:
        shown = ", ".join(r.affected_equipment[:6])
        if len(r.affected_equipment) > 6:
            shown += "…"
        meta_bits.append(f"Equipment: {shown}")
    if r.evidence.time_range_start:
        meta_bits.append(f"Window: {_time_window(r)}")
    if meta_bits:
        header_bits.append(Paragraph(" · ".join(meta_bits), _MUTED_STYLE))

    # Compact metrics — skip trivial zero counts
    metric_rows = []
    for k, v in r.metrics.items():
        if v is None:
            continue
        if "count" in k.lower() and float(v) == 0:
            continue
        metric_rows.append([k.replace("_", " ").title(), _fmt(v, 2)])
    if metric_rows:
        header_bits.append(Spacer(1, 4))
        header_bits.append(_styled_table(["Metric", "Value"], metric_rows[:8], col_widths=[9 * cm, 7.5 * cm]))

    story.append(KeepTogether(header_bits))

    # Finding tables only when not already listed in the unified All Faults table
    # (diagnostic distribution tables e.g. box plot are still useful here).
    if include_finding_tables or not _has_real_findings(r):
        for table in r.tables:
            if not table.rows:
                continue
            story.append(Paragraph(table.title, _CAPTION_STYLE))
            capped = table.rows[:_MAX_TABLE_ROWS]
            display_rows = [[_cell(c) for c in row] for row in capped]
            col_w = [_CONTENT_W / max(len(table.columns), 1)] * len(table.columns)
            story.append(_styled_table(table.columns, display_rows, col_widths=col_w))
            if len(table.rows) > _MAX_TABLE_ROWS:
                story.append(
                    Paragraph(
                        f"+{len(table.rows) - _MAX_TABLE_ROWS} more row(s) omitted — see Excel report.",
                        _MUTED_STYLE,
                    )
                )
            story.append(Spacer(1, 6))

    summary_charts = [c for c in r.charts if c.chart_type != "heatmap" and chart_has_plottable_data(c)]
    _append_charts(story, summary_charts, max_charts=2)

    evidence = [c for c in r.evidence_charts if chart_has_plottable_data(c)]
    _append_charts(story, evidence, max_charts=2, caption_prefix="Evidence — ")

    recs = _actionable_recommendations(r.recommendations)
    if recs:
        story.append(Paragraph("Recommended actions", _CAPTION_STYLE))
        for rec in recs:
            story.append(Paragraph(f"&bull; {rec}", _BODY_STYLE))

    story.append(Spacer(1, 12))


def _page_footer(canvas, doc) -> None:
    canvas.saveState()
    canvas.setStrokeColor(_STONE_BORDER)
    canvas.setLineWidth(0.5)
    canvas.line(_MARGIN, 1.15 * cm, A4[0] - _MARGIN, 1.15 * cm)
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(_STONE_MUTED)
    canvas.drawString(_MARGIN, 0.7 * cm, "Photon Intelligence Center Lite · Solar Performance Analysis")
    canvas.drawRightString(A4[0] - _MARGIN, 0.7 * cm, f"Page {doc.page}")
    canvas.restoreState()


def build_pdf_story(ctx: ReportContext) -> list:
    """Build the Platypus story for the PDF (also used by unit tests for content checks)."""
    story: list = []

    brief = build_owner_brief(ctx.run.results)
    story.append(_cover_banner(ctx, brief))
    story.append(Spacer(1, 12))

    detail_results = [r for r in ctx.run.results if _worth_detail_section(r)]
    skipped_unavailable = [r for r in ctx.run.results if r.status == ResultStatus.UNAVAILABLE]
    skipped_empty = [
        r
        for r in ctx.run.results
        if r.status == ResultStatus.OK and not _worth_detail_section(r)
    ]
    ok_with_findings = [r for r in ctx.run.results if _has_real_findings(r)]

    story.append(Paragraph("Plant Information", _H2_STYLE))
    story.append(
        _styled_table(
            ["Field", "Value", "Field", "Value"],
            [
                ["Plant name", ctx.plant.plant_name, "Timezone", ctx.plant.timezone],
                ["AC capacity (MW)", _fmt(ctx.plant.ac_capacity_mw, 2), "DC capacity (MWp)", _fmt(ctx.plant.dc_capacity_mwp, 2)],
                ["Module rating (Wp)", _fmt(ctx.plant.module_rating_wp, 0), "Inverter capacity (kW)", _fmt(ctx.plant.inverter_capacity_kw, 0)],
                ["Module technology", ctx.plant.module_technology, "Bifacial", "Yes" if ctx.plant.bifacial else "No"],
                [
                    "Tariff (INR/kWh)",
                    _fmt(ctx.plant.tariff_inr_per_kwh, 2) if ctx.plant.tariff_inr_per_kwh else "Not provided",
                    "PR benchmark (%)",
                    _fmt(ctx.plant.pr_benchmark_pct, 1) if ctx.plant.pr_benchmark_pct else "Not provided",
                ],
            ],
            col_widths=[3.8 * cm, 4.45 * cm, 3.8 * cm, 4.45 * cm],
        )
    )
    story.append(Spacer(1, 8))

    story.append(Paragraph("Data Source & Input Quality", _H2_STYLE))
    v = ctx.validation
    story.append(
        Paragraph(
            f"{v.row_count} rows across {v.column_count} columns were validated: "
            f"{len(v.blockers)} blocking issue(s), {len(v.warnings)} warning(s). "
            f"Detected sampling interval: {ctx.interval_result.detected_interval_minutes:.1f} minute(s)"
            f"{' (irregular/mixed intervals detected)' if ctx.interval_result.is_irregular else ''}. "
            f"External irradiance fallback used: "
            f"{'Yes' if ctx.external_irradiance_used else 'No — not used (feature deferred to a future phase).'}",
            _BODY_STYLE,
        )
    )
    if v.warnings:
        story.append(
            _styled_table(
                ["Issue", "Message", "Affected rows"],
                [[w.code, w.message, str(w.affected_rows)] for w in v.warnings[:15]],
                col_widths=[4 * cm, 10 * cm, 2.5 * cm],
            )
        )
    story.append(Spacer(1, 6))

    # Single KPI strip (not repeated elsewhere)
    story.append(Paragraph("Key Performance Indicators", _H2_STYLE))
    for bit in _kpi_strip(ctx):
        story.append(bit)
    story.append(Spacer(1, 10))

    # Single energy-loss bridge / waterfall
    bridge = build_loss_bridge(ctx.run.kpis, ctx.run.results)
    waterfall_ok = False
    if bridge is not None:
        story.append(Paragraph("Energy Loss Bridge", _H2_STYLE))
        if bridge.mode == "bridge":
            story.append(
                Paragraph(
                    f"Expected {_fmt(bridge.expected_mwh, 3)} MWh → "
                    f"diagnosed {_fmt(bridge.diagnosed_mwh, 3)} MWh → "
                    f"unknown {_fmt(bridge.unknown_mwh, 3)} MWh → "
                    f"actual {_fmt(bridge.actual_mwh, 3)} MWh.",
                    _BODY_STYLE,
                )
            )
            cards = _bridge_summary_cards(bridge)
            if cards is not None:
                story.append(Spacer(1, 4))
                story.append(cards)
                story.append(Spacer(1, 6))
        waterfall = render_waterfall(bridge)
        if waterfall is not None:
            story.append(KeepTogether([waterfall, Spacer(1, 4)]))
            waterfall_ok = True
        # Segment table only when waterfall could not be drawn (avoid duplicate of the chart)
        if not waterfall_ok:
            story.append(
                _styled_table(
                    ["Segment", "MWh"],
                    [[s.label, _fmt(s.raw_mwh, 3)] for s in bridge.segments],
                    col_widths=[12.5 * cm, 4 * cm],
                )
            )
        if bridge.note:
            story.append(Paragraph(bridge.note, _MUTED_STYLE))
        story.append(Spacer(1, 10))
    else:
        loss_rows = [
            (r.title, r.loss_energy_kwh or 0.0)
            for r in ok_with_findings
            if (r.loss_energy_kwh or 0) > 0
        ]
        if loss_rows:
            story.append(Paragraph("Loss Summary", _H2_STYLE))
            fallback = ChartSpec(
                chart_id="loss_summary",
                title="Diagnosed loss by module (kWh)",
                chart_type="bar",
                figure={
                    "data": [
                        {
                            "type": "bar",
                            "x": [n for n, _ in loss_rows],
                            "y": [v for _, v in loss_rows],
                            "marker": {"color": "#dc2626"},
                        }
                    ],
                    "layout": {"yaxis": {"title": {"text": "Loss (kWh)"}}},
                },
            )
            img = render_chart_spec(fallback)
            if img is not None:
                story.append(img)
            story.append(Spacer(1, 10))

    # Single All Faults table
    fault_rows = _fault_rows_from_results(ctx.run.results)
    story.append(Paragraph("All Faults", _H2_STYLE))
    if fault_rows:
        story.append(
            Paragraph(
                f"{len(fault_rows)} confirmed fault finding(s). "
                "Interactive Plotly zoom remains on the Results dashboard.",
                _BODY_STYLE,
            )
        )
        story.append(
            _styled_table(
                ["Fault type", "Equipment", "Severity", "Loss (kWh)", "Time window", "Status"],
                fault_rows[:80],
                col_widths=[3.8 * cm, 2.8 * cm, 2 * cm, 2.2 * cm, 3.5 * cm, 2.2 * cm],
            )
        )
        if len(fault_rows) > 80:
            story.append(Paragraph(f"+{len(fault_rows) - 80} more fault row(s) omitted.", _MUTED_STYLE))
    else:
        story.append(Paragraph("No confirmed fault findings in this run.", _BODY_STYLE))

    if detail_results:
        story.append(PageBreak())
        story.append(Paragraph("Fault-wise Analysis", _H2_STYLE))
        story.append(
            Paragraph(
                "Detail for modules with confirmed findings or meaningful diagnostic charts. "
                "Finding rows are listed once in All Faults above.",
                _MUTED_STYLE,
            )
        )
        for r in detail_results:
            # Skip re-dumping fault tables that already appear in All Faults
            _append_result_section(story, r, include_finding_tables=not _has_real_findings(r))

    # Compact appendix — mapping confidence + short skip list (no threshold JSON spam)
    has_appendix = bool(ctx.mapping_confidence_by_column) or bool(skipped_unavailable) or bool(skipped_empty)
    if has_appendix:
        story.append(PageBreak())
        story.append(Paragraph("Technical Appendix", _H2_STYLE))
        if ctx.mapping_confidence_by_column:
            story.append(
                Paragraph(
                    "Column mapping confidence",
                    ParagraphStyle("appendix_h", parent=_STYLES["Heading4"], textColor=_STONE),
                )
            )
            story.append(
                _styled_table(
                    ["Source column", "Confidence"],
                    [[c, f"{conf * 100:.0f}%"] for c, conf in ctx.mapping_confidence_by_column.items()],
                    col_widths=[10.5 * cm, 6 * cm],
                )
            )
            story.append(Spacer(1, 8))

        if skipped_unavailable or skipped_empty:
            story.append(
                Paragraph(
                    "Modules not detailed in this report",
                    ParagraphStyle("appendix_h2", parent=_STYLES["Heading4"], textColor=_STONE),
                )
            )
            skip_rows: list[list[str]] = []
            for r in skipped_unavailable:
                skip_rows.append([r.title, "Unavailable", (r.summary or "")[:120]])
            for r in skipped_empty:
                skip_rows.append([r.title, "No findings", (r.summary or "")[:120]])
            story.append(
                _styled_table(
                    ["Module", "Reason", "Note"],
                    skip_rows,
                    col_widths=[4.5 * cm, 3 * cm, 9 * cm],
                )
            )

        story.append(Spacer(1, 10))
        story.append(
            Paragraph(
                "Charts are static matplotlib renders of Results figures. "
                "Interactive zoom and Investigate overlays are available only in the dashboard.",
                _MUTED_STYLE,
            )
        )

    return story


def build_pdf(ctx: ReportContext) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        topMargin=1.5 * cm,
        bottomMargin=1.6 * cm,
        leftMargin=_MARGIN,
        rightMargin=_MARGIN,
        title=ctx.report_title,
        author="Photon Intelligence Center Lite",
    )
    doc.build(build_pdf_story(ctx), onFirstPage=_page_footer, onLaterPages=_page_footer)
    return buf.getvalue()


# Public alias used by the job worker (matches build_excel_report naming).
build_pdf_report = build_pdf
