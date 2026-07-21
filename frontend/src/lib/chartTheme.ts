/** Shared chart colours — amber / emerald / rose (no blue). */

export const CHART_SEGMENT = {
  expected: "#57534e", // stone-600 — reference, not a fault
  actual: "#047857", // emerald-700 — delivered energy
  loss: "#dc2626", // rose-600 — diagnosed fault loss
  unknown: "#78716c", // stone-500 — unattributed gap
  brand: "#d97706", // amber-600
  brandSoft: "rgba(217, 119, 6, 0.28)",
  brandLine: "#b45309",
} as const;

export const CHART_PALETTE = [
  "#d97706",
  "#059669",
  "#dc2626",
  "#a16207",
  "#047857",
  "#e11d48",
  "#ca8a04",
  "#16a34a",
] as const;

/** Replace common Plotly default blues with brand amber. */
export function recolorBlueTraces(data: unknown[]): unknown[] {
  if (!Array.isArray(data)) return data;
  return data.map((raw) => {
    const t = raw as Record<string, unknown>;
    if (!t || typeof t !== "object") return raw;
    const next = { ...t };
    const line = next.line as Record<string, unknown> | undefined;
    if (line && typeof line.color === "string" && isBlueish(line.color)) {
      next.line = { ...line, color: CHART_SEGMENT.brandLine };
    }
    const marker = next.marker as Record<string, unknown> | undefined;
    if (marker && typeof marker.color === "string" && isBlueish(marker.color)) {
      next.marker = { ...marker, color: CHART_SEGMENT.brandSoft };
    }
    if (typeof next.fillcolor === "string" && isBlueish(next.fillcolor)) {
      next.fillcolor = CHART_SEGMENT.brandSoft;
    }
    return next;
  });
}

function isBlueish(color: string): boolean {
  const c = color.toLowerCase();
  return (
    c.includes("0284c7") ||
    c.includes("0ea5e9") ||
    c.includes("38bdf8") ||
    c.includes("0891b2") ||
    c.includes("3b82f6") ||
    c.includes("2563eb") ||
    c.includes("14,165,233") ||
    c.includes("2,132,199") ||
    c.includes("sky") ||
    c.includes("blue")
  );
}

/** Standard paper margins (no modebar — keep modest padding only). */
export function plotlySafeMargins(extra?: {
  t?: number;
  r?: number;
  b?: number;
  l?: number;
  pad?: number;
}): Record<string, number> {
  return {
    t: 28,
    r: 28,
    b: 64,
    l: 56,
    pad: 4,
    ...extra,
  };
}

/** Neutral hover tooltip — never inherit bar fill (avoids stuck green boxes on Actual). */
export function plotlyHoverLabel(dark: boolean): Record<string, unknown> {
  return {
    bgcolor: dark ? "rgba(28,25,23,0.96)" : "rgba(255,255,255,0.98)",
    bordercolor: dark ? "#57534e" : "#d6d3d1",
    font: {
      size: 12,
      color: dark ? "#e7e5e4" : "#292524",
      family: "DM Sans, Segoe UI, system-ui, sans-serif",
    },
    align: "left",
  };
}

/** Modebar permanently off — use downloadPlotlyPng + external button instead. */
export function plotlyUiConfig(_filename = "chart"): Record<string, unknown> {
  return {
    responsive: true,
    displaylogo: false,
    displayModeBar: false,
    staticPlot: false,
  };
}

/** PNG export via Plotly API (external button, not the floating modebar). */
export async function downloadPlotlyPng(
  host: HTMLElement | null | undefined,
  filename: string,
): Promise<void> {
  const gd = host?.querySelector(".js-plotly-plot") as HTMLElement | null;
  if (!gd) return;

  type PlotlyApi = {
    downloadImage: (
      el: HTMLElement,
      opts: { format: "png"; filename: string; width?: number; height?: number },
    ) => Promise<unknown>;
  };

  const fromWindow = (window as unknown as { Plotly?: PlotlyApi }).Plotly;
  if (fromWindow?.downloadImage) {
    await fromWindow.downloadImage(gd, { format: "png", filename });
    return;
  }

  const mod = (await import("plotly.js")) as unknown as { default?: PlotlyApi } & PlotlyApi;
  const Plotly = mod.default ?? mod;
  await Plotly.downloadImage(gd, { format: "png", filename });
}
