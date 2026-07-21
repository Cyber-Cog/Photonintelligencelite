import { useMemo, useRef } from "react";
import Plot from "react-plotly.js";
import { ChartDownloadButton } from "@/components/ChartDownloadButton";
import { useTheme } from "@/context/ThemeContext";
import { plotlyHoverLabel, plotlySafeMargins, plotlyUiConfig, recolorBlueTraces } from "@/lib/chartTheme";
import type { ChartSpec } from "@/types";

function countBoxCategories(chart: ChartSpec): number {
  const traces = chart.figure.data ?? [];
  const cats = new Set<string>();
  for (const raw of traces) {
    const t = raw as { x?: unknown[]; type?: string };
    if (!t?.x) continue;
    for (const v of t.x) {
      if (v != null && v !== "") cats.add(String(v));
    }
  }
  return cats.size || 1;
}

function deepMergeAxis(
  themeAxis: Record<string, unknown>,
  baseAxis: Record<string, unknown> | undefined,
  fontColor: string,
): Record<string, unknown> {
  const base = baseAxis ?? {};
  const baseTitle = (base.title as Record<string, unknown> | string | undefined) ?? {};
  const titleObj =
    typeof baseTitle === "string"
      ? { text: baseTitle, font: { size: 12, color: fontColor } }
      : {
          ...baseTitle,
          font: { size: 12, color: fontColor, ...((baseTitle.font as object) || {}) },
        };
  return {
    ...themeAxis,
    ...base,
    gridcolor: (base.gridcolor as string) ?? themeAxis.gridcolor,
    linecolor: (base.linecolor as string) ?? themeAxis.linecolor,
    tickfont: { size: 11, color: fontColor, ...((base.tickfont as object) || {}) },
    title: titleObj,
    automargin: true,
  };
}

