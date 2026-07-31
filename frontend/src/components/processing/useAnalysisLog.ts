import { useEffect, useRef, useState } from "react";
import { ALGORITHM_DOCS } from "@/content/algorithms";
import { classifyIntegrityProgressMessage } from "./analysisLogProgress";

export type LogLevel = "info" | "ok" | "run" | "wait" | "warn";

export interface AnalysisLogLine {
  id: string;
  level: LogLevel;
  text: string;
  /** Relative elapsed seconds when the line was appended (for display). */
  elapsedSec: number;
}

export interface AnalysisLogMeta {
  isDemo?: boolean;
  filename?: string | null;
}

const ALGORITHM_TITLES = ALGORITHM_DOCS.map((d) => d.title);

/** Chart titles shown during generating_charts — honest prep labels, not fabricated results. */
export const CHART_PREP_LABELS = [
  "Performance ratio trend",
  "Loss waterfall",
  "Inverter efficiency distribution",
  "Investigate: expected vs measured",
];

type Stage = { level: LogLevel; text: string };

/** Demo validating — paced while backend prepares demo CSV. */
const DEMO_VALIDATE_STAGES: Stage[] = [
  { level: "run", text: "Loading demo plant SCADA frame…" },
  { level: "run", text: "Applying fixed demo column map…" },
  { level: "run", text: "Checking timestamp continuity…" },
  { level: "run", text: "Spot-checking irradiance & AC coverage…" },
  { level: "run", text: "Verifying plant architecture bindings…" },
  { level: "info", text: "Demo validation can take 15–30s on a cold free-tier host…" },
];

/** Upload-path validating (rare on this page; still keep console alive). */
const UPLOAD_VALIDATE_STAGES: Stage[] = [
  { level: "run", text: "Reading mapped SCADA columns…" },
  { level: "run", text: "Checking timestamp parse rate…" },
  { level: "run", text: "Spot-checking irradiance coverage…" },
  { level: "run", text: "Verifying inverter AC channels…" },
  { level: "run", text: "Cross-checking plant capacity ratings…" },
  { level: "info", text: "Large multi-sheet uploads take longer at this gate…" },
];

const NORMALIZE_STAGES: Stage[] = [
  { level: "ok", text: "Validation checks passed" },
  { level: "run", text: "Finalizing validation summary…" },
  { level: "run", text: "Packaging plant architecture for the runner…" },
];

/** Queued / pre-worker handoff — keeps the tall console filled for upload jobs. */
const QUEUE_HANDOFF_STAGES: Stage[] = [
  { level: "ok", text: "Intake gate cleared — analysis handoff" },
  { level: "run", text: "Staging mapped columns into runner payload…" },
  { level: "run", text: "Confirming header stitch & canonical field bindings…" },
  { level: "run", text: "Checking plant architecture & capacity ratings…" },
  { level: "run", text: "Building fault & loss module execution order…" },
];

