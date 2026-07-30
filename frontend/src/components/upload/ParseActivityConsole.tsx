import { useEffect, useRef } from "react";
import clsx from "clsx";
import type { AnalysisLogLine, LogLevel } from "@/components/processing/useAnalysisLog";
import type { UploadActivityPhase } from "./useParseActivityLog";

const LEVEL_STYLE: Record<LogLevel, string> = {
  info: "text-stone-500 dark:text-stone-400",
  ok: "text-accent-700 dark:text-accent-400",
  run: "text-brand-800 dark:text-brand-300",
  wait: "text-amber-700 dark:text-amber-400",
  warn: "text-rose-700 dark:text-rose-400",
};

const LEVEL_TAG: Record<LogLevel, string> = {
  info: "INFO",
  ok: "DONE",
  run: "EXEC",
  wait: "WAIT",
  warn: "FAIL",
};

function formatClock(sec: number): string {
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return `${m.toString().padStart(2, "0")}:${s.toString().padStart(2, "0")}`;
}

/** Mini decorative sheet-scan skeleton — activity only, not real chart data. */
function SheetScanSkeleton({ phase }: { phase: UploadActivityPhase }) {
  const parsing = phase === "parsing";
  const rows = [0.92, 0.78, 0.85, 0.64, 0.71, 0.55];

  return (
    <div
      className={clsx(
        "parse-sheet-card flex flex-col rounded-lg border border-stone-200/80 bg-white/70 p-2.5 dark:border-stone-700/70 dark:bg-stone-950/40",
        parsing && "proc-chart-shimmer",
      )}
      aria-hidden
    >
      <div className="mb-2 flex items-center justify-between gap-2">
        <p className="text-[10px] font-semibold uppercase tracking-wide text-stone-500 dark:text-stone-400">
          Sheet scan
        </p>
        <span
          className={clsx(
            "rounded px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wide",
            phase === "uploading" && "bg-brand-50 text-brand-700 dark:bg-brand-950/40 dark:text-brand-300",
            parsing && "bg-amber-50 text-amber-800 dark:bg-amber-950/40 dark:text-amber-300",
          )}
        >
          {phase === "uploading" ? "buffer" : "reading"}
        </span>
      </div>
      <div className="flex flex-1 flex-col justify-center gap-1.5">
        {rows.map((w, i) => (
          <div
            key={i}
            className={clsx(
              "parse-sheet-row h-1.5 rounded-sm bg-stone-200/90 dark:bg-stone-700/80",
              parsing && "parse-sheet-row-live",
            )}
            style={{
              width: `${w * 100}%`,
              animationDelay: parsing ? `${i * 90}ms` : undefined,
            }}
          />
        ))}
      </div>
      <p className="mt-2 font-mono text-[9px] text-stone-400 dark:text-stone-500">
        {phase === "uploading" ? "awaiting bytes…" : "headers · rows · types"}
      </p>
    </div>
  );
}

/**
 * Compact upload/parse activity panel — console energy without the full Processing takeover.
 */
export function ParseActivityConsole({
  lines,
  phase,
  live = true,
}: {
  lines: AnalysisLogLine[];
  phase: UploadActivityPhase;
  live?: boolean;
}) {
  const scrollerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = scrollerRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
  }, [lines]);

  return (
    <div
      className="parse-activity mt-3 flex flex-col gap-2 sm:flex-row sm:items-stretch"
      aria-label="Upload and parse activity"
    >
      <section className="parse-activity-panel flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
        <header className="flex shrink-0 items-center justify-between gap-2 border-b border-stone-200/80 px-2.5 py-1.5 dark:border-stone-700/80">
          <div className="flex items-center gap-2">
            <span className="font-display text-[10px] font-semibold uppercase tracking-[0.14em] text-stone-600 dark:text-stone-300">
              Parse console
            </span>
            {live && (
              <span className="proc-live-dot inline-flex items-center gap-1 rounded-md bg-accent-50 px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wide text-accent-800 dark:bg-accent-950/50 dark:text-accent-300">
                <span className="h-1.5 w-1.5 rounded-full bg-accent-500" aria-hidden />
                Live
              </span>
            )}
          </div>
          <span className="font-mono text-[9px] text-stone-400 dark:text-stone-500">
            {phase === "uploading" ? "xfer" : "xlsx→csv"}
          </span>
        </header>

        <div
          ref={scrollerRef}
          className="proc-log-scroll h-[7.5rem] overflow-y-auto px-2.5 py-2"
          role="log"
          aria-live="polite"
          aria-relevant="additions"
        >
          {lines.length === 0 ? (
            <p className="font-mono text-[11px] text-stone-400">Starting transfer…</p>
          ) : (
            <ul className="space-y-0.5">
              {lines.map((line) => (
                <li
                  key={line.id}
                  className="proc-log-line flex gap-1.5 font-mono text-[10px] leading-relaxed sm:text-[11px]"
                >
                  <span className="shrink-0 tabular-nums text-stone-400 dark:text-stone-500">
                    {formatClock(line.elapsedSec)}
                  </span>
                  <span
                    className={clsx("w-8 shrink-0 font-semibold tracking-wide", LEVEL_STYLE[line.level])}
                  >
                    {LEVEL_TAG[line.level]}
                  </span>
                  <span className={clsx("min-w-0 break-words", LEVEL_STYLE[line.level])}>{line.text}</span>
                </li>
              ))}
            </ul>
          )}
          {live && (
            <div className="proc-log-cursor mt-1 flex items-center gap-1 font-mono text-[10px] text-brand-700 dark:text-brand-400">
              <span className="opacity-70">›</span>
              <span className="proc-caret h-3 w-1.5 bg-brand-500/80 dark:bg-brand-400/70" aria-hidden />
            </div>
          )}
        </div>
      </section>

      <div className="hidden w-[7.5rem] shrink-0 sm:block">
        <SheetScanSkeleton phase={phase} />
      </div>
    </div>
  );
}
