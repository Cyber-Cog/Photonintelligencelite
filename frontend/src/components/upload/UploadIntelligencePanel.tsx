import { Badge } from "@/components/ui/Badge";
import type {
  UploadArchitectureSummary,
  UploadHierarchyLevel,
  UploadModuleImpactPreview,
} from "@/types";

function HierarchyMatrix({ levels, compact }: { levels: UploadHierarchyLevel[]; compact?: boolean }) {
  if (levels.length === 0) return null;

  return (
    <div className={compact ? "space-y-2" : "space-y-3"}>
      {levels.map((level) => (
        <div key={level.level_id}>
          <div className="mb-1.5 flex items-center justify-between gap-2">
            <p className={`font-medium text-[color:var(--pic-text)] ${compact ? "text-xs" : "text-sm"}`}>{level.title}</p>
            <span className="text-[10px] tabular-nums text-[color:var(--pic-text-muted)]">
              {level.detected_count}/{level.total_count}
            </span>
          </div>
          <ul className="space-y-1">
            {level.signals.map((sig) => (
              <li key={sig.id} className={`flex items-start gap-2 ${compact ? "text-xs" : "text-sm"}`}>
                <span
                  className={`mt-0.5 flex h-3.5 w-3.5 shrink-0 items-center justify-center rounded-sm text-[9px] font-bold ${
                    sig.present
                      ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300"
                      : "bg-stone-100 text-stone-400 dark:bg-stone-800 dark:text-stone-500"
                  }`}
                  aria-hidden
                >
                  {sig.present ? "✓" : "·"}
                </span>
                <span className="min-w-0 flex-1">
                  <span className={sig.present ? "text-[color:var(--pic-text)]" : "text-[color:var(--pic-text-muted)]"}>
                    {sig.label}
                  </span>
                  {sig.present && sig.detected_via && sig.detected_via !== sig.id ? (
                    <span className="mt-0.5 block text-[10px] text-[color:var(--pic-text-muted)]">
                      via {sig.detected_via.replace(/_/g, " ")}
                    </span>
                  ) : null}
                  {!sig.present ? (
                    <span className="mt-0.5 block text-[10px] text-amber-700 dark:text-amber-400">Not detected in this file</span>
                  ) : null}
                </span>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </div>
  );
}

function ArchitectureCard({ arch }: { arch: UploadArchitectureSummary }) {
  const sourceLabel =
    arch.source === "pack_import"
      ? "From Complete Analysis Pack"
      : arch.source === "saved_config"
        ? "From saved plant config"
        : arch.source === "device_id" || arch.source === "hierarchy_columns"
          ? "Inferred from equipment IDs"
          : arch.detected
            ? "Detected"
            : "Not yet detected";

  return (
    <div className="rounded-xl border border-[color:var(--pic-border)] bg-[color:var(--pic-surface-raised)] p-4">
      <div className="flex items-center justify-between gap-2">
        <p className="font-display text-sm font-semibold text-[color:var(--pic-text)]">Plant architecture</p>
        <Badge tone={arch.detected ? "success" : "warning"}>{arch.detected ? "Detected" : "Missing"}</Badge>
      </div>
      {arch.detected ? (
        <dl className="mt-3 grid grid-cols-3 gap-2 text-center">
          {[
            { label: "Inverters", value: arch.inverter_count },
            { label: "SCBs", value: arch.scb_count },
            { label: "Strings", value: arch.string_count },
          ].map((item) => (
            <div key={item.label} className="rounded-lg border border-[color:var(--pic-border-subtle)] bg-[color:var(--pic-surface-muted)] px-2 py-2">
              <dt className="text-[10px] font-semibold uppercase tracking-wide text-[color:var(--pic-text-muted)]">{item.label}</dt>
              <dd className="mt-0.5 text-lg font-semibold tabular-nums text-[color:var(--pic-text)]">{item.value}</dd>
            </div>
          ))}
        </dl>
      ) : (
        <p className="mt-3 text-sm text-[color:var(--pic-text-muted)]">
          No inverter → SCB → string tree yet. Map equipment ID columns in Setup, upload the architecture Excel, or use pattern apply.
        </p>
      )}
      <p className="mt-2 text-[10px] text-[color:var(--pic-text-muted)]">{sourceLabel}</p>
      {arch.notes.length > 0 ? (
        <ul className="mt-2 space-y-1 text-xs text-[color:var(--pic-text-secondary)]">
          {arch.notes.slice(0, 2).map((note) => (
            <li key={note}>{note}</li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

function ModuleImpactCard({ impact }: { impact: UploadModuleImpactPreview }) {
  return (
    <div className="rounded-xl border border-[color:var(--pic-border)] bg-[color:var(--pic-surface-raised)] p-4">
      <div className="flex items-center justify-between gap-2">
        <p className="font-display text-sm font-semibold text-[color:var(--pic-text)]">Analysis impact preview</p>
        <span className="text-xs tabular-nums text-[color:var(--pic-text-muted)]">
          {impact.ready_count} ready · {impact.blocked_count} blocked
        </span>
      </div>
      <p className="mt-2 text-xs text-[color:var(--pic-text-muted)]">{impact.preview_note}</p>
      {impact.blocked_modules.length > 0 ? (
        <ul className="mt-3 max-h-64 space-y-2 overflow-y-auto">
          {impact.blocked_modules.map((m) => (
            <li
              key={m.algorithm_id}
              className="rounded-lg border border-amber-200/80 bg-amber-50/60 px-3 py-2 dark:border-amber-900/40 dark:bg-amber-950/20"
            >
              <p className="text-sm font-medium text-amber-950 dark:text-amber-100">{m.title}</p>
              <p className="mt-0.5 text-xs text-amber-900/90 dark:text-amber-200/90">{m.message}</p>
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-3 text-sm text-emerald-800 dark:text-emerald-300">All fault modules have the columns they need at this stage.</p>
      )}
    </div>
  );
}

type Props = {
  hierarchy: UploadHierarchyLevel[];
  architecture?: UploadArchitectureSummary | null;
  moduleImpact?: UploadModuleImpactPreview | null;
  showPlaceholder?: boolean;
};

export function UploadIntelligencePanel({ hierarchy, architecture, moduleImpact, showPlaceholder }: Props) {
  if (showPlaceholder) {
    return (
      <div className="flex flex-col gap-4">
        <div className="rounded-xl border border-[color:var(--pic-border)] bg-[color:var(--pic-surface-raised)] p-4">
          <p className="font-display text-sm font-semibold text-[color:var(--pic-text)]">What you will see after upload</p>
          <ul className="mt-3 space-y-2 text-sm text-[color:var(--pic-text-muted)]">
            <li>Signals detected at each hierarchy — plant/WMS, inverter, SCB/string</li>
            <li>Inverter, SCB, and string counts from your data or pack</li>
            <li>Which fault analyses may not run until Setup is complete</li>
          </ul>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      {architecture ? <ArchitectureCard arch={architecture} /> : null}

      <div className="rounded-xl border border-[color:var(--pic-border)] bg-[color:var(--pic-surface-raised)] p-4">
        <p className="font-display text-sm font-semibold text-[color:var(--pic-text)]">Signals by hierarchy (job total)</p>
        <p className="mt-1 text-xs text-[color:var(--pic-text-muted)]">
          Shows what was detected across all uploaded files — expand each file in the table for per-file detail.
        </p>
        <div className="mt-3">
          <HierarchyMatrix levels={hierarchy} />
        </div>
      </div>

      {moduleImpact ? <ModuleImpactCard impact={moduleImpact} /> : null}
    </div>
  );
}

export { HierarchyMatrix };
