import { SectionPanel } from "@/components/ui/SectionPanel";
import type { SummaryUnitRow } from "@/lib/summaryInsights";

const TONE_DOT: Record<SummaryUnitRow["tone"], string> = {
  bad: "bg-rose-500",
  warn: "bg-amber-500",
  ok: "bg-emerald-500",
  neutral: "bg-stone-400",
};

const TONE_METRIC: Record<SummaryUnitRow["tone"], string> = {
  bad: "text-rose-700 dark:text-rose-300",
  warn: "text-amber-800 dark:text-amber-200",
  ok: "text-emerald-700 dark:text-emerald-300",
  neutral: "text-stone-700 dark:text-stone-200",
};

function InsightList({
  rows,
  empty,
  onSelect,
}: {
  rows: SummaryUnitRow[];
  empty: string;
  onSelect: (algorithmId: string) => void;
}) {
  if (rows.length === 0) {
    return <p className="px-1 py-2 text-xs leading-relaxed text-stone-500 dark:text-stone-400">{empty}</p>;
  }

  return (
    <ul className="divide-y divide-stone-100 dark:divide-stone-800/80">
      {rows.map((row) => (
        <li key={row.id}>
          <button
            type="button"
            className="flex w-full items-center gap-3 px-1 py-2.5 text-left transition hover:bg-stone-50/80 dark:hover:bg-stone-800/40"
            onClick={() => onSelect(row.algorithmId)}
          >
            <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${TONE_DOT[row.tone]}`} aria-hidden />
            <div className="min-w-0 flex-1">
              <p className="truncate text-[13px] font-semibold text-stone-900 dark:text-stone-50">{row.label}</p>
              {row.detail ? (
                <p className="mt-0.5 truncate text-[11px] text-stone-500 dark:text-stone-400">{row.detail}</p>
              ) : null}
            </div>
            <p className={`shrink-0 text-xs font-semibold tabular-nums ${TONE_METRIC[row.tone]}`}>{row.metric}</p>
          </button>
        </li>
      ))}
    </ul>
  );
}

/** Compact detail panels for Summary — worst inverters + string/SCB health. */
export function SummaryInsightPanels({
  worstInverters,
  stringHealth,
  stringHealthyNote,
  onModule,
}: {
  worstInverters: SummaryUnitRow[];
  stringHealth: SummaryUnitRow[];
  stringHealthyNote: string | null;
  onModule: (algorithmId: string) => void;
}) {
  return (
    <div className="grid gap-3 lg:grid-cols-2" data-tour="summary-insights">
      <SectionPanel
        title="Worst inverters"
        description="Highest conversion / clip loss share"
        accent="rose"
        scrollMargin={false}
        bodyClassName="px-3.5 pb-2.5 pt-1"
      >
        <InsightList
          rows={worstInverters}
          empty="No inverter loss ranking yet — map AC + DC (or SCB current) and re-run."
          onSelect={onModule}
        />
      </SectionPanel>

      <SectionPanel
        title="String health"
        description="Disconnected strings and voltage faults"
        accent="amber"
        scrollMargin={false}
        bodyClassName="px-3.5 pb-2.5 pt-1"
      >
        <InsightList
          rows={stringHealth}
          empty={stringHealthyNote ?? "No string/SCB findings to list."}
          onSelect={onModule}
        />
      </SectionPanel>
    </div>
  );
}