function prefersReducedMotion(): boolean {
  return typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

function phaseRank(state: string | null | undefined): number {
  const order = [
    "uploaded",
    "parsing",
    "mapping",
    "validating",
    "normalizing",
    "queued",
    "running",
    "generating_charts",
    "generating_report",
    "completed",
  ];
  if (!state) return -1;
  const i = order.indexOf(state);
  return i >= 0 ? i : state === "failed" ? 99 : -1;
}

function looksLikeDemoPrep(progressMessage: string | null | undefined, isDemo?: boolean): boolean {
  if (isDemo) return true;
  if (!progressMessage) return false;
  return /demo/i.test(progressMessage);
}

/**
 * Builds a staged console log that advances with real job state transitions.
 * Early states (validating / normalizing / queued) get paced honest activity so
 * upload jobs don't leave a tall empty console; algorithms pace while `running`.
 */
export function useAnalysisLog(
  state: string | null | undefined,
  progressMessage: string | null | undefined,
  queuePosition: number | null | undefined,
  elapsedSec: number,
  meta: AnalysisLogMeta = {},
): AnalysisLogLine[] {
  const [lines, setLines] = useState<AnalysisLogLine[]>([]);
  const seenStates = useRef<Set<string>>(new Set());
  const algoIndex = useRef(0);
  const algoTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const stageTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const heartbeatTimer = useRef<ReturnType<typeof setInterval> | null>(null);
  const lastProgress = useRef<string | null>(null);
  const lastHeartbeatBucket = useRef(-1);
  const stageIndex = useRef(0);
  const seq = useRef(0);
  const elapsedRef = useRef(elapsedSec);
  elapsedRef.current = elapsedSec;
  const metaRef = useRef(meta);
  metaRef.current = meta;
  const progressRef = useRef(progressMessage);
  progressRef.current = progressMessage;

  const push = (level: LogLevel, text: string) => {
    seq.current += 1;
    const id = `L${seq.current}`;
    setLines((prev) => {
      const next = [...prev, { id, level, text, elapsedSec: elapsedRef.current }];
      return next.length > 100 ? next.slice(-100) : next;
    });
  };

  const clearStageTimer = () => {
    if (stageTimer.current) {
      clearTimeout(stageTimer.current);
      stageTimer.current = null;
    }
  };

  const paceStages = (stages: Stage[], intervalMs: number, onDone?: () => void) => {
    clearStageTimer();
    stageIndex.current = 0;
    const reduced = prefersReducedMotion();
    const gap = reduced ? Math.min(intervalMs, 400) : intervalMs;

    const tick = () => {
      if (stageIndex.current >= stages.length) {
        onDone?.();
        return;
      }
      const stage = stages[stageIndex.current];
      if (stageIndex.current > 0) {
        const prev = stages[stageIndex.current - 1];
        if (prev.level === "run") {
          push("ok", `${prev.text.replace(/…$/, "").replace(/\.\.\.$/, "")} — done`);
        }
      }
      push(stage.level, stage.text);
      stageIndex.current += 1;
      if (stageIndex.current < stages.length) {
        stageTimer.current = setTimeout(tick, gap);
      } else {
        onDone?.();
      }
    };

    stageTimer.current = setTimeout(tick, reduced ? 150 : 350);
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

    const { isDemo, filename } = metaRef.current;
    const fileLabel = filename?.trim() || null;

    if (state === "uploaded" || state === "parsing") {
      push("info", fileLabel ? `Source · ${fileLabel}` : "Upload received");
      push("run", "Opening workbook / detecting sheets…");
      return;
    }
    if (state === "mapping") {
      push("wait", "Awaiting column mapping confirmation…");
      return;
    }
    if (state === "validating") {
      if (looksLikeDemoPrep(progressRef.current, isDemo)) {
        push("info", fileLabel ? `Demo source · ${fileLabel}` : "Demo plant SCADA staged");
        push("run", "Preparing demo data for analysis…");
      } else {
        push("info", fileLabel ? `Source · ${fileLabel}` : "Uploaded SCADA staged");
        push("run", "Running data validation gate…");
      }
      return;
    }
    if (state === "normalizing") {
      push("run", "Normalizing validated frame…");
      return;
    }
    if (state === "queued") {
      // Upload path often lands here directly after Validation — seed context so the console isn't empty.
      if (!seenStates.current.has("validating") && !seenStates.current.has("normalizing")) {
        push("ok", "Validation acknowledged");
        if (fileLabel) push("info", `Source · ${fileLabel}`);
        push("info", "Sheet detection & header stitch already completed at upload");
      } else if (looksLikeDemoPrep(progressRef.current, isDemo) || isDemo) {
        push("ok", "Demo preparation complete");
      }
      push("wait", "Job queued — waiting for an available worker");
      return;
    }
    if (state === "running") {
      clearStageTimer();
      push("ok", "Worker claimed job");
      push("run", "Loading canonical SCADA frame & plant architecture…");
      push("run", "Dispatching fault & loss modules…");
      return;
    }
    if (state === "generating_charts") {
      clearStageTimer();
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
      // If the final progress_message carried AI integrity (poll may have raced),
      // ensure it is visible even when the intermediate commit was missed.
      const pm = progressRef.current;
      if (pm && /AI integrity/i.test(pm) && pm !== lastProgress.current) {
        lastProgress.current = pm;
        const aiClass = classifyIntegrityProgressMessage(pm);
        if (aiClass.show) push(aiClass.level, pm);
        else push("info", pm);
      }
      return;
    }
    if (state === "failed") {
      clearStageTimer();
      push("warn", "Analysis stopped — see error details");
    }
  }, [state]);

  // Pace pre-run stages while validating / normalizing / queued
  useEffect(() => {
    clearStageTimer();
    if (!state) return;

    if (state === "validating") {
      const demo = looksLikeDemoPrep(progressRef.current, metaRef.current.isDemo);
      paceStages(demo ? DEMO_VALIDATE_STAGES : UPLOAD_VALIDATE_STAGES, 1500);
      return () => clearStageTimer();
    }

    if (state === "normalizing") {
      paceStages(NORMALIZE_STAGES, 900);
      return () => clearStageTimer();
    }

    if (state === "queued") {
      paceStages(QUEUE_HANDOFF_STAGES, 1100, () => {
        // After handoff, unveil module queue in a compact burst
        const titles = ALGORITHM_TITLES;
        const preview = titles.slice(0, 4).join(" → ");
        push("info", `Module queue · ${preview}${titles.length > 4 ? " → …" : ""}`);
        for (let i = 0; i < titles.length; i++) {
          push("wait", `Queued module · ${titles[i]}`);
        }
        push("wait", "Holding for free analysis worker…");
      });
      return () => clearStageTimer();
    }

    return () => clearStageTimer();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state]);

  // Surface truthful API progress_message when it changes (skip noisy queue copy)
  useEffect(() => {
    if (!progressMessage) return;
    if (progressMessage === lastProgress.current) return;
    if (progressMessage.startsWith("Another job is currently running")) return;
    lastProgress.current = progressMessage;

    // AI integrity lines — always show on the LIVE console (not a chatbot).
    const aiClass = classifyIntegrityProgressMessage(progressMessage);
    if (aiClass.show) {
      push(aiClass.level, progressMessage);
      return;
    }

    const mutedDupes = [
      "Running analysis algorithms…",
      "Building dashboard charts…",
      "Generating PDF and Excel reports…",
      "Analysis complete.",
      "Preparing demo data…",
      "Validating uploaded data…",
    ];
    if (mutedDupes.includes(progressMessage)) return;

    // Soft-mute generic queue strings we already staged
    if (/^Queued/i.test(progressMessage) && seenStates.current.has("queued")) return;

    push("info", progressMessage);
  }, [progressMessage]);

  // Queue position updates
  useEffect(() => {
    if (state !== "queued") return;
    if (queuePosition == null || queuePosition <= 0) return;
    push("wait", `Queue position ${queuePosition}`);
  }, [state, queuePosition]);

  // Heartbeats while validating / queued so the console keeps ticking
  useEffect(() => {
    if (heartbeatTimer.current) {
      clearInterval(heartbeatTimer.current);
      heartbeatTimer.current = null;
    }
    if (state !== "validating" && state !== "queued" && state !== "normalizing") {
      lastHeartbeatBucket.current = -1;
      return;
    }

    const reduced = prefersReducedMotion();
    const everySec = reduced ? 12 : 8;

    heartbeatTimer.current = setInterval(() => {
      const bucket = Math.floor(elapsedRef.current / everySec);
      if (bucket <= 0 || bucket === lastHeartbeatBucket.current) return;
      lastHeartbeatBucket.current = bucket;
      if (state === "queued") {
        push("wait", `Still queued · ${elapsedRef.current}s — workers busy or warming up`);
      } else if (state === "validating") {
        push("info", `Still validating · ${elapsedRef.current}s`);
      } else {
        push("info", `Still finalizing · ${elapsedRef.current}s`);
      }
    }, 1000);

    return () => {
      if (heartbeatTimer.current) {
        clearInterval(heartbeatTimer.current);
        heartbeatTimer.current = null;
      }
    };
  }, [state]);

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
