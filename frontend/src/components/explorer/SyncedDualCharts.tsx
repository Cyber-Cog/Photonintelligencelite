import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ChartDownloadButton } from "@/components/ChartDownloadButton";
import { Spinner } from "@/components/ui/Spinner";
import { CHART_PALETTE, plotlyHoverLabel, plotlyUiConfig } from "@/lib/chartTheme";
import type { TimeseriesSeries } from "@/types";

const Plot = lazy(() => import("react-plotly.js"));

export type SignalPane = "current" | "voltage" | "other" | "meteo";

export function classifySignal(signal: string): SignalPane {
  const s = signal.toLowerCase();
  if (s.includes("current")) return "current";
  if (s.includes("voltage")) return "voltage";
  if (s.includes("poa") || s.includes("ghi") || s.includes("temp")) return "meteo";
  return "other";
}

type ColoredSeries = TimeseriesSeries & { color: string; colorIndex: number };

function buildPaneFigure(
  series: ColoredSeries[],
  yTitle: string,
  dark: boolean,
  height: number,
  uirevision: string,
  showXTitle: boolean,
): { data: Record<string, unknown>[]; layout: Record<string, unknown> } {
  const fontColor = dark ? "#d6d3d1" : "#44403c";
  const grid = dark ? "#44403c" : "#e7e5e4";
  const hasMeteo = series.some((s) => classifySignal(s.signal) === "meteo");

  const data = series.map((s) => {
    const isMeteo = classifySignal(s.signal) === "meteo";
    return {
      type: "scatter",
      mode: "lines",
      name: s.name,
      x: s.timestamps,
      y: s.values,
      line: { width: 1.4, color: s.color },
      yaxis: isMeteo ? "y2" : "y",
      hovertemplate: `%{y:.3~f}<extra>${s.name}</extra>`,
    };
  });

  const layout: Record<string, unknown> = {
    autosize: true,
    height,
    paper_bgcolor: "transparent",
    plot_bgcolor: dark ? "rgba(28,25,23,0.5)" : "rgba(250,250,249,0.8)",
    font: { color: fontColor, size: 10, family: "DM Sans, Segoe UI, system-ui, sans-serif" },
    margin: { t: 6, r: hasMeteo ? 44 : 12, b: showXTitle ? 36 : 22, l: 44, pad: 0 },
    xaxis: {
      title: showXTitle ? { text: "Time", font: { size: 10, color: fontColor } } : undefined,
      gridcolor: grid,
      automargin: true,
      zeroline: false,
      showspikes: true,
      spikemode: "across",
      spikesnap: "cursor",
      spikethickness: 1,
      spikecolor: "#a8a29e",
      spikedash: "dot",
      uirevision,
    },
    yaxis: {
      title: { text: yTitle, font: { size: 10, color: fontColor } },
      gridcolor: grid,
      automargin: true,
      zeroline: false,
      uirevision,
    },
    showlegend: false,
    hovermode: "x",
    hoverlabel: plotlyHoverLabel(dark),
    dragmode: "zoom",
    uirevision,
  };

  if (hasMeteo) {
    layout.yaxis2 = {
      title: { text: "Irr / Temp", font: { size: 10, color: fontColor } },
      overlaying: "y",
      side: "right",
      gridcolor: "transparent",
      automargin: true,
      zeroline: false,
      uirevision,
    };
  }

  return { data, layout };
}

