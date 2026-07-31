import { ProgressBar } from "@/components/ui/ProgressBar";
import type { UploadSignalCheckItem } from "@/types";

type Props = {
  checklist: UploadSignalCheckItem[];
  looksLikePack: boolean;
  showPlaceholder?: boolean;
};

export function UploadSignalSidebar({ checklist, looksLikePack, showPlaceholder }: Props) {
  const presentCount = checklist.filter((c) => c.present).length;
  const total = checklist.length || 1;
  const pct = Math.round((presentCount / total) * 100);
  const missingSetup = checklist.filter((c) => !c.present && c.setup_only);

  return (
    <div className="flex flex-col gap-4">
      <div className="rounded-xl border border-[color:var(--pic-border)] bg-[color:var(--pic-surface-raised)] p-4">
        <div className="flex items-center justify-between gap-2">
          <p className="font-display text-sm font-semibold text-[color:var(--pic-text)]">Required signals</p>
          {checklist.length > 0 ? (
            <span className="text-xs tabular-nums text-[color:var(--pic-text-muted)]">
              {presentCount} / {total}
            </span>
          ) : null}
        </div>

        {showPlaceholder || checklist.length === 0 ? (
          <p className="mt-3 text-sm leading-relaxed text-[color:var(--pic-text-muted)]">
            Upload files to see which signals were detected in each sheet.
          </p>
        ) : (
          <ul className="mt-3 space-y-2">
            {checklist.map((item) => (
              <li key={item.id} className="flex items-start gap-2.5 text-sm">
                <span
                  className={`mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-sm text-[10px] font-bold ${
                    item.present
                      ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300"
                      : item.setup_only
                        ? "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300"
                        : "bg-stone-100 text-stone-400 dark:bg-stone-800 dark:text-stone-500"
                  }`}
                  aria-hidden
                >
                  {item.present ? "✓" : item.setup_only ? "!" : "·"}
                </span>
                <span className="min-w-0 flex-1">
                  <span className={item.present ? "text-[color:var(--pic-text)]" : "text-[color:var(--pic-text-secondary)]"}>
                    {item.label}
                  </span>
                  {!item.present && item.hint ? (
                    <span className="mt-0.5 block text-xs text-amber-700 dark:text-amber-400">{item.hint}</span>
                  ) : null}
                </span>
              </li>
            ))}
          </ul>
        )}

        {checklist.length > 0 ? (
          <div className="mt-4">
            <ProgressBar pct={pct} />
            <p className="mt-1 text-right text-[10px] tabular-nums text-[color:var(--pic-text-muted)]">{pct}%</p>
          </div>
        ) : null}

        {missingSetup.length > 0 ? (
          <p className="mt-3 text-xs text-amber-800 dark:text-amber-300">
            {missingSetup.length} item{missingSetup.length === 1 ? "" : "s"} to confirm in Setup.
          </p>
        ) : null}
      </div>

      <div className="rounded-xl border border-[color:var(--pic-border)] bg-[color:var(--pic-surface-muted)] p-4">
        <p className="font-display text-[10px] font-semibold uppercase tracking-[0.14em] text-[color:var(--pic-text-muted)]">
          Accepted shapes
        </p>
        <div className="mt-3 flex flex-wrap gap-2">
          {[
            { id: "pack", label: "Complete Pack", active: looksLikePack },
            { id: "smb", label: "SMB / SCB split", active: !looksLikePack },
            { id: "multi", label: "Multi-file", active: true },
          ].map((shape) => (
            <span
              key={shape.id}
              className={`rounded-lg border px-2.5 py-1 text-xs font-medium ${
                shape.active
                  ? "border-brand-300/80 bg-brand-50 text-brand-900 dark:border-brand-600/50 dark:bg-brand-950/40 dark:text-brand-200"
                  : "border-[color:var(--pic-border-subtle)] text-[color:var(--pic-text-muted)]"
              }`}
            >
              {shape.label}
            </span>
          ))}
        </div>
      </div>

      <div className="rounded-xl border border-[color:var(--pic-border)] bg-[color:var(--pic-surface-muted)] p-4">
        <p className="font-display text-[10px] font-semibold uppercase tracking-[0.14em] text-[color:var(--pic-text-muted)]">
          What happens next
        </p>
        <ol className="mt-3 space-y-3 text-sm text-[color:var(--pic-text-secondary)]">
          <li className="flex gap-2">
            <span className="font-semibold text-brand-700 dark:text-brand-300">1.</span>
            <span>
              <span className="font-medium text-[color:var(--pic-text)]">Setup</span> — confirm column mapping and plant details
            </span>
          </li>
          <li className="flex gap-2">
            <span className="font-semibold text-brand-700 dark:text-brand-300">2.</span>
            <span>
              <span className="font-medium text-[color:var(--pic-text)]">Validate</span> — check timestamps and gaps
            </span>
          </li>
          <li className="flex gap-2">
            <span className="font-semibold text-brand-700 dark:text-brand-300">3.</span>
            <span>
              <span className="font-medium text-[color:var(--pic-text)]">Analyze</span> — run fault detection
            </span>
          </li>
        </ol>
      </div>
    </div>
  );
}
