import { useEffect, useRef, useState } from "react";
import { ALGORITHM_DOCS } from "@/content/algorithms";

export type LogLevel = "info" | "ok" | "run" | "wait" | "warn";

export interface AnalysisLogLine {
  id: string;
  level: LogLevel;
  text: string;
  /** Relative elapsed seconds when the line was appended (for display). */
  elapsedSec: number;
}

const ALGORITHM_TITLES = ALGORITHM_DOCS.map((d) => d.title);

/** Chart titles shown during generating_charts — honest prep labels, not fabricated results. */
export const CHART_PREP_LABELS = [
  "Performance ratio trend",
  "Loss waterfall",
  "Inverter efficiency distribution",
  "Investigate: expected vs measured",
];

function prefersReducedMotion(): boolean {
  return typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

function phaseRank(state: string | null | undefined): number {
  const order = ["queued", "running", "generating_charts", "generating_report", "completed"];
  if (!state) return -1;
  const i = order.indexOf(state);
  return i >= 0 ? i : state === "failed" ? 99 : -1;
}

/**
 * Builds a staged console log that advances with real job state transitions.
 * Algorithm lines are paced while `running`, then flushed when charts/report start.
 */
export function useAnalysisLog(
  state: string | null | undefined,
  progressMessage: string | null | undefined,
  queuePosition: number | null | undefined,
  elapsedSec: number,
): AnalysisLogLine[] {
  const [lines, setLines] = useState<AnalysisLogLine[]>([]);
  const seenStates = useRef<Set<string>>(new Set());
  const algoIndex = useRef(0);
  const algoTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const lastProgress = useRef<string | null>(null);
  const seq = useRef(0);
  const elapsedRef = useRef(elapsedSec);
  elapsedRef.current = elapsedSec;

  const push = (level: LogLevel, text: string) => {
    seq.current += 1;
    const id = `L${seq.current}`;
    setLines((prev) => {
      const next = [...prev, { id, level, text, elapsedSec: elapsedRef.current }];
      return next.length > 80 ? next.slice(-80) : next;
    });
  };

  // Bootstrap + state transitions
  useEffect(() => {
    if (!state) {
      if (!seenStates.current.has("__boot")) {
        seenStates.current.add("__boot");
        push("info", "Connecting to analysis service…");
      }
      return;
    }

    if (seenStates.current.has(state)) return;
    seenStates.current.add(state);

    if (state === "queued") {
      push("wait", "Job queued — waiting for an available worker");
      return;
    }
    if (state === "running") {
      push("ok", "Worker claimed job");
      push("run", "Loading canonical SCADA frame & plant architecture…");
      push("run", "Dispatching fault & loss modules…");
      return;
    }
    if (state === "generating_charts") {
      // Mark the in-flight module done, then any not-yet-shown modules.
      if (algoIndex.current > 0 && algoIndex.current <= ALGORITHM_TITLES.length) {
        push("ok", `Module complete · ${ALGORITHM_TITLES[algoIndex.current - 1]}`);
      }
      for (let i = algoIndex.current; i < ALGORITHM_TITLES.length; i++) {
        push("ok", `Module complete · ${ALGORITHM_TITLES[i]}`);
      }
      algoIndex.current = ALGORITHM_TITLES.length;
      push("ok", "Algorithm pass finished");
      push("run", "Building dashboard chart figures…");
      return;
    }
    if (state === "generating_report") {
      push("ok", "Chart figures ready");
      push("run", "Generating PDF and Excel reports…");
      return;
    }
    if (state === "completed") {
      push("ok", "Analysis complete — opening results…");
      return;
    }
    if (state === "failed") {
      push("warn", "Analysis stopped — see error details");
    }
  }, [state]);

  // Surface truthful API progress_message when it changes (skip noisy queue copy)
  useEffect(() => {
    if (!progressMessage) return;
    if (progressMessage === lastProgress.current) return;
    if (progressMessage.startsWith("Another job is currently running")) return;
    lastProgress.current = progressMessage;

    // Avoid duplicating the same text we already staged for this state
    const mutedDupes = [
      "Running analysis algorithms…",
      "Building dashboard charts…",
      "Generating PDF and Excel reports…",
      "Analysis complete.",
    ];
    if (mutedDupes.includes(progressMessage)) return;

    push("info", progressMessage);
  }, [progressMessage]);

  // Queue position updates
  useEffect(() => {
    if (state !== "queued") return;
    if (queuePosition == null || queuePosition <= 0) return;
    push("wait", `Queue position ${queuePosition}`);
  }, [state, queuePosition]);

  // Pace algorithm unveil while running
  useEffect(() => {
    if (algoTimer.current) {
      clearTimeout(algoTimer.current);
      algoTimer.current = null;
    }
    if (state !== "running") return;

    const reduced = prefersReducedMotion();
    const intervalMs = reduced ? 400 : 1400;

    const tick = () => {
      if (algoIndex.current >= ALGORITHM_TITLES.length) {
        push("info", "Still computing — large sites can take a few minutes");
        return;
      }
      const title = ALGORITHM_TITLES[algoIndex.current];
      if (algoIndex.current > 0) {
        const prev = ALGORITHM_TITLES[algoIndex.current - 1];
        push("ok", `Module complete · ${prev}`);
      }
      push("run", `Executing · ${title}`);
      algoIndex.current += 1;
      if (algoIndex.current < ALGORITHM_TITLES.length) {
        algoTimer.current = setTimeout(tick, intervalMs);
      } else {
        push("info", "Finalizing residual loss aggregates…");
      }
    };

    // First algorithm shortly after entering running
    algoTimer.current = setTimeout(tick, reduced ? 200 : 700);

    return () => {
      if (algoTimer.current) clearTimeout(algoTimer.current);
    };
  }, [state]);

  // When leaving running early (rare), don't leave timers hanging — handled by cleanup above
  useEffect(() => {
    if (phaseRank(state) > phaseRank("running") && state !== "failed") {
      if (algoTimer.current) {
        clearTimeout(algoTimer.current);
        algoTimer.current = null;
      }
    }
  }, [state]);

  return lines;
}
