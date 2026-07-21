import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  acknowledgeWarnings,
  ApiError,
  getValidation,
  retryValidation,
} from "@/api/client";
import { StepIndicator } from "@/components/StepIndicator";
import { Badge } from "@/components/ui/Badge";
import { ErrorState } from "@/components/ui/ErrorState";
import { InfoBanner } from "@/components/ui/InfoBanner";
import { PageHeader } from "@/components/ui/PageHeader";
import { SectionPanel } from "@/components/ui/SectionPanel";
import { Spinner } from "@/components/ui/Spinner";
import { ALGORITHM_FIELD_HINTS } from "@/lib/canonicalHints";
import { fixHref } from "@/lib/missingReasons";
import type { ValidationIssue, ValidationResponse } from "@/types";

function issueFixHref(jobId: string, issue: ValidationIssue): string {
  const col = issue.affected_columns[0];
  if (col) {
    return `/jobs/${jobId}/setup#mapping&field=${encodeURIComponent(col)}`;
  }
  if (/timestamp/i.test(issue.code) || /timestamp/i.test(issue.message)) {
    return `/jobs/${jobId}/setup#mapping&field=timestamp`;
  }
  return `/jobs/${jobId}/setup#mapping`;
}

function readinessFixHref(
  jobId: string,
  algorithmId: string,
  missingFields: string[],
  missingConfig: string[],
): string {
  if (missingConfig.some((c) => /architecture/i.test(c))) {
    return fixHref(jobId, { kind: "setup", hash: "architecture", field: "architecture" });
  }
  if (missingConfig.some((c) => /rating/i.test(c))) {
    return fixHref(jobId, { kind: "setup", hash: "plant", field: "inverter_capacity_kw" });
  }
  const first = missingFields[0]?.split(" or ")[0];
  const hint = first || ALGORITHM_FIELD_HINTS[algorithmId];
  if (hint) {
    return fixHref(jobId, { kind: "setup", hash: "mapping", field: hint });
  }
  return fixHref(jobId, { kind: "setup", hash: "mapping" });
}

function IssueRow({ issue, jobId }: { issue: ValidationIssue; jobId: string }) {
  const href = issueFixHref(jobId, issue);
  return (
    <li className="flex flex-col gap-1 border-b border-stone-100 py-3 last:border-0 dark:border-stone-800">
      <div className="flex items-center gap-2">
        <Badge tone={issue.severity === "blocker" ? "danger" : "warning"}>{issue.severity}</Badge>
        <span className="font-mono text-xs text-stone-400">{issue.code}</span>
      </div>
      <p className="text-sm text-stone-700 dark:text-stone-200">{issue.message}</p>
      <p className="text-xs text-stone-500">Likely cause: {issue.likely_cause}</p>
      {issue.remediation && (
        <p className="text-xs text-brand-700 dark:text-brand-300">Next: {issue.remediation}</p>
      )}
      {issue.affected_columns.length > 0 && (
        <p className="text-xs text-stone-400">Columns: {issue.affected_columns.join(", ")}</p>
      )}
      {(issue.sample_values?.length ?? 0) > 0 && (
        <p className="text-xs text-stone-400">
          Sample values: {issue.sample_values!.map((v) => `"${v}"`).join(", ")}
        </p>
      )}
      {issue.affected_rows > 0 && (
        <p className="text-xs text-stone-400">{issue.affected_rows.toLocaleString()} rows affected</p>
      )}
      <Link to={href} className="mt-1 w-fit text-xs font-semibold text-amber-800 underline dark:text-amber-200">
        Open field in Setup
      </Link>
    </li>
  );
}

