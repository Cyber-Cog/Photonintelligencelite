import type { LogLevel } from "@/components/processing/useAnalysisLog";

/** Workflow steps that show the fullscreen transition overlay. */
export type TransitionPhase = "to-setup" | "to-validate" | "to-analyze" | "to-demo";

export type ScriptLine = { level: LogLevel; text: string; delayMs: number };

export const TRANSITION_TITLES: Record<TransitionPhase, string> = {
  "to-setup": "Opening Setup",
  "to-validate": "Saving setup",
  "to-analyze": "Queuing analysis",
  "to-demo": "Starting demo plant",
};

export const TRANSITION_SUBTITLES: Record<TransitionPhase, string> = {
  "to-setup": "Loading column mapping and plant architecture…",
  "to-validate": "Persisting config — validation continues on the next page…",
  "to-analyze": "Acknowledging checks and starting fault modules…",
  "to-demo": "Preparing sample SCADA and architecture…",
};

/** Short paced lines — Continue APIs return fast; Validate page polls the heavy work. */
export const TRANSITION_SCRIPTS: Record<TransitionPhase, ScriptLine[]> = {
  "to-setup": [
    { level: "run", text: "Loading detected column headers…", delayMs: 0 },
    { level: "run", text: "Preparing mapping suggestions…", delayMs: 180 },
    { level: "ok", text: "Setup workspace ready", delayMs: 360 },
  ],
  "to-validate": [
    { level: "run", text: "Saving column mapping…", delayMs: 0 },
    { level: "run", text: "Writing plant ratings & architecture…", delayMs: 160 },
    { level: "ok", text: "Handing off to validation…", delayMs: 320 },
  ],
  "to-analyze": [
    { level: "run", text: "Acknowledging validation results…", delayMs: 0 },
    { level: "run", text: "Queuing fault modules…", delayMs: 180 },
    { level: "ok", text: "Analysis job queued", delayMs: 360 },
  ],
  "to-demo": [
    { level: "run", text: "Provisioning demo job…", delayMs: 0 },
    { level: "info", text: "Loading sample SCADA…", delayMs: 160 },
    { level: "ok", text: "Demo analysis starting…", delayMs: 320 },
  ],
};
