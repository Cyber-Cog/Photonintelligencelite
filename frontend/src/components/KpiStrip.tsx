import { KpiCard } from "@/components/KpiCard";

type KpiTone = "neutral" | "good" | "bad";
type KpiIcon = "pr" | "yield" | "availability" | "loss" | "revenue" | "faults";

export type KpiStripItem = {
  label: string;
  value: number | string | null;
  unit?: string;
  tone?: KpiTone;
  icon?: KpiIcon;
  missingHint?: string | null;
  missingHref?: string | null;
};

/**
 * Plant KPI board — six visual tiles with tone washes and icons.
 * Prefer this over a flat label|value strip so the Results first viewport reads as a plant scoreboard.
 */
export function KpiStrip({ items, flush = false }: { items: KpiStripItem[]; flush?: boolean }) {
  const board = (
    <div
      className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6 lg:gap-2.5"
      data-tour="summary-kpis"
      role="group"
      aria-label="Plant KPIs"
    >
      {items.map((item, i) => (
        <KpiCard
          key={item.label}
          label={item.label}
          value={item.value}
          unit={item.unit}
          tone={item.tone}
          icon={item.icon ?? "pr"}
          index={i}
          missingHint={item.missingHint}
          missingHref={item.missingHref}
        />
      ))}
    </div>
  );

  if (flush) {
    return (
      <div className="border-t border-[color:var(--pic-border-subtle)] bg-[color:var(--pic-surface-inset)] px-3 py-2.5 sm:px-4">
        {board}
      </div>
    );
  }

  return board;
}
