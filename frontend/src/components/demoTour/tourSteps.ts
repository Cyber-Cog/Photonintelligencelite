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
    body: "Sample SCADA ran through the full pipeline. Use the left Results sidebar to jump sections and tools — this short tour covers the highlights.",
    route: "dashboard",
    selector: "[data-tour='results-welcome']",
    resultsSection: "overview",
    placement: "bottom",
  },
  {
    id: "summary",
    title: "Summary KPIs",
    body: "Ten plant KPIs in one dense band. Summary also holds integrity status and the Action Centre; Performance covers inverter and string health.",
    route: "dashboard",
    selector: "[data-tour='summary-kpis']",
    resultsSection: ["overview", "summary"],
    placement: "bottom",
  },
  {
    id: "loss-bridge",
    title: "Losses",
    body: "Expected → diagnosed losses → unknown → actual. Open Losses for the waterfall chart and segment table.",
    route: "dashboard",
    selector: "[data-tour='loss-bridge']",
    resultsSection: ["losses", "bridge"],
    placement: "top",
  },
  {
    id: "faults",
    title: "Faults & Investigate",
    body: "Every finding in one table with Actionable / Non-actionable tabs. Open Investigate for evidence charts and intervals.",
    route: "dashboard",
    selector: "[data-tour='faults-table']",
    resultsSection: "faults",
    placement: "top",
  },
  {
    id: "diagnostics",
    title: "Devices modules",
    body: "Open Devices in the sidebar: fault checks and box plot analysis nest underneath. Status chips are Healthy / Findings / Needs data.",
    route: "dashboard",
    selector: "[data-tour^='nav-diag-'], #results-devices-subnav button[data-results-section]",
    resultsSection: ["diagnostics", "devices"],
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
    body: "Export an operator PDF or a spreadsheet of results to share with the site team — also under Reports in the sidebar.",
    route: "dashboard",
    selector: "[data-tour='download-reports']",
    resultsSection: ["reports", "overview", "summary"],
    placement: "left",
  },
  {
    id: "done",
    title: "You're ready",
    body: "That’s the workspace. Run your own upload anytime, or replay this tour from Profile settings.",
    route: "dashboard",
    resultsSection: ["overview", "summary"],
    placement: "center",
  },
];