function usePaneHeight(enabled: boolean, panes: number) {
  const ref = useRef<HTMLDivElement>(null);
  const [height, setHeight] = useState(panes > 1 ? 220 : 320);

  useEffect(() => {
    if (!enabled) return;
    const el = ref.current;
    if (!el) return;
    const measure = () => {
      const h = Math.floor(el.getBoundingClientRect().height);
      const min = panes > 1 ? 140 : 180;
      if (h > min) setHeight(h);
    };
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, [enabled, panes]);

  return { ref, height };
}

type PlotlyGd = HTMLElement & { data?: unknown[]; layout?: unknown };

type PlotlyApi = {
  relayout: (gd: PlotlyGd, update: Record<string, unknown>) => Promise<unknown>;
  Fx: {
    hover: (gd: PlotlyGd, opts: { xval: unknown } | unknown[]) => void;
    unhover: (gd: PlotlyGd) => void;
  };
};

async function getPlotly() {
  const fromWindow = (window as unknown as { Plotly?: PlotlyApi }).Plotly;
  if (fromWindow?.relayout) return fromWindow;
  const mod = (await import("plotly.js")) as unknown as { default?: PlotlyApi } & PlotlyApi;
  return mod.default ?? mod;
}

function extractXRange(event: Record<string, unknown>): [string | number, string | number] | "autorange" | null {
  if (event["xaxis.autorange"] === true) return "autorange";
  const r0 = event["xaxis.range[0]"];
  const r1 = event["xaxis.range[1]"];
  if (r0 != null && r1 != null) return [r0 as string | number, r1 as string | number];
  const range = event["xaxis.range"];
  if (Array.isArray(range) && range.length >= 2) {
    return [range[0] as string | number, range[1] as string | number];
  }
  return null;
}

function nearestIndex(timestamps: string[], x: unknown): number {
  if (!timestamps.length) return 0;
  const key = String(x);
  // Exact / string match via binary search on ISO-like ascending stamps
  let lo = 0;
  let hi = timestamps.length - 1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    const v = timestamps[mid];
    if (v === key) return mid;
    if (v < key) lo = mid + 1;
    else hi = mid - 1;
  }
  if (lo <= 0) return 0;
  if (lo >= timestamps.length) return timestamps.length - 1;
  // Pick closer neighbor
  const a = timestamps[lo - 1];
  const b = timestamps[lo];
  return Math.abs(Date.parse(a) - Date.parse(key)) <= Math.abs(Date.parse(b) - Date.parse(key)) ? lo - 1 : lo;
}

/** Nearest sample values across all series for the shared legend. */
function legendValuesAt(series: ColoredSeries[], x: unknown): Record<string, string> {
  const next: Record<string, string> = {};
  if (x == null || !series.length) return next;
  for (const s of series) {
    if (!s.timestamps.length) {
      next[s.name] = "—";
      continue;
    }
    const y = s.values[nearestIndex(s.timestamps, x)];
    next[s.name] = typeof y === "number" && Number.isFinite(y) ? y.toFixed(2) : "—";
  }
  return next;
}

