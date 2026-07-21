/**
 * Shared contract between Results sidebar/tabs and the demo tour.
 * Tour activates a section first, then spotlights — no mega-page scroll thrash.
 *
 * Flat nav (4 sections). Diagnostics modules are picked from the folder list
 * inside the Diagnostics main pane (not nested in the Results sidebar).
 *
 * Nav buttons should expose:
 *   data-results-section="{id}"  and  data-tour="nav-{id}"
 * Diagnostics folder items also expose:
 *   data-results-section="{algorithm_id}"  and  data-tour="nav-diag-{algorithm_id}"
 * Listeners receive window event `pic:results-section` with detail = section id
 * or algorithm_id string (module deep-link opens Diagnostics + that folder item).
 */

export const RESULTS_SECTIONS = [
  { id: "summary", label: "Summary", tour: "nav-summary" },
  { id: "bridge", label: "Loss bridge", tour: "nav-bridge" },
  { id: "faults", label: "Faults", tour: "nav-faults" },
  { id: "diagnostics", label: "Diagnostics", tour: "nav-diagnostics" },
] as const;

export type ResultsSectionId = (typeof RESULTS_SECTIONS)[number]["id"];

export const RESULTS_SECTION_EVENT = "pic:results-section";

/** Legacy tour/deep-link aliases → current section ids. */
const SECTION_ALIASES: Record<string, ResultsSectionId> = {
  actions: "summary",
  "owner-actions": "summary",
  "owner_actions": "summary",
};

export function resolveResultsSectionId(v: unknown): ResultsSectionId | null {
  if (typeof v !== "string" || !v) return null;
  if (SECTION_ALIASES[v]) return SECTION_ALIASES[v];
  if (RESULTS_SECTIONS.some((s) => s.id === v)) return v as ResultsSectionId;
  return null;
}

export function isResultsSectionId(v: unknown): v is ResultsSectionId {
  return typeof v === "string" && RESULTS_SECTIONS.some((s) => s.id === v);
}

function sleep(ms: number): Promise<void> {
  return new Promise((r) => setTimeout(r, ms));
}

/** Ask Results UI to show a section (detail is the id string). */
export function requestResultsSection(id: string): void {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new CustomEvent(RESULTS_SECTION_EVENT, { detail: id }));
}

/**
 * Activate one Results section. Tries sidebar/tab buttons first, then dispatches
 * `pic:results-section`. Accepts fallbacks (e.g. ["summary","bridge"]).
 * Also accepts algorithm ids for Diagnostics module deep-links.
 */
export async function activateResultsSection(
  section: string | string[] | undefined,
): Promise<string | null> {
  if (!section) return null;
  const ids = Array.isArray(section) ? section : [section];
  if (!ids.length) return null;

  for (const raw of ids) {
    const id = SECTION_ALIASES[raw] ?? raw;
    const btn = document.querySelector<HTMLElement>(
      `[data-results-section="${id}"], [data-tour="nav-${id}"], [data-tour="nav-diag-${id}"]`,
    );
    if (btn) {
      btn.click();
      await sleep(80);
      return id;
    }
  }

  const fallback = SECTION_ALIASES[ids[0]] ?? ids[0];
  requestResultsSection(fallback);
  await sleep(80);
  return fallback;
}

/** True when the element is effectively visible in the viewport. */
export function isMostlyInView(el: Element, margin = 72): boolean {
  const r = el.getBoundingClientRect();
  if (r.width < 2 || r.height < 2) return false;
  const vh = window.innerHeight;
  return r.bottom > margin && r.top < vh - margin;
}
