import { useMemo, useRef, useState } from "react";
import Plot from "react-plotly.js";
import { ChartDownloadButton } from "@/components/ChartDownloadButton";
import { MissingReasonBanner } from "@/components/MissingReasonBanner";
import { SectionPanel } from "@/components/ui/SectionPanel";
import { useTheme } from "@/context/ThemeContext";
import { plotlyHoverLabel, plotlySafeMargins, plotlyUiConfig } from "@/lib/chartTheme";
import {
  buildLossBridge,
  scaleSegments,
  WATERFALL_LEGEND,
  type BridgeSegment,
  type WaterfallUnit,
} from "@/lib/lossWaterfall";
import { diagnoseBridgeGaps } from "@/lib/missingReasons";
import type { KpiResponse, ResultObject } from "@/types";

function fmtMwh(v: number, digits = 3): string {
  if (!Number.isFinite(v)) return "—";
  if (Math.abs(v) >= 100) return v.toFixed(1);
  if (Math.abs(v) >= 10) return v.toFixed(2);
  return v.toFixed(digits);
}

/** Short x tick so Expected / Unknown / Actual stay readable; full name stays in hover. */
function axisLabel(seg: BridgeSegment): string {
  if (seg.key === "expected") return "Expected";
  if (seg.key === "actual") return "Actual";
  if (seg.key === "unknown") return "Unknown";
  return seg.label;
}

function UnitToggle({
  unit,
  setUnit,
  expectedOk,
}: {
  unit: WaterfallUnit;
  setUnit: (u: WaterfallUnit) => void;
  expectedOk: boolean;
}) {
  return (
    <div
      className="inline-flex rounded-xl border border-stone-200/90 bg-stone-50/80 p-0.5 dark:border-stone-700 dark:bg-stone-950/40"
      role="group"
      aria-label="Units"
    >
      <button
        type="button"
        className={`rounded-lg px-2.5 py-0.5 text-[11px] font-semibold transition-colors ${
          unit === "mwh"
            ? "bg-brand-600 text-white shadow-sm dark:bg-brand-500 dark:text-stone-950"
            : "text-stone-500 hover:text-stone-800 dark:hover:text-stone-200"
        }`}
        onClick={() => setUnit("mwh")}
      >
        MWh
      </button>
      <button
        type="button"
        className={`rounded-lg px-2.5 py-0.5 text-[11px] font-semibold transition-colors ${
          unit === "pct"
            ? "bg-brand-600 text-white shadow-sm dark:bg-brand-500 dark:text-stone-950"
            : "text-stone-500 hover:text-stone-800 dark:hover:text-stone-200"
        }`}
        onClick={() => setUnit("pct")}
        disabled={!expectedOk}
        title={!expectedOk ? "No expected energy" : "% of expected"}
      >
        %
      </button>
    </div>
  );
}

