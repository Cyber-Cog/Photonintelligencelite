import { useState } from "react";
import { ApiError, rerunAiIntegrity } from "@/api/client";
import type { AiIntegrityCheck } from "@/types";

const SEV_STYLES: Record<string, string> = {
  pass: "bg-accent-100 text-accent-900 dark:bg-accent-950/50 dark:text-accent-200",
  warn: "bg-amber-100 text-amber-950 dark:bg-amber-950/40 dark:text-amber-100",
  fail: "bg-rose-100 text-rose-950 dark:bg-rose-950/40 dark:text-rose-100",
};

const PANEL_TONE: Record<string, string> = {
  pass: "border-accent-200/80 bg-accent-50/40 dark:border-accent-800/40 dark:bg-stone-900",
  warn: "border-amber-200/90 bg-amber-50/50 dark:border-amber-800/40 dark:bg-stone-900",
  fail: "border-rose-200/90 bg-rose-50/50 dark:border-rose-800/40 dark:bg-stone-900",
  error: "border-rose-200/90 bg-rose-50/50 dark:border-rose-800/40 dark:bg-stone-900",
  skipped: "border-stone-200 bg-stone-50/80 dark:border-stone-700 dark:bg-stone-900",
};

/** Compact non-chat integrity checklist for Results. */
export function RunIntegrityPanel({
  jobId,
  check,
  canRerun = false,
  onUpdated,
}: {
  jobId: string;
  check: AiIntegrityCheck | null | undefined;
  canRerun?: boolean;
  onUpdated?: (next: AiIntegrityCheck) => void;
}) {
  const [busy, setBusy] = useState(false);
  const [localError, setLocalError] = useState<string | null>(null);

  if (!check) return null;
  if (check.status === "skipped" && !(check.findings?.length > 0)) return null;

  const tone = PANEL_TONE[check.status] ?? PANEL_TONE.skipped;
  const findings = (check.findings || []).filter((f) => f.severity !== "pass");

  async function onRerun() {
    setBusy(true);
    setLocalError(null);
    try {
      const next = await rerunAiIntegrity(jobId);
      onUpdated?.(next);
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : "Could not re-run integrity check.";
      setLocalError(msg);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section
      data-tour="run-integrity"
      aria-label="Run integrity"
      className={`rounded-pic-lg border px-3.5 py-3 ${tone}`}
    >
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <p className="tool-eyebrow mb-0.5">Run integrity</p>
          <h3 className="font-display text-sm font-semibold tracking-tight text-[color:var(--pic-text)]">
            {check.summary || "Fault-run integrity check"}
          </h3>
          <p className="mt-0.5 text-[11px] text-[color:var(--pic-text-muted)]">
            {check.source === "rules+ai"
              ? "Rules + AI"
              : check.source === "rules"
                ? "Rules"
                : check.source === "ai"
                  ? "AI"
                  : "System"}
            {check.model ? ` · ${check.model}` : ""}
            {check.checked_at
              ? ` · ${new Date(check.checked_at).toLocaleString(undefined, {
                  dateStyle: "short",
                  timeStyle: "short",
                })}`
              : ""}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span
            className={`rounded-md px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide ${
              SEV_STYLES[check.status === "error" ? "fail" : check.status] ?? SEV_STYLES.warn
            }`}
          >
            {check.status}
          </span>
          {canRerun ? (
            <button
              type="button"
              className="btn-ghost !px-2 !py-0.5 text-[11px]"
              disabled={busy}
              onClick={() => void onRerun()}
            >
              {busy ? "Checking…" : "Re-run check"}
            </button>
          ) : null}
        </div>
      </div>

      {check.error ? (
        <p className="mt-2 text-xs text-rose-800 dark:text-rose-200" role="alert">
          {check.error}
        </p>
      ) : null}
      {localError ? (
        <p className="mt-2 text-xs text-rose-800 dark:text-rose-200" role="alert">
          {localError}
        </p>
      ) : null}

      {findings.length > 0 ? (
        <ul className="mt-2.5 space-y-1.5" role="list">
          {findings.map((f, i) => (
            <li
              key={`${f.code}-${f.module_id ?? ""}-${i}`}
              className="flex gap-2 text-[12px] leading-snug text-[color:var(--pic-text-secondary)]"
            >
              <span
                className={`mt-0.5 shrink-0 rounded px-1 py-px text-[9px] font-bold uppercase tracking-wide ${
                  SEV_STYLES[f.severity] ?? SEV_STYLES.warn
                }`}
              >
                {f.severity}
              </span>
              <span>
                {f.module_id ? (
                  <span className="font-semibold text-[color:var(--pic-text)]">{f.module_id}: </span>
                ) : null}
                {f.message}
              </span>
            </li>
          ))}
        </ul>
      ) : check.status === "pass" ? (
        <p className="mt-2 text-[12px] text-[color:var(--pic-text-muted)]">
          No display/run contradictions detected.
        </p>
      ) : null}
    </section>
  );
}
