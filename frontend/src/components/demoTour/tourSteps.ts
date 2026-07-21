export type TourRoute = "dashboard" | "data" | "architecture" | "explore";

export type TourStepDef = {
  id: string;
  title: string;
  body: string;
  /** Job sub-route required for this step. */
  route: TourRoute;
  /** CSS selector — prefer [data-tour="…"]. Omit for centered welcome/done cards. */
  selector?: string;
  /**
   * Results sidebar/tab section(s) to activate before spotlighting.
   * Fallbacks work across stacked vs single-pane layouts.
   * Algorithm ids open the Diagnostics module pane.
   */
  resultsSection?: string | string[];
  /** Skip silently when the target is missing (e.g. Action Center when healthy). */
  optional?: boolean;
  /** Allow pointer events on the highlighted region. */
  allowInteract?: boolean;
  placement?: "auto" | "top" | "bottom" | "left" | "right" | "center";
};

/** Results steps switch sidebar panes (no mega-page scroll). Replay from Profile anytime. */
export const DEMO_TOUR_STEPS: TourStepDef[] = [
  {
    id: "welcome",
    title: "Your demo plant",
    body: "Sample SCADA ran through the full pipeline. Use the left nav to jump sections — this short tour covers the highlights.",
    route: "dashboard",
    selector: "[data-tour='results-welcome']",
    resultsSection: "summary",
    placement: "bottom",
  },
  {
    id: "summary",
    title: "Summary & actions",
    body: "KPIs first, then the Owner Action Center below — prioritized problems and a clear next step, without a separate nav item.",
    route: "dashboard",
    selector: "[data-tour='summary-kpis']",
    resultsSection: "summary",
    placement: "bottom",
  },
  {
    id: "loss-bridge",
    title: "Loss bridge",
    body: "A waterfall from expected energy to what the plant delivered — each bar is a loss bucket, with a segment table underneath.",
    route: "dashboard",
    selector: "[data-tour='loss-bridge']",
    resultsSection: "bridge",
    placement: "top",
  },
  {
    id: "faults",
    title: "Faults & Investigate",
    body: "Every finding in one table. Open Investigate for evidence charts and intervals tied to the fault.",
    route: "dashboard",
    selector: "[data-tour='faults-table']",
    resultsSection: "faults",
    placement: "top",
  },
  {
    id: "diagnostics",
    title: "Diagnostics modules",
    body: "Open Diagnostics, then pick a module from the narrow folder — summary and findings open in the wide pane; use Investigate for evidence charts.",
    route: "dashboard",
    selector: "[data-tour='diagnostics-folder-list'] button[data-results-section]",
    resultsSection: "diagnostics",
    optional: true,
    placement: "right",
  },
  {
    id: "raw-data",
    title: "Raw data",
    body: "Browse the underlying SCADA rows. Narrow by date range, then download a filtered CSV when you need it.",
    route: "data",
    selector: "[data-tour='raw-data-filters']",
    placement: "bottom",
    allowInteract: true,
  },
  {
    id: "explorer",
    title: "Signal Explorer",
    body: "Plot any signal over time at inverter, SCB, string, or weather level — great for validating a finding.",
    route: "explore",
    selector: "[data-tour='signal-explorer']",
    placement: "bottom",
    allowInteract: true,
  },
  {
    id: "downloads",
    title: "Download reports",
    body: "Export an operator PDF or a spreadsheet of results to share with the site team.",
    route: "dashboard",
    selector: "[data-tour='download-reports']",
    resultsSection: "summary",
    placement: "left",
  },
  {
    id: "done",
    title: "You're ready",
    body: "That’s the workspace. Run your own upload anytime, or replay this tour from Profile settings.",
    route: "dashboard",
    resultsSection: "summary",
    placement: "center",
  },
];
