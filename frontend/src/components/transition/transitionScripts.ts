import type { LogLevel } from "@/components/processing/useAnalysisLog";

/** Workflow steps that show the fullscreen transition overlay. */
export type TransitionPhase = "to-setup" | "to-validate" | "to-analyze" | "to-demo";

export type ScriptLine = { level: LogLevel; text: string; delayMs: number };

export const TRANSITION_TITLES: Record<TransitionPhase, string> = {
  "to-setup": "Opening Setup",
  "to-validate": "Saving & validating",
  "to-analyze": "Queuing analysis",
  "to-demo": "Starting demo plant",
};

export const TRANSITION_SUBTITLES: Record<TransitionPhase, string> = {
  "to-setup": "Loading column mapping and plant architecture…",
  "to-validate": "Persisting config and starting data checks…",
  "to-analyze": "Acknowledging checks and starting fault modules…",
  "to-demo": "Preparing sample SCADA and architecture…",
};

/** PIC-relevant paced lines — honest work, not fake tech gibberish. */
export const TRANSITION_SCRIPTS: Record<TransitionPhase, ScriptLine[]> = {
  "to-setup": [
    { level: "run", text: "Loading detected column headers…", delayMs: 0 },
    { level: "run", text: "Preparing mapping suggestions…", delayMs: 420 },
    { level: "info", text: "Checking timestamp & interval candidates…", delayMs: 820 },
    { level: "run", text: "Loading plant architecture summary…", delayMs: 1180 },
    { level: "ok", text: "Setup workspace ready", delayMs: 1600 },
  ],
  "to-validate": [
    { level: "run", text: "Saving column mapping…", delayMs: 0 },
    { level: "run", text: "Writing plant ratings & architecture…", delayMs: 380 },
    { level: "info", text: "Checking timestamp parse coverage…", delayMs: 780 },
    { level: "run", text: "Scoring fault-module readiness…", delayMs: 1120 },
    { level: "ok", text: "Handing off to validation gate…", delayMs: 1500 },
  ],
  "to-analyze": [
    { level: "run", text: "Acknowledging validation results…", delayMs: 0 },
    { level: "info", text: "Queuing PR / yield / availability…", delayMs: 400 },
    { level: "run", text: "Scheduling string & inverter diagnostics…", delayMs: 820 },
    { level: "run", text: "Warming loss-bridge inputs…", delayMs: 1180 },
    { level: "ok", text: "Analysis job queued", delayMs: 1550 },
  ],
  "to-demo": [
    { level: "run", text: "Provisioning demo job…", delayMs: 0 },
    { level: "info", text: "Loading sample SCADA sheet…", delayMs: 360 },
    { level: "run", text: "Applying demo mapping & architecture…", delayMs: 760 },
    { level: "ok", text: "Demo analysis starting…", delayMs: 1180 },
  ],
};