export function ValidationPage() {
  const { jobId } = useParams<{ jobId: string }>();
  const navigate = useNavigate();

  const [validation, setValidation] = useState<ValidationResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [acking, setAcking] = useState(false);
  const [retrying, setRetrying] = useState(false);

  const reload = () => {
    if (!jobId) return;
    setLoading(true);
    getValidation(jobId)
      .then(setValidation)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Could not load validation results."))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobId]);

  if (!jobId) return null;

  const hasBlockers = (validation?.blockers.length ?? 0) > 0;
  const canDrop = Boolean(validation?.can_proceed_with_row_drops);
  const tsCol = validation?.timestamp_column;

  const handleContinue = async (dropBad = false) => {
    setAcking(true);
    setError(null);
    try {
      await acknowledgeWarnings(jobId, dropBad);
      navigate(`/jobs/${jobId}/processing`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not queue the job. Try again.");
      reload();
    } finally {
      setAcking(false);
    }
  };

  const handleRetry = async () => {
    setRetrying(true);
    setError(null);
    try {
      await retryValidation(jobId, false);
      reload();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not retry validation.");
    } finally {
      setRetrying(false);
    }
  };

  return (
    <div className="tool-enter mx-auto w-full max-w-3xl pb-8">
      <StepIndicator current={3} jobId={jobId} />
      <PageHeader
        className="mb-5"
        eyebrow="Gate before analysis"
        title="Data validation"
        description="Checked your upload for issues that could affect analysis accuracy. The upload is retained so you can fix mapping and retry without starting over."
      />

      {loading && (
        <div className="flex items-center gap-2 text-sm text-stone-500">
          <Spinner className="h-4 w-4" /> Checking your data…
        </div>
      )}

      {!loading && error && !validation && (
        <ErrorState title="Could not load validation" message={error} />
      )}

      {!loading && validation && (
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-4">
            <div className="stat-tile">
              <p className="label mb-0">Rows</p>
              <p className="mt-1 font-display text-lg font-semibold tabular-nums text-stone-900 dark:text-stone-50">
                {validation.row_count.toLocaleString()}
              </p>
            </div>
            <div className="stat-tile">
              <p className="label mb-0">Columns</p>
              <p className="mt-1 font-display text-lg font-semibold tabular-nums text-stone-900 dark:text-stone-50">
                {validation.column_count}
              </p>
            </div>
            <div className="stat-tile">
              <p className="label mb-0">Sample interval</p>
              <p className="mt-1 font-display text-lg font-semibold tabular-nums text-stone-900 dark:text-stone-50">
                {validation.detected_interval_minutes ? `${validation.detected_interval_minutes} min` : "—"}
              </p>
            </div>
            <div className="stat-tile">
              <p className="label mb-0">Timestamp column</p>
              <p
                className="mt-1 truncate font-display text-lg font-semibold text-stone-900 dark:text-stone-50"
                title={tsCol ?? undefined}
              >
                {tsCol || "—"}
              </p>
            </div>
          </div>

          {hasBlockers && (
            <SectionPanel
              title={`${validation.blockers.length} blocking issue${validation.blockers.length === 1 ? "" : "s"}`}
              description="Analysis paused. Upload retained."
              accent="rose"
              scrollMargin={false}
            >
              <ul>
                {validation.blockers.map((b, i) => (
                  <IssueRow key={i} issue={b} jobId={jobId} />
                ))}
              </ul>

              <div className="mt-4 rounded-xl border border-stone-200/90 bg-stone-50/80 p-3.5 dark:border-stone-700 dark:bg-stone-950/40">
                <p className="tool-eyebrow mb-2.5">Fix mapping and retry</p>
                <div className="flex flex-wrap gap-2">
                  <button
                    type="button"
                    className="btn-primary"
                    onClick={() => navigate(`/jobs/${jobId}/setup#mapping&field=timestamp`)}
                  >
                    Fix column mapping
                  </button>
                  <button type="button" className="btn-secondary" onClick={handleRetry} disabled={retrying}>
                    {retrying ? <Spinner className="h-4 w-4" /> : null}
                    Retry validation
                  </button>
                  {canDrop && (
                    <button
                      type="button"
                      className="btn-secondary"
                      onClick={() => handleContinue(true)}
                      disabled={acking}
                      title="Drops rows whose timestamps could not be parsed"
                    >
                      {acking ? <Spinner className="h-4 w-4" /> : null}
                      Proceed with warnings (keep {(validation.rows_that_would_be_kept ?? 0).toLocaleString()}, drop{" "}
                      {(validation.rows_that_would_be_dropped ?? 0).toLocaleString()})
                    </button>
                  )}
                </div>
                {!canDrop && (validation.timestamp_parse_fail ?? 0) > 0 && (
                  <p className="mt-2.5 text-xs text-stone-500">
                    Proceed-with-warnings is available when ≥
                    {Math.round((validation.proceed_with_drops_min_ok_ratio ?? 0.8) * 100)}% of timestamps parse OK.
                    Right now {(validation.timestamp_parse_ok ?? 0).toLocaleString()} parse OK /{" "}
                    {(validation.timestamp_parse_fail ?? 0).toLocaleString()} fail — remap the Timestamp column
                    (often to &quot;Date And Time&quot;) instead of restarting.
                  </p>
                )}
              </div>
            </SectionPanel>
          )}

          {validation.warnings.length > 0 && (
            <SectionPanel
              title={`${validation.warnings.length} warning${validation.warnings.length === 1 ? "" : "s"}`}
              accent="amber"
              scrollMargin={false}
            >
              <ul>
                {validation.warnings.map((w, i) => (
                  <IssueRow key={i} issue={w} jobId={jobId} />
                ))}
              </ul>
            </SectionPanel>
          )}

          {validation.interval_notes.length > 0 && (
            <p className="text-xs text-stone-400">{validation.interval_notes.join(" ")}</p>
          )}

          {(validation.module_readiness?.length ?? 0) > 0 && (
            <SectionPanel
              title="Fault / loss module readiness"
              description="Modules blocked by missing telemetry or plant architecture are listed with remediation steps. Blocked modules do not appear as empty results on the dashboard."
              accent="brand"
              scrollMargin={false}
            >
              <ul className="space-y-2">
                {validation.module_readiness.map((m) => (
                  <li
                    key={m.algorithm_id}
                    className="rounded-xl border border-stone-200/90 bg-stone-50/50 px-3.5 py-2.5 dark:border-stone-800 dark:bg-stone-950/40"
                  >
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge tone={m.will_run ? "info" : "warning"}>{m.will_run ? "Will run" : "Blocked"}</Badge>
                      <span className="text-sm font-medium text-stone-800 dark:text-stone-100">{m.title}</span>
                    </div>
                    <p className="mt-1 text-xs text-stone-600 dark:text-stone-300">{m.message}</p>
                    {!m.will_run && (
                      <Link
                        to={readinessFixHref(jobId, m.algorithm_id, m.missing_fields, m.missing_config)}
                        className="mt-1.5 inline-block text-xs font-semibold text-amber-800 underline dark:text-amber-200"
                      >
                        {m.how_to_fix || "Open Setup to fix"}
                      </Link>
                    )}
                  </li>
                ))}
              </ul>
            </SectionPanel>
          )}

          {!hasBlockers && validation.warnings.length === 0 && (
            <InfoBanner tone="success" title="Ready to analyze">
              No data-quality blockers. Review module readiness above, then run analysis.
            </InfoBanner>
          )}

          {error && <p className="text-sm text-rose-600 dark:text-rose-400">{error}</p>}

          <div className="flex flex-wrap justify-end gap-3 border-t border-stone-200/80 pt-4 dark:border-stone-800/80">
            <button
              type="button"
              className="btn-secondary"
              onClick={() => navigate(`/jobs/${jobId}/setup`)}
            >
              Edit mapping / plant
            </button>
            <button type="button" className="btn-ghost" onClick={() => navigate(`/upload?replace=${jobId}`)}>
              Replace files / Back to upload
            </button>
            {!hasBlockers && (
              <button type="button" className="btn-primary" onClick={() => handleContinue(false)} disabled={acking}>
                {acking ? <Spinner className="h-4 w-4" /> : null}
                {validation.warnings.length > 0 ? "Acknowledge & run analysis" : "Run analysis"}
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
