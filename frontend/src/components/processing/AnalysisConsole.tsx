import { useEffect, useRef } from "react";
import clsx from "clsx";
import type { AnalysisLogLine, LogLevel } from "./useAnalysisLog";

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

export function AnalysisConsole({
  lines,
  live,
}: {
  lines: AnalysisLogLine[];
  live: boolean;
}) {
  const scrollerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = scrollerRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
  }, [lines]);

  return (
    <section
      className="proc-panel flex min-h-0 flex-1 flex-col overflow-hidden"
      aria-label="Analysis console"
    >
      <header className="flex shrink-0 items-center justify-between gap-2 border-b border-stone-200/80 px-3 py-1.5 dark:border-stone-700/80">
        <div className="flex items-center gap-2">
          <span className="font-display text-[11px] font-semibold uppercase tracking-[0.14em] text-stone-600 dark:text-stone-300">
            Analysis console
          </span>
          {live && (
            <span className="proc-live-dot inline-flex items-center gap-1.5 rounded-md bg-accent-50 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-accent-800 dark:bg-accent-950/50 dark:text-accent-300">
              <span className="h-1.5 w-1.5 rounded-full bg-accent-500" aria-hidden />
              Live
            </span>
          )}
        </div>
        <span className="font-mono text-[10px] text-stone-400 dark:text-stone-500">
          pic-pipeline · {lines.length} evt
        </span>
      </header>

      <div
        ref={scrollerRef}
        className="proc-log-scroll min-h-0 flex-1 overflow-y-auto px-3 py-2"
        role="log"
        aria-live="polite"
        aria-relevant="additions"
      >
        {lines.length === 0 ? (
          <p className="font-mono text-[11px] text-stone-400">Awaiting job status…</p>
        ) : (
          <ul className="space-y-0.5">
            {lines.map((line) => (
              <li
                key={line.id}
                className="proc-log-line flex gap-2 font-mono text-[11px] leading-snug sm:text-[12px]"
              >
                <span className="shrink-0 tabular-nums text-stone-400 dark:text-stone-500">
                  {formatClock(line.elapsedSec)}
                </span>
                <span
                  className={clsx(
                    "w-9 shrink-0 font-semibold tracking-wide",
                    LEVEL_STYLE[line.level],
                  )}
                >
                  {LEVEL_TAG[line.level]}
                </span>
                <span className={clsx("min-w-0 break-words", LEVEL_STYLE[line.level])}>{line.text}</span>
              </li>
            ))}
          </ul>
        )}
        {live && (
          <div className="proc-log-cursor mt-1 flex items-center gap-1.5 font-mono text-[11px] text-brand-700 dark:text-brand-400">
            <span className="opacity-70">›</span>
            <span className="proc-caret h-3.5 w-1.5 bg-brand-500/80 dark:bg-brand-400/70" aria-hidden />
          </div>
        )}
      </div>
    </section>
  );
}