export function LossWaterfallBridge({
  kpis,
  results,
  jobId,
}: {
  kpis: KpiResponse;
  results: ResultObject[];
  jobId: string;
}) {
  const { theme } = useTheme();
  const [unit, setUnit] = useState<WaterfallUnit>("mwh");
  const chartHostRef = useRef<HTMLDivElement>(null);
  const dark = theme === "dark";

  const model = useMemo(() => buildLossBridge(kpis, results), [kpis, results]);
  const emptyGaps = useMemo(() => (model ? model.gaps : diagnoseBridgeGaps(kpis)), [model, kpis]);

  const chartHeight = useMemo(() => {
    const n = model?.segments.length ?? 0;
    return Math.min(480, Math.max(320, n > 10 ? 400 : 340));
  }, [model?.segments.length]);

  const scaled = useMemo(() => {
    if (!model) return [];
    return scaleSegments(model.segments, unit, model.expectedMwh);
  }, [model, unit]);

  const fontColor = dark ? "#d6d3d1" : "#44403c";
  const muted = dark ? "#a8a29e" : "#78716c";
  const grid = dark ? "#292524" : "#e7e5e4";
  const plotBg = dark ? "rgba(28,25,23,0.45)" : "rgba(250,250,249,0.9)";

  if (!model) {
    return (
      <SectionPanel
        title="Energy loss bridge"
        description="Expected to diagnostics to unknown to actual"
        scrollMargin={false}
      >
        <div className="space-y-3">
          <MissingReasonBanner reasons={emptyGaps} jobId={jobId} />
          {emptyGaps.length === 0 && (
            <p className="border border-dashed border-stone-200 px-3 py-8 text-center text-sm text-stone-500 dark:border-stone-700">
              No bridge available. Run analysis with AC energy and irradiance, or wait for fault modules that report
              energy loss.
            </p>
          )}
        </div>
      </SectionPanel>
    );
  }

  const n = scaled.length;
  const bottomPad = n > 6 ? 96 : 72;
  const yTitle = unit === "pct" && model.expectedMwh > 0 ? "% of expected" : "MWh";
  const prPct = model.expectedMwh > 0 ? (model.actualMwh / model.expectedMwh) * 100 : null;
  const xTicks = scaled.map(axisLabel);
  const yMax = scaled.reduce((m, s) => Math.max(m, s.invisible + s.visible), 0);
  const yHeadroom = yMax > 0 ? yMax * 0.14 : 1;

  const figureData = [
    {
      type: "bar" as const,
      name: "_spacer",
      x: xTicks,
      y: scaled.map((s) => s.invisible),
      marker: { color: "rgba(0,0,0,0)" },
      hoverinfo: "skip" as const,
      showlegend: false,
      // No text / textposition — values only via hover (avoids labels on tall bars).
    },
    {
      type: "bar" as const,
      name: "Segment",
      x: xTicks,
      y: scaled.map((s) => s.visible),
      customdata: scaled.map((s) => [s.rawMwh, s.label]),
      marker: {
        color: scaled.map((s) => s.fill),
        line: {
          color: scaled.map((s) =>
            s.kind === "unknown" ? "#a8a29e" : s.kind === "loss" ? "rgba(153,27,27,0.35)" : "rgba(28,25,23,0.08)",
          ),
          width: scaled.map((s) => (s.visible > 0 ? 1 : 0)),
        },
      },
      // Full segment name in hover; short tick on axis. Neutral hoverlabel in layout.
      hovertemplate:
        unit === "pct"
          ? "<b>%{customdata[1]}</b><br>%{customdata[0]:.3f} MWh<br>%{y:.2f}% of expected<extra></extra>"
          : "<b>%{customdata[1]}</b><br>%{y:.3f} MWh<extra></extra>",
      showlegend: false,
    },
  ];

  return (
    <SectionPanel
      title={model.mode === "bridge" ? "Energy loss bridge" : "Diagnosed energy losses"}
      description={
        model.mode === "bridge"
          ? "Expected → fault diagnostics → unknown → actual"
          : "Category bars only. Expected and actual blocked until KPIs are complete."
      }
      actions={
        <div className="flex flex-wrap items-center gap-2">
          <ChartDownloadButton hostRef={chartHostRef} filename="energy_loss_bridge" />
          {model.mode === "bridge" && (
            <UnitToggle unit={unit} setUnit={setUnit} expectedOk={model.expectedMwh > 0} />
          )}
        </div>
      }
      scrollMargin={false}
      bodyClassName="space-y-3 p-0"
    >
      {model.mode === "bridge" && (
        <div className="grid grid-cols-2 gap-px border-b border-stone-200 bg-stone-200 dark:border-stone-800 dark:bg-stone-800 sm:grid-cols-4">
          {[
            { label: "Expected", value: `${fmtMwh(model.expectedMwh)} MWh`, className: "text-stone-700 dark:text-stone-200" },
            { label: "Actual", value: `${fmtMwh(model.actualMwh)} MWh`, className: "text-emerald-700 dark:text-emerald-400" },
            { label: "PR", value: prPct != null ? `${prPct.toFixed(1)}%` : "—", className: "text-stone-800 dark:text-stone-100" },
            { label: "Unknown", value: `${fmtMwh(model.unknownMwh)} MWh`, className: "text-stone-500" },
          ].map((cell) => (
            <div key={cell.label} className="bg-white px-3 py-2 dark:bg-stone-900/80">
              <p className="text-[10px] font-semibold uppercase tracking-wide text-stone-400">{cell.label}</p>
              <p className={`text-sm font-semibold tabular-nums ${cell.className}`}>{cell.value}</p>
            </div>
          ))}
        </div>
      )}

      <div className="space-y-2.5 p-3">
        {model.gaps.length > 0 && <MissingReasonBanner reasons={model.gaps} jobId={jobId} />}

        {model.note && (
          <p className="rounded border border-amber-200 bg-amber-50/80 px-3 py-2 text-xs text-amber-900 dark:border-amber-900/50 dark:bg-amber-950/30 dark:text-amber-100">
            {model.note}
          </p>
        )}

        <div
          className="flex flex-wrap gap-x-4 gap-y-1 border border-stone-200 bg-stone-50 px-2.5 py-1.5 dark:border-stone-700 dark:bg-stone-800/40"
          role="list"
          aria-label="Colours"
        >
          {WATERFALL_LEGEND.map((leg) => (
            <span
              key={leg.key}
              className="inline-flex items-center gap-1.5 text-[11px] font-medium text-stone-600 dark:text-stone-300"
              role="listitem"
            >
              <span
                className="inline-block h-2.5 w-2.5 rounded-sm border border-stone-300/80"
                style={{ background: leg.fill }}
                aria-hidden
              />
              {leg.name}
            </span>
          ))}
        </div>

        <div
          ref={chartHostRef}
          className="plotly-chart-host w-full overflow-visible border border-stone-200 dark:border-stone-800"
        >
          <Plot
            data={figureData}
            layout={{
              barmode: "stack",
              autosize: true,
              height: chartHeight,
              margin: plotlySafeMargins({ b: bottomPad, l: 52 }),
              paper_bgcolor: "transparent",
              plot_bgcolor: plotBg,
              font: { color: fontColor, size: 11, family: "DM Sans, Segoe UI, system-ui, sans-serif" },
              // No layout annotations — values only in hover (no sticky labels on bars).
              annotations: [],
              hoverlabel: plotlyHoverLabel(dark),
              xaxis: {
                tickangle: n > 5 ? -32 : 0,
                tickfont: { size: 10, color: muted },
                automargin: true,
                showgrid: false,
                linecolor: grid,
                ticklen: 4,
                categoryorder: "array",
                categoryarray: xTicks,
              },
              yaxis: {
                title: { text: yTitle, font: { size: 10, color: muted } },
                tickfont: { size: 10, color: muted },
                gridcolor: grid,
                zeroline: false,
                rangemode: "tozero",
                range: [0, yMax + yHeadroom],
                automargin: true,
                ticksuffix: unit === "pct" ? "%" : "",
              },
              bargap: 0.28,
              showlegend: false,
              // closest clears on mouseleave — no sticky compare/unified box.
              hovermode: "closest",
            }}
            config={plotlyUiConfig("energy_loss_bridge")}
            style={{ width: "100%", height: chartHeight }}
            useResizeHandler
          />
        </div>

        <div className="overflow-x-auto rounded-xl border border-stone-200/90 dark:border-stone-700">
          <table className="w-full min-w-[28rem] text-left text-sm">
            <thead>
              <tr className="border-b border-stone-200 bg-stone-50/90 text-[10px] font-semibold uppercase tracking-wide text-stone-400 dark:border-stone-700 dark:bg-stone-950/50">
                <th className="px-3 py-2 font-semibold">Segment</th>
                <th className="px-3 py-2 text-right font-semibold">MWh</th>
                {model.expectedMwh > 0 && (
                  <th className="px-3 py-2 text-right font-semibold">% of expected</th>
                )}
                <th className="px-3 py-2 font-semibold">Type</th>
              </tr>
            </thead>
            <tbody>
              {model.segments.map((seg) => {
                const pct =
                  model.expectedMwh > 0 ? (seg.rawMwh / model.expectedMwh) * 100 : null;
                const typeLabel =
                  seg.kind === "total" ? "Total" : seg.kind === "unknown" ? "Unknown" : "Loss";
                return (
                  <tr
                    key={seg.key}
                    className="border-b border-stone-100 last:border-0 dark:border-stone-800/80"
                  >
                    <td className="px-3 py-2">
                      <span className="inline-flex items-center gap-2 font-medium text-stone-800 dark:text-stone-100">
                        <span
                          className="inline-block h-2.5 w-2.5 shrink-0 rounded-sm border border-stone-300/70"
                          style={{ background: seg.fill }}
                          aria-hidden
                        />
                        {seg.label}
                      </span>
                    </td>
                    <td className="px-3 py-2 text-right tabular-nums text-stone-700 dark:text-stone-300">
                      {fmtMwh(seg.rawMwh)}
                    </td>
                    {model.expectedMwh > 0 && (
                      <td className="px-3 py-2 text-right tabular-nums text-stone-500">
                        {pct != null ? `${pct.toFixed(2)}%` : "—"}
                      </td>
                    )}
                    <td className="px-3 py-2 text-xs text-stone-500">{typeLabel}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </SectionPanel>
  );
}
