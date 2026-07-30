import { useEffect, useRef, useState } from "react";
import type { AnalysisLogLine, LogLevel } from "@/components/processing/useAnalysisLog";

export type UploadActivityPhase = "uploading" | "parsing";

/** Honest staged copy while Excel→CSV runs — not fake metrics. */
const PARSE_STAGES: { level: LogLevel; text: string }[] = [
  { level: "run", text: "Reading workbook structure…" },
  { level: "run", text: "Detecting header rows…" },
  { level: "run", text: "Normalizing sheets…" },
  { level: "run", text: "Extracting columns & sample rows…" },
  { level: "info", text: "Wide workbooks can take up to a minute…" },
];

function prefersReducedMotion(): boolean {
  return typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

function isDefaultParseHint(msg: string): boolean {
  return msg.startsWith("Parsing Excel workbook");
}

/**
 * Compact console log for the Upload page during upload + Excel parse wait.
 * Advances with real phase / API progress_message, plus paced honest stages while parsing.
 */
export function useParseActivityLog(
  active: boolean,
  phase: UploadActivityPhase | null,
  progressMessage: string | null | undefined,
  fileNames: string[],
  uploadPct: number,
  elapsedSec: number,
): AnalysisLogLine[] {
  const [lines, setLines] = useState<AnalysisLogLine[]>([]);
  const seenPhase = useRef<string | null>(null);
  const lastProgress = useRef<string | null>(null);
  const lastPctBucket = useRef(-1);
  const skippedDefaultParse = useRef(false);
  const stageIndex = useRef(0);
  const stageTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const seq = useRef(0);
  const elapsedRef = useRef(elapsedSec);
  elapsedRef.current = elapsedSec;
  const filesKey = fileNames.join("\0");

  const push = (level: LogLevel, text: string) => {
    seq.current += 1;
    const id = `U${seq.current}`;
    setLines((prev) => {
      const next = [...prev, { id, level, text, elapsedSec: elapsedRef.current }];
      return next.length > 40 ? next.slice(-40) : next;
    });
  };

  // Reset when inactive
  useEffect(() => {
    if (active) return;
    setLines([]);
    seenPhase.current = null;
    lastProgress.current = null;
    lastPctBucket.current = -1;
    skippedDefaultParse.current = false;
    stageIndex.current = 0;
    if (stageTimer.current) {
      clearTimeout(stageTimer.current);
      stageTimer.current = null;
    }
  }, [active]);

  // Bootstrap when upload / parse phase starts
  useEffect(() => {
    if (!active || !phase) return;
    if (seenPhase.current === phase) return;

    const prev = seenPhase.current;
    seenPhase.current = phase;

    if (phase === "uploading" && prev == null) {
      const n = fileNames.length;
      const label =
        n === 1
          ? fileNames[0] || "1 file"
          : `${n} files · ${fileNames.slice(0, 2).join(", ")}${n > 2 ? "…" : ""}`;
      push("info", `Queued transfer · ${label}`);
      push("run", "Uploading to PIC Lite…");
      return;
    }

    if (phase === "parsing") {
      if (prev === "uploading") {
        push("ok", "Upload received");
      }
      push("run", "Opening Excel workbook…");
      stageIndex.current = 0;
    }
    // fileNames via filesKey; push is stable enough for mount transitions
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active, phase, filesKey]);

  // Upload progress buckets (avoid spam)
  useEffect(() => {
    if (!active || phase !== "uploading") return;
    const bucket = Math.floor(uploadPct / 25);
    if (bucket === lastPctBucket.current) return;
    if (uploadPct <= 0) return;
    lastPctBucket.current = bucket;
    if (uploadPct >= 100) {
      push("ok", "Bytes transferred — awaiting parse worker");
    } else if (bucket >= 1) {
      push("info", `Transfer ${Math.min(uploadPct, 99)}%`);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active, phase, uploadPct]);

  // Real API progress_message (skip generic default once — phase already said "Opening Excel…")
  useEffect(() => {
    if (!active || !progressMessage) return;
    if (progressMessage === lastProgress.current) return;
    lastProgress.current = progressMessage;

    if (isDefaultParseHint(progressMessage)) {
      if (skippedDefaultParse.current) return;
      skippedDefaultParse.current = true;
      return;
    }

    push("info", progressMessage);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active, progressMessage]);

  // Pace honest parse stages
  useEffect(() => {
    if (stageTimer.current) {
      clearTimeout(stageTimer.current);
      stageTimer.current = null;
    }
    if (!active || phase !== "parsing") return;

    const reduced = prefersReducedMotion();
    const intervalMs = reduced ? 500 : 1600;

    const tick = () => {
      if (stageIndex.current >= PARSE_STAGES.length) {
        push("wait", "Still parsing — large multi-sheet reports take longer");
        return;
      }
      const stage = PARSE_STAGES[stageIndex.current];
      if (stageIndex.current > 0) {
        const prev = PARSE_STAGES[stageIndex.current - 1];
        if (prev.level === "run") {
          push("ok", `${prev.text.replace(/\.\.\.$/, "")} — done`);
        }
      }
      push(stage.level, stage.text);
      stageIndex.current += 1;
      if (stageIndex.current < PARSE_STAGES.length) {
        stageTimer.current = setTimeout(tick, intervalMs);
      } else {
        stageTimer.current = setTimeout(() => {
          push("wait", "Still parsing — large multi-sheet reports take longer");
        }, intervalMs * 2);
      }
    };

    stageTimer.current = setTimeout(tick, reduced ? 250 : 600);

    return () => {
      if (stageTimer.current) clearTimeout(stageTimer.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active, phase]);

  return lines;
}
