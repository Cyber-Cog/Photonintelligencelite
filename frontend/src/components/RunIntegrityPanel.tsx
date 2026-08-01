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

function isRulesPlusAi(source: string | null | undefined): boolean {
  return Boolean(source && (source === "rules+ai" || source.startsWith("rules+")));
}

/** Honest one-line AI layer status for Results / Upload (not a chatbot). */
export function aiLayerStatusLabel(check: AiIntegrityCheck): string {
  const layer = check.ai_layer;
  const err = (check.error || "").toLowerCase();
  const provider =
    check.provider === "gemini"
      ? "Gemini"
      : check.provider === "zenmux"
        ? "ZenMux"
        : check.source?.includes("gemini")
          ? "Gemini"
          : check.source?.includes("zenmux")
            ? "ZenMux"
            : "AI";
  if (layer === "ok") return `${provider}: ok`;
  if (layer === "not_configured" || (!check.configured && (layer == null || layer === "skipped"))) {
    return "AI not configured";
  }
  if (layer === "failed" || check.status === "error" || check.error) {
    if (err.includes("gemini")) return "Gemini check failed";
    if (err.includes("sk-mg") || err.includes("management") || err.includes("sk-ai")) {
      return "AI key rejected — use GEMINI_API_KEY or sk-ai-v1";
    }
    if (err.includes("403") || err.includes("401")) {
      return "AI key rejected";
    }
    return "AI check failed";
  }
  if (layer === "skipped") return "AI skipped (rules only)";
  if (check.source === "rules+ai" || check.source?.startsWith("rules+")) return `${provider}: ok`;
  if (check.source === "rules" && !check.configured) return "AI not configured";
  if (check.source === "rules") return "AI skipped (rules only)";
  return "AI status unknown";
}

/** Compact non-chat integrity checklist for Results or Upload review. */
export function RunIntegrityPanel({
  jobId,
  check,
  canRerun = false,
  onUpdated,
  eyebrow = "Run integrity",
  emptyPassMessage = "No display/run contradictions detected.",
  quiet = false,
}: {
  jobId: string;
  check: AiIntegrityCheck | null | undefined;
  canRerun?: boolean;
  onUpdated?: (next: AiIntegrityCheck) => void;
  eyebrow?: string;
  emptyPassMessage?: string;
  /** Flat divider layout for Summary (less card chrome). */
  quiet?: boolean;
}) {
  const [busy, setBusy] = useState(false);
  const [localError, setLocalError] = useState<string | null>(null);

  // Always show when a check object exists — including AI-not-configured / skipped.
  if (!check) return null;

  const tone = quiet ? "" : (PANEL_TONE[check.status] ?? PANEL_TONE.skipped);
  const findings = (check.findings || []).filter((f) => f.severity !== "pass");
  const aiLabel = aiLayerStatusLabel(check);
  const rulesCount =
    check.rules_finding_count != null
      ? check.rules_finding_count
      : findings.length;

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
      className={
        quiet
          ? "border-b border-[color:var(--pic-border-subtle)] pb-3"
          : `rounded-pic-lg border px-3.5 py-3 ${tone}`
      }
    >
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          {!quiet ? <p className="tool-eyebrow mb-0.5">{eyebrow}</p> : null}
          <h3 className="font-display text-sm font-semibold tracking-tight text-[color:var(--pic-text)]">
            {quiet ? "Integrity" : check.summary || "Fault-run integrity check"}
          </h3>
      <p className="mt-0.5 text-[11px] text-[color:var(--pic-text-muted)]" data-testid="ai-layer-status">
            {quiet && check.summary ? `${check.summary} · ` : ""}
            {isRulesPlusAi(check.source)
              ? "Rules + AI"
              : check.source === "rules"
                ? "Rules"
                : check.source === "ai"
                  ? "AI"
                  : "System"}
            {` · ${rulesCount} finding(s)`}
            {` · ${aiLabel}`}
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
              {busy ? "Checking…" : "Re-run"}
            </button>
          ) : null}
        </div>
      </div>

      {check.error ? (
        <p className="mt-1.5 text-xs text-rose-800 dark:text-rose-200" role="alert">
          {check.error}
        </p>
      ) : null}
      {localError ? (
        <p className="mt-2 text-xs text-rose-800 dark:text-rose-200" role="alert">
          {localError}
        </p>
      ) : null}

      {findings.length > 0 ? (
        <ul className="mt-2 space-y-1" role="list">
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
      ) : check.status === "pass" || check.status === "skipped" ? (
        <p className="mt-1.5 text-[12px] text-[color:var(--pic-text-muted)]">
          {emptyPassMessage}
        </p>
      ) : null}
      {check.mapping_hints && check.mapping_hints.length > 0 ? (
        <ul className="mt-2 space-y-1 text-[11px] text-[color:var(--pic-text-muted)]" role="list">
          {check.mapping_hints.slice(0, 6).map((h, i) => (
            <li key={`${h.column_name}-${i}`}>
              Suggest: <span className="text-[color:var(--pic-text)]">{h.column_name}</span>
              {" → "}
              <span className="font-medium text-[color:var(--pic-text)]">{h.canonical_field}</span>
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}
