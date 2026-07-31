import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  acknowledgeWarnings,
  ApiError,
  downloadAuthenticated,
  getValidation,
  parsedExcelUrl,
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

/** Issue codes where Setup mapping cannot help — inspect data / continue instead. */
const DATA_INSPECT_CODES = new Set([
  "duplicate_timestamps",
  "unsorted_timestamps",
  "missing_timestamps",
  "corrupted_rows",
  "non_numeric_values",
  "negative_values_where_impossible",
]);

type IssueCta =
  | { kind: "setup"; href: string; label: string }
  | { kind: "download_parsed"; label: string }
  | { kind: "none" };

function issueCta(jobId: string, issue: ValidationIssue): IssueCta {
  if (DATA_INSPECT_CODES.has(issue.code)) {
    return { kind: "download_parsed", label: "Download parsed Excel" };
  }

  const col = issue.affected_columns[0];
  const plantCapacityCodes = new Set([
    "inverter_rating_mismatch",
    "imported_inverter_rating_mismatch",
    "imported_equipment_rating_mismatch",
    "imported_equipment_rating_mismatch_bulk",
    "imported_ac_capacity_mismatch",
    "imported_dc_capacity_mismatch",
    "ac_capacity_mismatch",
    "dc_capacity_mismatch",
    "inverter_rating_missing",
    "inverter_rating_uses_plant_default",
  ]);
  const architectureCodes = new Set([
    "architecture_missing",
    "architecture_scb_missing_inverter",
    "imported_equipment_rating_mismatch",
    "imported_equipment_rating_mismatch_bulk",
  ]);

  if (architectureCodes.has(issue.code) || col === "architecture") {
    return {
      kind: "setup",
      href: fixHref(jobId, { kind: "setup", hash: "architecture", field: "architecture" }),
      label: "Open field in Setup",
    };
  }
  if (plantCapacityCodes.has(issue.code) || col === "inverter_capacity_kw" || col === "ac_capacity_mw" || col === "dc_capacity_mwp") {
    const field =
      col === "ac_capacity_mw" || col === "dc_capacity_mwp" || col === "inverter_capacity_kw"
        ? col
        : issue.code.includes("ac_capacity")
          ? "ac_capacity_mw"
          : issue.code.includes("dc_capacity")
            ? "dc_capacity_mwp"
            : "inverter_capacity_kw";
    return {
      kind: "setup",
      href: fixHref(jobId, { kind: "setup", hash: "plant", field }),
      label: "Open field in Setup",
    };
  }
  if (col) {
    return {
      kind: "setup",
      href: `/jobs/${jobId}/setup#mapping&field=${encodeURIComponent(col)}`,
      label: "Open field in Setup",
    };
  }
  if (/timestamp/i.test(issue.code) || /timestamp/i.test(issue.message)) {
    return {
      kind: "setup",
      href: `/jobs/${jobId}/setup#mapping&field=timestamp`,
      label: "Open field in Setup",
    };
  }
  return { kind: "setup", href: `/jobs/${jobId}/setup#mapping`, label: "Open field in Setup" };
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

function IssueRow({
  issue,
  jobId,
  onDownloadParsed,
  downloadingParsed,
}: {
  issue: ValidationIssue;
  jobId: string;
  onDownloadParsed?: () => void;
  downloadingParsed?: boolean;
}) {
  const cta = issueCta(jobId, issue);
  const isDataInspect = DATA_INSPECT_CODES.has(issue.code);
  return (
    <li className="flex flex-col gap-1 border-b border-stone-100 py-3 last:border-0 dark:border-stone-800">
      <div className="flex items-center gap-2">
        <Badge tone={issue.severity === "blocker" ? "danger" : "warning"}>{issue.severity}</Badge>
        {!isDataInspect && <span className="font-mono text-xs text-stone-400">{issue.code}</span>}
      </div>
      <p className="text-sm font-medium text-stone-800 dark:text-stone-100">{issue.message}</p>
      <p className="text-xs text-stone-500">{issue.likely_cause}</p>
      {issue.remediation && (
        <p className="text-xs text-brand-700 dark:text-brand-300">{issue.remediation}</p>
      )}
      {(issue.sample_values?.length ?? 0) > 0 && (
        <ul className="mt-0.5 list-disc space-y-0.5 pl-4 text-xs text-stone-600 dark:text-stone-300">
          {issue.sample_values!.slice(0, 5).map((v) => (
            <li key={v}>
              <span className="font-mono">{v}</span>
            </li>
          ))}
        </ul>
      )}
      {issue.affected_rows > 0 && (
        <p className="text-xs text-stone-400">{issue.affected_rows.toLocaleString()} extra row(s)</p>
      )}
      {cta.kind === "download_parsed" && onDownloadParsed && (
        <div className="mt-1.5 flex flex-wrap items-center gap-3">
          <button
            type="button"
            className="text-xs font-semibold text-amber-800 underline dark:text-amber-200"
            onClick={() => onDownloadParsed()}
            disabled={downloadingParsed}
          >
            {downloadingParsed ? "Downloading…" : cta.label}
          </button>
          {!issue.blocks_analysis && (
            <span className="text-xs text-stone-500">Or continue anyway below</span>
          )}
        </div>
      )}
      {cta.kind === "setup" && (
        <Link to={cta.href} className="mt-1 w-fit text-xs font-semibold text-amber-800 underline dark:text-amber-200">
          {cta.label}
        </Link>
      )}
    </li>
  );
}

/** True once validation has produced a real summary (not empty defaults). */
function validationSummaryReady(v: ValidationResponse | null): boolean {
  if (!v) return false;
  if ((v.blockers?.length ?? 0) > 0) return true;
  if ((v.module_readiness?.length ?? 0) > 0) return true;
  if ((v.row_count ?? 0) > 0 || (v.column_count ?? 0) > 0) return true;
  if ((v.warnings?.length ?? 0) > 0) return true;
  const st = (v.state || "").toLowerCase();
  // Terminal / post-validation states with an empty summary still need a decisive UI
  // (failed with no issues is rare; treat completed/normalizing/failed as settled only
  // when we also have can_proceed or explicit counts — otherwise keep polling).
  if (st === "failed" && (v.blockers?.length ?? 0) === 0 && (v.row_count ?? 0) === 0) {
    return false;
  }
  return false;
}

export function ValidationPage() {
  const { jobId } = useParams<{ jobId: string }>();
  const navigate = useNavigate();

  const [validation, setValidation] = useState<ValidationResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [acking, setAcking] = useState(false);
  const [retrying, setRetrying] = useState(false);
  const [downloadingParsed, setDownloadingParsed] = useState(false);

  const reload = () => {
    if (!jobId) return;
    setLoading(true);
    getValidation(jobId)
      .then(setValidation)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Could not load validation results."))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    if (!jobId) return;
    let cancelled = false;
    let attempts = 0;
    const maxAttempts = 60;

    const tick = async () => {
      try {
        const v = await getValidation(jobId);
        if (cancelled) return;
        setValidation(v);
        setError(null);
        if (validationSummaryReady(v) || attempts >= maxAttempts) {
          setLoading(false);
          return;
        }
        attempts += 1;
        setLoading(true);
        window.setTimeout(() => {
          if (!cancelled) void tick();
        }, 500);
      } catch (err) {
        if (cancelled) return;
        setError(err instanceof ApiError ? err.message : "Could not load validation results.");
        setLoading(false);
      }
    };

    setLoading(true);
    void tick();
    return () => {
      cancelled = true;
    };
  }, [jobId]);

  if (!jobId) return null;

  const summaryReady = validationSummaryReady(validation);
  const hasBlockers = (validation?.blockers.length ?? 0) > 0;
  const canDrop = Boolean(validation?.can_proceed_with_row_drops);
  const tsCol = validation?.timestamp_column;
  const canRunAnalysis = summaryReady && !hasBlockers && Boolean(validation?.can_proceed);

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

  const handleDownloadParsed = async () => {
    if (downloadingParsed) return;
    setDownloadingParsed(true);
    setError(null);
    try {
      await downloadAuthenticated(
        parsedExcelUrl(jobId),
        `pic_lite_parsed_${jobId.slice(0, 8)}.xlsx`,
      );
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not download parsed Excel.");
    } finally {
      setDownloadingParsed(false);
    }
  };

  return (
    <div className="tool-enter flow-shell flow-stack pb-8">
      <StepIndicator current={3} jobId={jobId} />
      <PageHeader
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

      {!loading && validation && !summaryReady && (
        <InfoBanner tone="info" title="Validation still running">
          Waiting for row counts and module readiness. This page refreshes automatically.
        </InfoBanner>
      )}

      {!loading && validation && summaryReady && (
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
                  <IssueRow
                    key={i}
                    issue={b}
                    jobId={jobId}
                    onDownloadParsed={() => void handleDownloadParsed()}
                    downloadingParsed={downloadingParsed}
                  />
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
                  <IssueRow
                    key={i}
                    issue={w}
                    jobId={jobId}
                    onDownloadParsed={() => void handleDownloadParsed()}
                    downloadingParsed={downloadingParsed}
                  />
                ))}
              </ul>
            </SectionPanel>
          )}

          {validation.interval_notes.length > 0 && (
            <p className="text-xs text-stone-400">{validation.interval_notes.join(" ")}</p>
          )}

          {(validation.module_readiness?.length ?? 0) > 0 && (
            <SectionPanel
              title="Fault / diagnostic module readiness"
              description="Confirmed after parsing your rows — not a repeat of Upload detection. Blocked modules list missing signals or config. Validation uses populated columns only."
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
                      <Badge tone={m.will_run ? "info" : "warning"}>
                        {m.will_run ? "Will run" : "Needs data"}
                      </Badge>
                      {m.module_kind === "analysis" || m.algorithm_id === "box_plot" ? (
                        <Badge tone="neutral">Analysis</Badge>
                      ) : null}
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

          {!hasBlockers && validation.warnings.length === 0 && canRunAnalysis && (
            <InfoBanner tone="success" title="Ready to analyze">
              No data-quality blockers. Review module readiness above, then run analysis.
            </InfoBanner>
          )}

          {error && <p className="text-sm text-rose-600 dark:text-rose-400">{error}</p>}

          <div className="flex flex-wrap justify-end gap-3 border-t border-stone-200/80 pt-4 dark:border-stone-800/80">
            <button
              type="button"
              className="btn-secondary"
              onClick={() => void handleDownloadParsed()}
              disabled={downloadingParsed}
              title="Download tidy parsed data (official headers) for offline verify / edit / re-upload"
            >
              {downloadingParsed ? "Downloading…" : "Download parsed Excel"}
            </button>
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
            {canRunAnalysis && (
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