export function PlotlyChart({ chart, tall, fullWidth }: { chart: ChartSpec; tall?: boolean; fullWidth?: boolean }) {
  const { theme } = useTheme();
  const chartHostRef = useRef<HTMLDivElement>(null);
  const dark = theme === "dark";
  const isBox = chart.chart_type === "box";
  const isDiagnostic = chart.chart_type === "diagnostic" || tall;
  const isBar = chart.chart_type === "bar";
  const boxCats = isBox ? countBoxCategories(chart) : 0;

  const height = useMemo(() => {
    const layoutH = (chart.figure.layout as { height?: number } | undefined)?.height;
    if (typeof layoutH === "number" && layoutH > 0 && !isBox) return layoutH;
    if (isBox) {
      // Boxes sit on x-axis — keep a stable readable height; width grows with categories.
      return boxCats > 8 ? 420 : 380;
    }
    if (isDiagnostic) return 440;
    if (isBar) {
      const n = ((chart.figure.data?.[0] as { x?: unknown[] } | undefined)?.x as unknown[] | undefined)?.length ?? 0;
      return Math.max(300, Math.min(460, 200 + n * 10));
    }
    return 360;
  }, [chart, isBox, isDiagnostic, isBar, boxCats]);

  const minWidth = useMemo(() => {
    if (!isBox) return undefined;
    // ~72px per inverter so labels aren't crushed; scroll container handles overflow.
    return Math.max(320, boxCats * 72 + 96);
  }, [isBox, boxCats]);

  const data = useMemo(() => recolorBlueTraces(chart.figure.data ?? []), [chart.figure.data]);

  const layout = useMemo(() => {
    const base = { ...(chart.figure.layout ?? {}) } as Record<string, unknown>;
    const fontColor = dark ? "#d6d3d1" : "#44403c";
    const muted = dark ? "#a8a29e" : "#78716c";
    const grid = dark ? "#292524" : "#e7e5e4";
    const plotBg = dark ? "rgba(28,25,23,0.45)" : "rgba(250,250,249,0.9)";

    const baseMargin = (base.margin as Record<string, number> | undefined) ?? {};
    const rotate = isBox && boxCats > 6;
    const safe = plotlySafeMargins({
      t: isDiagnostic ? 36 : 28,
      b: isBox ? (rotate ? 110 : 72) : isBar ? 72 : 56,
      l: 64,
    });
    const margin = {
      ...safe,
      ...baseMargin,
      t: Math.max(safe.t, baseMargin.t ?? 0),
      r: Math.max(safe.r, baseMargin.r ?? 0),
      b: Math.max(safe.b, baseMargin.b ?? 0),
      l: Math.max(safe.l, baseMargin.l ?? 0),
      ...(isBox && rotate ? { b: Math.max(baseMargin.b ?? 0, 110) } : {}),
    };

    // Drop payload title — we render chart.title in the card header to avoid double titles.
    // Drop sticky annotations that sit on data (bar-top labels clip tall bars); keep captions below.
    const { title: _ignoredTitle, annotations: baseAnnotations, ...restBase } = base;
    void _ignoredTitle;

    const annotations = Array.isArray(baseAnnotations)
      ? (baseAnnotations as Record<string, unknown>[])
          .filter((a) => {
            // Keep only paper-ref captions / footnotes (yref paper, typically below).
            const yref = String(a.yref ?? "y");
            const y = typeof a.y === "number" ? a.y : null;
            if (yref === "paper" && y != null && y < 0.05) return true;
            if (yref === "paper" && y != null && y > 1.02) return true;
            // Drop data-space annotations that cover bars/points.
            return false;
          })
          .map((a) => ({
            ...a,
            font: { size: 10, color: muted, ...((a.font as object) || {}) },
            y: typeof a.y === "number" && (a.y as number) < 0 ? -0.08 : a.y,
          }))
      : [];

    return {
      ...restBase,
      autosize: true,
      height,
      margin,
      paper_bgcolor: "transparent",
      plot_bgcolor: plotBg,
      font: { color: fontColor, size: 12, family: "DM Sans, Segoe UI, system-ui, sans-serif" },
      xaxis: deepMergeAxis(
        {
          gridcolor: grid,
          zeroline: false,
          showline: true,
          linecolor: grid,
          tickangle: isBox && rotate ? -35 : undefined,
        },
        base.xaxis as Record<string, unknown> | undefined,
        fontColor,
      ),
      yaxis: deepMergeAxis(
        {
          gridcolor: grid,
          zeroline: false,
          showline: true,
          linecolor: grid,
        },
        base.yaxis as Record<string, unknown> | undefined,
        fontColor,
      ),
      legend: {
        orientation: "h",
        y: -0.18,
        x: 0,
        xanchor: "left",
        font: { size: 11, color: muted },
        bgcolor: "rgba(0,0,0,0)",
        ...((base.legend as object) || {}),
      },
      annotations,
      hovermode: (base.hovermode as string) === "x unified" || (base.hovermode as string) === "x"
        ? "closest"
        : (base.hovermode as string) || "closest",
      hoverlabel: plotlyHoverLabel(dark),
    };
  }, [chart.figure.layout, dark, height, isBox, isDiagnostic, isBar, boxCats]);

  const hasData =
    Array.isArray(data) &&
    data.some((trace) => {
      const t = trace as { y?: unknown[]; x?: unknown[]; q1?: unknown[]; z?: unknown[] };
      const hasY = Array.isArray(t.y) && t.y.some((v) => v != null && v !== "");
      const hasX = Array.isArray(t.x) && t.x.some((v) => v != null && v !== "");
      return (
        hasY ||
        hasX ||
        (t.q1 && t.q1.length > 0) ||
        (t.z && Array.isArray(t.z) && t.z.length > 0)
      );
    });

  if (!hasData) {
    return (
      <div className="rounded-lg border border-dashed border-stone-200 p-4 dark:border-stone-700">
        <h4 className="text-sm font-semibold text-stone-800 dark:text-stone-100">{chart.title}</h4>
        <p className="mt-2 text-xs text-stone-500">No plot points for this chart on the current job.</p>
      </div>
    );
  }

  return (
    <div
      className={`overflow-hidden rounded-lg border border-stone-100 bg-white/50 dark:border-stone-800 dark:bg-stone-950/25 ${
        fullWidth ? "col-span-full" : ""
      }`}
    >
      <div className="flex items-start justify-between gap-2 border-b border-stone-100/80 px-4 py-2.5 dark:border-stone-800/80">
        <h4 className="text-sm font-semibold leading-snug text-stone-800 dark:text-stone-100">{chart.title}</h4>
        <ChartDownloadButton hostRef={chartHostRef} filename={chart.chart_id || "chart"} />
      </div>
      <div
        ref={chartHostRef}
        className={`plotly-chart-host relative px-2 pb-2 pt-1 ${isBox ? "overflow-x-auto" : ""}`}
      >
        <Plot
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          data={data as any[]}
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          layout={layout as any}
          config={plotlyUiConfig(chart.chart_id)}
          style={{ width: "100%", minWidth, height }}
          useResizeHandler
        />
      </div>
    </div>
  );
}