export function SyncedDualCharts({
  series,
  dark,
  pointCount,
  forceSingle = false,
}: {
  series: TimeseriesSeries[];
  dark: boolean;
  pointCount: number;
  forceSingle?: boolean;
}) {
  const chartHostRef = useRef<HTMLDivElement>(null);
  const topPlotRef = useRef<PlotlyGd | null>(null);
  const bottomPlotRef = useRef<PlotlyGd | null>(null);
  const syncingRangeRef = useRef(false);
  const syncingHoverRef = useRef(false);
  const [zoomed, setZoomed] = useState(false);
  const [hoverByName, setHoverByName] = useState<Record<string, string>>({});
  const [hoverTime, setHoverTime] = useState<string | null>(null);

  useEffect(() => {
    setZoomed(false);
    setHoverByName({});
    setHoverTime(null);
  }, [series]);

  const colored = useMemo<ColoredSeries[]>(
    () =>
      series.map((s, i) => ({
        ...s,
        color: CHART_PALETTE[i % CHART_PALETTE.length],
        colorIndex: i,
      })),
    [series],
  );

  const panes = useMemo(() => {
    const current = colored.filter((s) => classifySignal(s.signal) === "current");
    const voltage = colored.filter((s) => classifySignal(s.signal) === "voltage");
    const meteo = colored.filter((s) => classifySignal(s.signal) === "meteo");
    const other = colored.filter((s) => classifySignal(s.signal) === "other");

    const dual = !forceSingle && current.length > 0 && voltage.length > 0;
    if (dual) {
      return {
        mode: "dual" as const,
        top: { title: "DC Current", yTitle: "Current (A)", series: [...current, ...other, ...meteo] },
        bottom: { title: "DC Voltage", yTitle: "Voltage (V)", series: voltage },
      };
    }
    return {
      mode: "single" as const,
      top: {
        title: "Timeseries",
        yTitle: "Value",
        series: colored,
      },
      bottom: null,
    };
  }, [colored, forceSingle]);

  const paneCount = panes.mode === "dual" ? 2 : 1;
  const { ref: stackRef, height: stackHeight } = usePaneHeight(true, paneCount);
  const topHeight = panes.mode === "dual" ? Math.max(140, Math.floor(stackHeight * 0.52) - 4) : stackHeight;
  const bottomHeight = panes.mode === "dual" ? Math.max(140, stackHeight - topHeight - 8) : 0;

  const uirevision = useMemo(
    () => series.map((s) => `${s.equipment_id}:${s.signal}`).join("|") || "empty",
    [series],
  );

  const topFigure = useMemo(
    () =>
      buildPaneFigure(panes.top.series, panes.top.yTitle, dark, topHeight, uirevision, panes.mode === "single"),
    [panes.top, dark, topHeight, uirevision, panes.mode],
  );

  const bottomFigure = useMemo(() => {
    if (!panes.bottom) return null;
    return buildPaneFigure(panes.bottom.series, panes.bottom.yTitle, dark, bottomHeight, uirevision, true);
  }, [panes.bottom, dark, bottomHeight, uirevision]);

  const applyRangeToOther = useCallback(
    async (source: "top" | "bottom", event: Record<string, unknown>) => {
      const range = extractXRange(event);
      if (range == null) return;
      if (syncingRangeRef.current) return;
      syncingRangeRef.current = true;
      try {
        setZoomed(range !== "autorange");
        const other = source === "top" ? bottomPlotRef.current : topPlotRef.current;
        if (!other || panes.mode !== "dual") return;
        const Plotly = await getPlotly();
        if (range === "autorange") {
          await Plotly.relayout(other, { "xaxis.autorange": true });
        } else {
          await Plotly.relayout(other, {
            "xaxis.range": range,
            "xaxis.autorange": false,
          });
        }
      } finally {
        requestAnimationFrame(() => {
          syncingRangeRef.current = false;
        });
      }
    },
    [panes.mode],
  );

  const onTopRelayout = useCallback(
    (event: Readonly<Record<string, unknown>>) => {
      void applyRangeToOther("top", event as Record<string, unknown>);
    },
    [applyRangeToOther],
  );

  const onBottomRelayout = useCallback(
    (event: Readonly<Record<string, unknown>>) => {
      void applyRangeToOther("bottom", event as Record<string, unknown>);
    },
    [applyRangeToOther],
  );

  const syncHover = useCallback(
    async (source: "top" | "bottom", event: Readonly<{ points?: { x?: unknown }[] }>) => {
      if (syncingHoverRef.current) return;
      const pts = event.points ?? [];
      if (!pts.length) return;
      const x = pts[0]?.x;
      setHoverByName(legendValuesAt(colored, x));
      setHoverTime(x != null ? String(x).replace("T", " ").slice(0, 19) : null);

      if (panes.mode !== "dual") return;
      const other = source === "top" ? bottomPlotRef.current : topPlotRef.current;
      if (!other || x == null) return;
      syncingHoverRef.current = true;
      try {
        const Plotly = await getPlotly();
        Plotly.Fx.hover(other, { xval: x });
      } catch {
        /* ignore hover sync failures */
      } finally {
        requestAnimationFrame(() => {
          syncingHoverRef.current = false;
        });
      }
    },
    [panes.mode, colored],
  );

  const clearHover = useCallback(
    async (source: "top" | "bottom") => {
      if (syncingHoverRef.current) return;
      setHoverByName({});
      setHoverTime(null);
      if (panes.mode !== "dual") return;
      const other = source === "top" ? bottomPlotRef.current : topPlotRef.current;
      if (!other) return;
      syncingHoverRef.current = true;
      try {
        const Plotly = await getPlotly();
        Plotly.Fx.unhover(other);
      } catch {
        /* ignore */
      } finally {
        requestAnimationFrame(() => {
          syncingHoverRef.current = false;
        });
      }
    },
    [panes.mode],
  );

  const resetZoom = async () => {
    setZoomed(false);
    syncingRangeRef.current = true;
    try {
      const Plotly = await getPlotly();
      const updates = { "xaxis.autorange": true };
      const jobs: Promise<unknown>[] = [];
      if (topPlotRef.current) jobs.push(Plotly.relayout(topPlotRef.current, updates));
      if (bottomPlotRef.current) jobs.push(Plotly.relayout(bottomPlotRef.current, updates));
      await Promise.all(jobs);
    } finally {
      requestAnimationFrame(() => {
        syncingRangeRef.current = false;
      });
    }
  };

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-xl border border-stone-200/90 bg-white/95 shadow-sm shadow-stone-900/[0.03] dark:border-stone-800 dark:bg-stone-900/70 dark:shadow-none">
      <div className="flex shrink-0 flex-wrap items-center gap-x-3 gap-y-1 border-b border-stone-200/80 px-2.5 py-1.5 dark:border-stone-800">
        <div className="min-w-0">
          <p className="font-display text-xs font-semibold text-stone-800 dark:text-stone-100">
            {panes.mode === "dual" ? "Current · Voltage" : "Timeseries"}
          </p>
          <p className="text-[10px] tabular-nums text-stone-400">
            {pointCount.toLocaleString()} pts
            {hoverTime ? ` · ${hoverTime}` : ""}
          </p>
        </div>
        <div className="flex min-w-0 flex-1 flex-wrap items-center gap-x-2.5 gap-y-0.5">
          {colored.map((s) => (
            <div
              key={`${s.equipment_id}-${s.signal}`}
              className="flex items-center gap-1 text-[10px] text-stone-600 dark:text-stone-300"
            >
              <span className="inline-block h-1.5 w-1.5 shrink-0 rounded-full" style={{ background: s.color }} />
              <span className="max-w-[9rem] truncate" title={s.name}>
                {s.name}
              </span>
              <span className="font-mono tabular-nums text-stone-800 dark:text-stone-100">
                {hoverByName[s.name] ?? "—"}
              </span>
            </div>
          ))}
        </div>
        <div className="ml-auto flex shrink-0 items-center gap-1.5">
          {zoomed && (
            <button type="button" className="btn-ghost !px-1.5 !py-0.5 text-[10px]" onClick={() => void resetZoom()}>
              Reset zoom
            </button>
          )}
          <ChartDownloadButton
            hostRef={chartHostRef}
            filename="signal_explorer"
            className="btn-secondary !px-2 !py-0.5 text-[10px]"
          />
        </div>
      </div>

      <div ref={chartHostRef} className="plotly-chart-host flex min-h-0 flex-1 flex-col px-1 pb-1 pt-0.5">
        <div ref={stackRef} className="flex min-h-0 flex-1 flex-col gap-1">
          <div className="relative min-h-0" style={{ flex: panes.mode === "dual" ? "1 1 52%" : "1 1 auto" }}>
            {panes.mode === "dual" && (
              <span className="pointer-events-none absolute left-2 top-0.5 z-[1] text-[9px] font-semibold uppercase tracking-wider text-stone-400">
                {panes.top.title}
              </span>
            )}
            <Suspense
              fallback={
                <div className="flex h-full items-center justify-center gap-2 text-sm text-stone-500">
                  <Spinner className="h-4 w-4" /> Loading chart…
                </div>
              }
            >
              <Plot
                // eslint-disable-next-line @typescript-eslint/no-explicit-any
                data={topFigure.data as any[]}
                // eslint-disable-next-line @typescript-eslint/no-explicit-any
                layout={topFigure.layout as any}
                config={plotlyUiConfig("signal_explorer_top")}
                style={{ width: "100%", height: topHeight }}
                useResizeHandler
                onInitialized={(_fig, gd) => {
                  topPlotRef.current = gd as PlotlyGd;
                }}
                onUpdate={(_fig, gd) => {
                  topPlotRef.current = gd as PlotlyGd;
                }}
                onRelayout={onTopRelayout}
                onHover={(e) => void syncHover("top", e)}
                onUnhover={() => void clearHover("top")}
              />
            </Suspense>
          </div>

          {panes.mode === "dual" && bottomFigure && (
            <div className="relative min-h-0" style={{ flex: "1 1 48%" }}>
              <span className="pointer-events-none absolute left-2 top-0.5 z-[1] text-[9px] font-semibold uppercase tracking-wider text-stone-400">
                {panes.bottom!.title}
              </span>
              <Suspense fallback={null}>
                <Plot
                  // eslint-disable-next-line @typescript-eslint/no-explicit-any
                  data={bottomFigure.data as any[]}
                  // eslint-disable-next-line @typescript-eslint/no-explicit-any
                  layout={bottomFigure.layout as any}
                  config={plotlyUiConfig("signal_explorer_bottom")}
                  style={{ width: "100%", height: bottomHeight }}
                  useResizeHandler
                  onInitialized={(_fig, gd) => {
                    bottomPlotRef.current = gd as PlotlyGd;
                  }}
                  onUpdate={(_fig, gd) => {
                    bottomPlotRef.current = gd as PlotlyGd;
                  }}
                  onRelayout={onBottomRelayout}
                  onHover={(e) => void syncHover("bottom", e)}
                  onUnhover={() => void clearHover("bottom")}
                />
              </Suspense>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
