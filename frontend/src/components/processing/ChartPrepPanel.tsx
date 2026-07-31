import clsx from "clsx";
import { CHART_PREP_LABELS } from "./useAnalysisLog";

type PrepPhase = "idle" | "loading" | "drawing" | "ready";

function phaseFromState(state: string | null | undefined): PrepPhase {
  if (!state || state === "queued" || state === "validating" || state === "normalizing") return "idle";
  if (state === "running") return "loading";
  if (state === "generating_charts") return "drawing";
  if (state === "generating_report" || state === "completed") return "ready";
  return "idle";
}

/** Deterministic decorative timeseries path (not real data). */
function seriesPath(seed: number, w: number, h: number): string {
  const pts: string[] = [];
  const n = 28;
  for (let i = 0; i <= n; i++) {
    const x = (i / n) * w;
    const wave =
      Math.sin(i * 0.45 + seed) * 0.28 +
      Math.sin(i * 0.18 + seed * 1.7) * 0.18 +
      Math.cos(i * 0.09) * 0.08;
    const y = h * (0.55 - wave) + (seed % 3) * 2;
    pts.push(`${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`);
  }
  return pts.join(" ");
}

function SkeletonPlot({
  label,
  phase,
  index,
}: {
  label: string;
  phase: PrepPhase;
  index: number;
}) {
  const w = 280;
  const h = 72;
  const path = seriesPath(index * 2.3 + 1, w, h);
  const drawing = phase === "drawing" || phase === "ready";
  const ready = phase === "ready";

  return (
    <div
      className={clsx(
        "proc-chart-card flex min-h-0 flex-1 flex-col rounded-md border border-stone-200/80 bg-white/70 p-2 dark:border-stone-700/70 dark:bg-stone-950/40",
        phase === "loading" && "proc-chart-shimmer",
      )}
      style={{ animationDelay: `${index * 100}ms` }}
    >
      <div className="mb-1 flex shrink-0 items-center justify-between gap-2">
        <p className="truncate text-[10px] font-semibold uppercase tracking-wide text-stone-500 dark:text-stone-400">
          {label}
        </p>
        <span
          className={clsx(
            "shrink-0 rounded px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wide",
            phase === "idle" && "bg-stone-100 text-stone-400 dark:bg-stone-800 dark:text-stone-500",
            phase === "loading" && "bg-brand-50 text-brand-700 dark:bg-brand-950/40 dark:text-brand-300",
            phase === "drawing" && "bg-amber-50 text-amber-800 dark:bg-amber-950/40 dark:text-amber-300",
            ready && "bg-accent-50 text-accent-800 dark:bg-accent-950/40 dark:text-accent-300",
          )}
        >
          {phase === "idle" && "queued"}
          {phase === "loading" && "buffering"}
          {phase === "drawing" && "drawing"}
          {ready && "ready"}
        </span>
      </div>

      <svg
        viewBox={`0 0 ${w} ${h}`}
        className="min-h-[3.25rem] w-full flex-1 text-brand-600 dark:text-brand-400"
        preserveAspectRatio="none"
        aria-hidden
      >
        {[0.25, 0.5, 0.75].map((t) => (
          <line
            key={`h-${t}`}
            x1={0}
            x2={w}
            y1={h * t}
            y2={h * t}
            className="stroke-stone-200 dark:stroke-stone-700"
            strokeWidth={1}
          />
        ))}
        {[0.2, 0.4, 0.6, 0.8].map((t) => (
          <line
            key={`v-${t}`}
            x1={w * t}
            x2={w * t}
            y1={0}
            y2={h}
            className="stroke-stone-100 dark:stroke-stone-800"
            strokeWidth={1}
          />
        ))}

        {ready && (
          <path
            d={`${path} L${w},${h} L0,${h} Z`}
            className="fill-accent-500/10 dark:fill-accent-400/10"
          />
        )}

        <path
          d={path}
          fill="none"
          stroke="currentColor"
          strokeWidth={1.75}
          strokeLinecap="round"
          strokeLinejoin="round"
          className={clsx(
            drawing ? "proc-chart-draw" : "opacity-20",
            ready && "opacity-90",
            phase === "loading" && "opacity-30",
          )}
          style={drawing ? { animationDelay: `${index * 180}ms` } : undefined}
        />

        <path
          d={seriesPath(index * 1.7 + 4, w, h)}
          fill="none"
          stroke="currentColor"
          strokeWidth={1.25}
          className={clsx(
            "text-accent-600 dark:text-accent-400",
            drawing ? "proc-chart-draw-delayed" : "opacity-0",
            ready ? "opacity-70" : drawing ? "opacity-45" : "opacity-0",
          )}
          style={drawing ? { animationDelay: `${220 + index * 180}ms` } : undefined}
        />
      </svg>
    </div>
  );
}

export function ChartPrepPanel({ state }: { state: string | null | undefined }) {
  const phase = phaseFromState(state);

  const statusCopy =
    phase === "idle"
      ? "Canvases idle until the worker starts"
      : phase === "loading"
        ? "Reserving figure layouts while modules run"
        : phase === "drawing"
          ? "Tracing series into dashboard figures"
          : "Figures prepared — packaging reports";

  return (
    <section
      className="proc-panel flex min-h-0 flex-col overflow-hidden lg:w-[min(100%,24rem)] lg:shrink-0"
      aria-label="Chart preparation"
    >
      <header className="flex shrink-0 items-center justify-between gap-2 border-b border-stone-200/80 px-3 py-2 dark:border-stone-700/80">
        <span className="font-display text-[11px] font-semibold uppercase leading-normal tracking-[0.14em] text-stone-600 dark:text-stone-300">
          Chart prep
        </span>
        <span className="min-w-0 truncate text-[10px] leading-normal text-stone-400 dark:text-stone-500">{statusCopy}</span>
      </header>

      <div className="flex min-h-0 flex-1 flex-col gap-1.5 overflow-y-auto p-2">
        {CHART_PREP_LABELS.map((label, i) => (
          <SkeletonPlot key={label} label={label} phase={phase} index={i} />
        ))}
      </div>
    </section>
  );
}
