import { Badge } from "@/components/ui/Badge";
import type {
  UploadArchitectureSummary,
  UploadHierarchyLevel,
  UploadModuleImpactPreview,
} from "@/types";

function SignalChips({ levels, dense }: { levels: UploadHierarchyLevel[]; dense?: boolean }) {
  if (levels.length === 0) return null;

  return (
    <div className={dense ? "space-y-2.5" : "space-y-3"}>
      {levels.map((level) => (
        <div key={level.level_id}>
          <div className="mb-1.5 flex items-center justify-between gap-2">
            <p className={`font-medium text-[color:var(--pic-text)] ${dense ? "text-xs" : "text-sm"}`}>{level.title}</p>
            <span className="text-[10px] tabular-nums text-[color:var(--pic-text-muted)]">
              {level.detected_count}/{level.total_count}
            </span>
          </div>
          <div className="flex flex-wrap gap-1.5">
            {level.signals.map((sig) => (
              <span
                key={sig.id}
                title={
                  sig.present
                    ? sig.detected_via && sig.detected_via !== sig.id
                      ? `Detected via ${sig.detected_via.replace(/_/g, " ")}`
                      : "Detected"
                    : "Not detected"
                }
                className={`inline-flex max-w-full items-center gap-1 rounded-md border px-2 py-0.5 text-[11px] leading-snug ${
                  sig.present
                    ? "border-emerald-200/90 bg-emerald-50/80 text-emerald-900 dark:border-emerald-800/50 dark:bg-emerald-950/30 dark:text-emerald-200"
                    : "border-[color:var(--pic-border-subtle)] bg-[color:var(--pic-surface-muted)] text-[color:var(--pic-text-muted)]"
                }`}
              >
                <span aria-hidden className="shrink-0 text-[9px] font-bold">
                  {sig.present ? "✓" : "○"}
                </span>
                <span className="truncate">{sig.label}</span>
              </span>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

function ArchitectureCard({ arch, compact }: { arch: UploadArchitectureSummary; compact?: boolean }) {
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
    <div className={`rounded-xl border border-[color:var(--pic-border)] bg-[color:var(--pic-surface-raised)] ${compact ? "p-3.5" : "p-4"}`}>
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
            <div
              key={item.label}
              className="rounded-lg border border-[color:var(--pic-border-subtle)] bg-[color:var(--pic-surface-muted)] px-2 py-2"
            >
              <dt className="text-[10px] font-semibold uppercase tracking-wide text-[color:var(--pic-text-muted)]">{item.label}</dt>
              <dd className="mt-0.5 text-lg font-semibold tabular-nums text-[color:var(--pic-text)]">{item.value}</dd>
            </div>
          ))}
        </dl>
      ) : (
        <p className="mt-3 text-sm leading-relaxed text-[color:var(--pic-text-muted)]">
          Map equipment IDs in Setup, upload the architecture Excel, or use pattern apply.
        </p>
      )}
      <p className="mt-2 text-[10px] text-[color:var(--pic-text-muted)]">{sourceLabel}</p>
    </div>
  );
}

function ModuleImpactCard({ impact }: { impact: UploadModuleImpactPreview }) {
  const showAll = impact.blocked_modules.length <= 4;

  return (
    <div className="rounded-xl border border-[color:var(--pic-border)] bg-[color:var(--pic-surface-raised)] p-3.5 lg:p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="font-display text-sm font-semibold text-[color:var(--pic-text)]">Analysis impact</p>
        <span className="text-xs tabular-nums text-[color:var(--pic-text-muted)]">
          {impact.ready_count} ready · {impact.blocked_count} blocked
        </span>
      </div>
      <p className="mt-1.5 text-xs text-[color:var(--pic-text-muted)]">{impact.preview_note}</p>
      {impact.blocked_modules.length > 0 ? (
        showAll ? (
          <ul className="mt-3 grid gap-2 sm:grid-cols-2">
            {impact.blocked_modules.map((m) => (
              <li
                key={m.algorithm_id}
                className="rounded-lg border border-amber-200/80 bg-amber-50/60 px-3 py-2 dark:border-amber-900/40 dark:bg-amber-950/20"
              >
                <p className="text-sm font-medium text-amber-950 dark:text-amber-100">{m.title}</p>
                <p className="mt-0.5 line-clamp-2 text-xs text-amber-900/90 dark:text-amber-200/90">{m.message}</p>
              </li>
            ))}
          </ul>
        ) : (
          <details className="group mt-3">
            <summary className="cursor-pointer list-none text-sm font-medium text-amber-800 dark:text-amber-200">
              <span className="group-open:hidden">{impact.blocked_count} modules may not run — show details</span>
              <span className="hidden group-open:inline">Hide module details</span>
            </summary>
            <ul className="mt-3 grid gap-2 sm:grid-cols-2">
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
          </details>
        )
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
  layout?: "sidebar" | "review";
};

export function UploadIntelligencePanel({
  hierarchy,
  architecture,
  moduleImpact,
  showPlaceholder,
  layout = "sidebar",
}: Props) {
  if (showPlaceholder) {
    return (
      <div className="rounded-xl border border-[color:var(--pic-border)] bg-[color:var(--pic-surface-raised)] p-4">
        <p className="font-display text-sm font-semibold text-[color:var(--pic-text)]">After upload you will see</p>
        <ul className="mt-3 space-y-2 text-sm text-[color:var(--pic-text-muted)]">
          <li>Signals at plant, inverter, and SCB/string levels</li>
          <li>Inverter, SCB, and string counts</li>
          <li>Which analyses may not run until Setup is complete</li>
        </ul>
      </div>
    );
  }

  if (layout === "review") {
    return (
      <div className="space-y-4">
        <div className="grid gap-4 lg:grid-cols-3">
          {architecture ? <ArchitectureCard arch={architecture} compact /> : null}
          <div className="rounded-xl border border-[color:var(--pic-border)] bg-[color:var(--pic-surface-raised)] p-3.5 lg:col-span-2 lg:p-4">
            <p className="font-display text-sm font-semibold text-[color:var(--pic-text)]">Signals by hierarchy (job total)</p>
            <p className="mt-1 text-xs text-[color:var(--pic-text-muted)]">Expand a file row above for per-file detail.</p>
            <div className="mt-3">
              <SignalChips levels={hierarchy} />
            </div>
          </div>
        </div>
        {moduleImpact ? <ModuleImpactCard impact={moduleImpact} /> : null}
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      {architecture ? <ArchitectureCard arch={architecture} /> : null}
      <div className="rounded-xl border border-[color:var(--pic-border)] bg-[color:var(--pic-surface-raised)] p-4">
        <p className="font-display text-sm font-semibold text-[color:var(--pic-text)]">Signals by hierarchy</p>
        <div className="mt-3">
          <SignalChips levels={hierarchy} />
        </div>
      </div>
      {moduleImpact ? <ModuleImpactCard impact={moduleImpact} /> : null}
    </div>
  );
}

export { SignalChips };
