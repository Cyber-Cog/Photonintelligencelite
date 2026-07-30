import { SectionPanel } from "@/components/ui/SectionPanel";
import type { InverterPrRow } from "@/types";

/**
 * Color scale for inverter PR bars (site scan).
 * Low PR → rose/amber (poor); high PR → emerald (good).
 * Relative to the min–max of this plant so underperformers stand out quickly.
 */
function prFill(pr: number, minPr: number, maxPr: number): string {
  const span = Math.max(maxPr - minPr, 0.5);
  const t = Math.min(1, Math.max(0, (pr - minPr) / span));
  // rose (0°) → amber (38°) → emerald (~145°)
  const hue = t < 0.5 ? 8 + t * 2 * 30 : 38 + (t - 0.5) * 2 * 107;
  const sat = 72 - t * 12;
  const light = 42 + t * 8;
  return `hsl(${hue.toFixed(0)} ${sat.toFixed(0)}% ${light.toFixed(0)}%)`;
}

function prBarWidthPct(pr: number, maxPr: number): number {
  if (!(maxPr > 0)) return 0;
  return Math.min(100, Math.max(4, (pr / maxPr) * 100));
}

/** Dense all-inverter PR comparison for Results Summary (analysis framing, not a fault). */
export function InverterComparisonPanel({ rows }: { rows: InverterPrRow[] }) {
  if (!rows.length) {
    return (
      <div data-tour="inverter-comparison">
        <SectionPanel
          title="Inverter comparison"
          description="Performance ratio by inverter — needs AC power, irradiance, and DC capacity"
          accent="brand"
          scrollMargin={false}
          bodyClassName="px-3.5 pb-3 pt-1"
        >
          <p className="text-xs leading-relaxed text-stone-500 dark:text-stone-400">
            Per-inverter PR is unavailable for this run. Map inverter AC power and POA/GHI, set plant (or SCB) DC
            capacity, then re-run.
          </p>
        </SectionPanel>
      </div>
    );
  }

  const prs = rows.map((r) => r.pr_pct);
  const minPr = Math.min(...prs);
  const maxPr = Math.max(...prs);
  const plantSpread = maxPr - minPr;

  return (
    <SectionPanel
      title="Inverter comparison"
      description={
        <>
          PR of every inverter · emerald = high, rose/amber = low
          {plantSpread >= 0.05 ? (
            <span className="text-stone-400">
              {" "}
              · spread {plantSpread.toFixed(1)} pts
            </span>
          ) : null}
        </>
      }
      accent="brand"
      scrollMargin={false}
      bodyClassName="px-3.5 pb-2.5 pt-1"
    >
      <div data-tour="inverter-comparison" className="space-y-1">
        <div className="mb-1.5 flex items-center justify-between gap-2 text-[10px] font-semibold uppercase tracking-wide text-stone-400">
          <span>Low</span>
          <span
            className="h-1.5 flex-1 rounded-full"
            style={{
              background: "linear-gradient(90deg, hsl(8 72% 46%), hsl(38 70% 48%), hsl(145 55% 40%))",
            }}
            aria-hidden
          />
          <span>High PR</span>
        </div>

        <ul className="divide-y divide-stone-100 dark:divide-stone-800/80">
          {rows.map((row) => {
            const fill = prFill(row.pr_pct, minPr, maxPr);
            const width = prBarWidthPct(row.pr_pct, maxPr);
            return (
              <li key={row.inverter_id} className="flex items-center gap-2.5 py-1.5">
                <p className="w-[5.5rem] shrink-0 truncate text-[12px] font-semibold text-stone-900 dark:text-stone-50 sm:w-28">
                  {row.inverter_id}
                </p>
                <div className="min-w-0 flex-1">
                  <div className="h-2 overflow-hidden rounded-sm bg-stone-100 dark:bg-stone-800">
                    <div
                      className="h-full rounded-sm transition-[width]"
                      style={{ width: `${width}%`, backgroundColor: fill }}
                      title={`${row.pr_pct.toFixed(1)}% PR · ${row.ac_energy_kwh.toLocaleString()} kWh · ${row.dc_kwp} kWp`}
                    />
                  </div>
                </div>
                <p
                  className="w-14 shrink-0 text-right text-[12px] font-semibold tabular-nums"
                  style={{ color: fill }}
                >
                  {row.pr_pct.toFixed(1)}%
                </p>
              </li>
            );
          })}
        </ul>
      </div>
    </SectionPanel>
  );
}
