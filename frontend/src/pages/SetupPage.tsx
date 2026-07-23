import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";
import { ApiError, detectEquipment, getSetupContext, submitMapping, submitPlantConfig } from "@/api/client";
import { EquipmentStructurePanel } from "@/components/EquipmentStructurePanel";
import { StepIndicator } from "@/components/StepIndicator";
import { Badge } from "@/components/ui/Badge";
import { InfoBanner } from "@/components/ui/InfoBanner";
import { PageHeader } from "@/components/ui/PageHeader";
import { SectionPanel } from "@/components/ui/SectionPanel";
import { Spinner } from "@/components/ui/Spinner";
import { SubnavTabs } from "@/components/ui/SubnavTabs";
import { useJob } from "@/context/JobContext";
import { CANONICAL_FIELD_OPTIONS, MODULE_TECHNOLOGY_OPTIONS, PLANT_TYPE_OPTIONS } from "@/lib/canonicalFields";
import {
  buildRatingsAndArchitecture,
  fromDetected,
  type EditableInverter,
} from "@/lib/equipmentStructure";
import {
  focusSetupField,
  parseSetupFocus,
  SETUP_FIELD_LABELS,
  setupFieldDomId,
} from "@/lib/setupFocus";
import { readUploadPath } from "@/lib/uploadPath";
import type { ColumnMappingSuggestion, PlantConfigInput } from "@/types";

type PlantForm = Omit<PlantConfigInput, "job_id" | "equipment_ratings" | "architecture"> & {
  modules_per_string?: number | null;
};

type FieldErrors = Partial<Record<string, string>>;
type SetupStep = "mapping" | "plant" | "architecture";

const SETUP_STEPS: { id: SetupStep; label: string }[] = [
  { id: "mapping", label: "Mapping" },
  { id: "plant", label: "Plant" },
  { id: "architecture", label: "Architecture" },
];

function sectionForField(key: string): SetupStep {
  if (key === "architecture") return "architecture";
  if (key === "timestamp" || key.startsWith("canonical:") || key.startsWith("column:")) return "mapping";
  return "plant";
}

const DEFAULT_PLANT: PlantForm = {
  plant_name: "",
  ac_capacity_mw: 0,
  dc_capacity_mwp: 0,
  module_rating_wp: 545,
  inverter_capacity_kw: 0,
  module_technology: MODULE_TECHNOLOGY_OPTIONS[0],
  bifacial: false,
  timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC",
  strings_per_scb: null,
  modules_per_string: 20,
  tariff_inr_per_kwh: null,
  pr_benchmark_pct: null,
  plant_type: "fixed_tilt",
};

function mappingHasEquipmentIds(mapping: Record<string, string>): boolean {
  const values = Object.values(mapping);
  return values.some((v) => v === "device_id" || v === "inverter_id" || v === "scb_id" || v === "string_id");
}

function isGarbageHeader(name: string): boolean {
  const n = name.trim().toLowerCase();
  return !n || n.startsWith("unnamed") || n.startsWith("column_");
}

function plantFromConfig(cfg: Record<string, unknown> | null | undefined): PlantForm {
  if (!cfg) return DEFAULT_PLANT;
  return {
    plant_name: String(cfg.plant_name ?? ""),
    ac_capacity_mw: Number(cfg.ac_capacity_mw ?? 0),
    dc_capacity_mwp: Number(cfg.dc_capacity_mwp ?? 0),
    module_rating_wp: Number(cfg.module_rating_wp ?? 545),
    inverter_capacity_kw: Number(cfg.inverter_capacity_kw ?? 0),
    module_technology: String(cfg.module_technology ?? MODULE_TECHNOLOGY_OPTIONS[0]),
    bifacial: Boolean(cfg.bifacial),
    timezone: String(cfg.timezone ?? DEFAULT_PLANT.timezone),
    strings_per_scb: cfg.strings_per_scb != null ? Number(cfg.strings_per_scb) : null,
    modules_per_string: cfg.modules_per_string != null ? Number(cfg.modules_per_string) : 20,
    tariff_inr_per_kwh: cfg.tariff_inr_per_kwh != null ? Number(cfg.tariff_inr_per_kwh) : null,
    pr_benchmark_pct: cfg.pr_benchmark_pct != null ? Number(cfg.pr_benchmark_pct) : null,
    plant_type: String(cfg.plant_type ?? "fixed_tilt"),
  };
}

function inputClass(invalid: boolean): string {
  return invalid
    ? "input border-amber-500 bg-amber-50/40 ring-2 ring-amber-400/70 dark:border-amber-500 dark:bg-amber-950/30 dark:ring-amber-500/40"
    : "input";
}

function FieldError({ message }: { message?: string }) {
  if (!message) return null;
  return (
    <p className="mt-1 text-xs font-medium text-amber-800 dark:text-amber-200" role="alert">
      {message}
    </p>
  );
}

export function SetupPage() {
  const { jobId } = useParams<{ jobId: string }>();
  const navigate = useNavigate();
  const location = useLocation();
  const { uploadInfo, setJob } = useJob();

  const [suggestions, setSuggestions] = useState<ColumnMappingSuggestion[]>(
    () => uploadInfo?.mapping_suggestions ?? [],
  );
  const [mapping, setMapping] = useState<Record<string, string>>(() => {
    const initial: Record<string, string> = {};
    for (const s of uploadInfo?.mapping_suggestions ?? []) {
      initial[s.column_name] = s.canonical_field ?? "ignore";
    }
    return initial;
  });
  const [plant, setPlant] = useState(DEFAULT_PLANT);
  const [equipment, setEquipment] = useState<EditableInverter[]>([]);
  const [detected, setDetected] = useState(false);
  const [detectNotes, setDetectNotes] = useState<string[]>([]);
  const [detecting, setDetecting] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [loadingContext, setLoadingContext] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  const [jobState, setJobState] = useState<string | null>(uploadInfo?.state ?? null);
  const [contextError, setContextError] = useState<string | null>(null);
  const [flashField, setFlashField] = useState<string | null>(null);
  const [activeStep, setActiveStep] = useState<SetupStep>("mapping");
  const [looksLikePack, setLooksLikePack] = useState<boolean | null>(
    () => uploadInfo?.looks_like_complete_pack ?? null,
  );
  const [packMatchRatio, setPackMatchRatio] = useState<number>(
    () => uploadInfo?.pack_match_ratio ?? 0,
  );
  const autoDetectDone = useRef(false);
  const focusApplied = useRef(false);
  const pendingFocusKey = useRef<string | null>(null);

  const clearFieldError = useCallback((key: string) => {
    setFieldErrors((prev) => {
      if (!prev[key]) return prev;
      const next = { ...prev };
      delete next[key];
      return next;
    });
  }, []);

  const applyFocus = useCallback((field: string | undefined, section?: string) => {
    const step: SetupStep | undefined =
      section === "mapping" || section === "plant" || section === "architecture"
        ? section
        : field
          ? sectionForField(field)
          : undefined;
    if (step) setActiveStep(step);

    if (field) {
      const key =
        field.startsWith("canonical:") || field.startsWith("column:") || field in SETUP_FIELD_LABELS
          ? field
          : section === "mapping"
            ? `canonical:${field}`
            : field;
      setFlashField(key);
      pendingFocusKey.current = key;
      return;
    }
    if (step) {
      pendingFocusKey.current = null;
      window.setTimeout(() => {
        document.getElementById(step)?.scrollIntoView({ behavior: "smooth", block: "start" });
      }, 40);
    }
  }, []);

  // After step content mounts, scroll/focus the pending field (deep-link or jump chips).
  useEffect(() => {
    const key = pendingFocusKey.current;
    if (!key) return;
    pendingFocusKey.current = null;
    const t = window.setTimeout(() => {
      focusSetupField(key);
      window.setTimeout(() => setFlashField(null), 2200);
    }, 60);
    return () => window.clearTimeout(t);
  }, [activeStep, flashField]);

  // Deep-link from Results / Validation Fix → exact control
  useEffect(() => {
    if (loadingContext || focusApplied.current) return;
    const { section, field } = parseSetupFocus(location.hash, location.search);
    if (!section && !field) return;
    focusApplied.current = true;
    const t = window.setTimeout(() => applyFocus(field, section), 100);
    return () => window.clearTimeout(t);
  }, [location.hash, location.search, loadingContext, suggestions.length, applyFocus]);

  // Always reload setup from the job (supports completed → edit & re-run).
  // If Excel is still parsing, poll until mapping (or failed).
  useEffect(() => {
    if (!jobId) return;
    let cancelled = false;
    let timer: number | undefined;

    const applyCtx = (ctx: Awaited<ReturnType<typeof getSetupContext>>) => {
      setSuggestions(ctx.mapping_suggestions);
      const next: Record<string, string> = {};
      for (const s of ctx.mapping_suggestions) {
        next[s.column_name] =
          ctx.current_mapping[s.column_name] ?? s.canonical_field ?? "ignore";
      }
      for (const [col, field] of Object.entries(ctx.current_mapping)) {
        if (!(col in next)) next[col] = field;
      }
      setMapping(next);
      if (ctx.plant_config) setPlant(plantFromConfig(ctx.plant_config));
      setJobState(ctx.state);
      setJob(jobId, {
        job_id: ctx.job_id,
        state: ctx.state,
        detected_columns: ctx.detected_columns,
        mapping_suggestions: ctx.mapping_suggestions,
        requires_manual_mapping: ctx.requires_manual_mapping,
        looks_like_complete_pack: ctx.looks_like_complete_pack ?? false,
        pack_match_ratio: ctx.pack_match_ratio ?? 0,
      });
      setLooksLikePack(ctx.looks_like_complete_pack ?? false);
      setPackMatchRatio(ctx.pack_match_ratio ?? 0);
      setContextError(null);
    };

    const load = async () => {
      setLoadingContext(true);
      try {
        for (;;) {
          if (cancelled) return;
          const ctx = await getSetupContext(jobId);
          if (cancelled) return;
          if (ctx.state === "parsing" || (ctx.state === "uploaded" && ctx.detected_columns.length === 0)) {
            setJobState(ctx.state);
            setContextError(null);
            setLoadingContext(true);
            await new Promise((r) => {
              timer = window.setTimeout(r, 1500);
            });
            continue;
          }
          applyCtx(ctx);
          setLoadingContext(false);
          return;
        }
      } catch (err) {
        if (cancelled) return;
        setContextError(
          err instanceof ApiError ? err.message : "Could not reload setup for this job.",
        );
        setLoadingContext(false);
      }
    };

    void load();
    return () => {
      cancelled = true;
      if (timer !== undefined) window.clearTimeout(timer);
    };
    // Intentionally only jobId — setJob from context must not retrigger (infinite reload).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobId]);

  const needsReview = useMemo(
    () =>
      suggestions.filter(
        (s) => s.band !== "auto" || isGarbageHeader(s.column_name) || s.canonical_field === "timestamp",
      ),
    [suggestions],
  );
  const autoMapped = useMemo(
    () =>
      suggestions.filter(
        (s) => s.band === "auto" && !isGarbageHeader(s.column_name) && s.canonical_field !== "timestamp",
      ),
    [suggestions],
  );
  /** Every detected column — never hide OEM columns behind pack assumptions. */
  const allColumns = useMemo(() => {
    const reviewKeys = new Set(needsReview.map((s) => s.column_name));
    return [...needsReview, ...autoMapped.filter((s) => !reviewKeys.has(s.column_name))];
  }, [needsReview, autoMapped]);

  const choseTemplatePath = jobId ? readUploadPath(jobId) === "template" : false;

  const timestampIsGarbage = useMemo(() => {
    const tsCol = Object.entries(mapping).find(([, v]) => v === "timestamp")?.[0];
    return tsCol ? isGarbageHeader(tsCol) : false;
  }, [mapping]);

  const runDetect = useCallback(async () => {
    if (!jobId) return;
    if (!mappingHasEquipmentIds(mapping)) {
      setDetectNotes([
        "Structure not detected: no Device ID / Inverter / SCB / String ID column is mapped. "
          + "Next: map an equipment ID column and re-detect, or use Excel template / pattern apply below.",
      ]);
      setDetected(false);
      setEquipment((prev) => prev);
      return;
    }
    setDetecting(true);
    setError(null);
    try {
      const res = await detectEquipment(jobId, mapping);
      setDetectNotes(res.notes);
      setDetected(res.detected);
      if (res.detected && res.inverters.length > 0) {
        setEquipment(fromDetected(res.inverters));
      } else {
        setEquipment((prev) => prev);
      }
    } catch (err) {
      setDetectNotes([
        err instanceof ApiError ? err.message : "Could not detect equipment from the upload.",
      ]);
      setEquipment((prev) => prev);
    } finally {
      setDetecting(false);
    }
  }, [jobId, mapping]);

  useEffect(() => {
    if (!jobId || loadingContext || suggestions.length === 0 || autoDetectDone.current) return;
    if (!mappingHasEquipmentIds(mapping)) {
      setEquipment((prev) => prev);
      setDetectNotes([
        "Structure not detected: map a Device ID (or Inverter / SCB / String ID) column to auto-detect, "
          + "or use Excel / pattern. Do not enter hundreds of inverters by hand.",
      ]);
      return;
    }
    autoDetectDone.current = true;
    void runDetect();
  }, [jobId, loadingContext, suggestions.length, mapping, runDetect]);

  const isInvalid = (key: string) => Boolean(fieldErrors[key]) || flashField === key;

  const validateAndCollectErrors = (): FieldErrors => {
    const next: FieldErrors = {};
    const hasTimestamp = Object.values(mapping).includes("timestamp");
    if (!hasTimestamp) {
      next.timestamp = "Map a Timestamp column before continuing.";
    } else if (timestampIsGarbage) {
      next.timestamp =
        "Timestamp is mapped to a broken header (Unnamed / Column_N). Choose the real Date/Time column.";
    }
    if (!plant.plant_name.trim()) {
      next.plant_name = "Enter the plant name.";
    }
    if (!(plant.ac_capacity_mw > 0)) {
      next.ac_capacity_mw = "Enter AC capacity greater than zero (MW).";
    }
    if (!(plant.dc_capacity_mwp > 0)) {
      next.dc_capacity_mwp = "Enter DC capacity greater than zero (MWp).";
    }
    if (!(plant.inverter_capacity_kw > 0)) {
      next.inverter_capacity_kw =
        "Enter a default inverter rating greater than zero (kW). Required for “Apply default rating to all”.";
    }
    if (equipment.length === 0 || equipment.every((e) => !e.inverter_id.trim())) {
      next.architecture =
        "Provide plant architecture: Excel upload, auto-detect from Device IDs, or apply an SMB pattern.";
    }
    return next;
  };

  const jumpToField = (key: string) => {
    applyFocus(key, sectionForField(key));
  };

  const stepIndex = SETUP_STEPS.findIndex((s) => s.id === activeStep);
  const goNextStep = () => {
    if (stepIndex < SETUP_STEPS.length - 1) {
      setActiveStep(SETUP_STEPS[stepIndex + 1].id);
      window.scrollTo({ top: 0, behavior: "smooth" });
    }
  };
  const goPrevStep = () => {
    if (stepIndex > 0) {
      setActiveStep(SETUP_STEPS[stepIndex - 1].id);
      window.scrollTo({ top: 0, behavior: "smooth" });
    }
  };

  if (!jobId) return null;

  if (loadingContext) {
    return (
      <div className="mx-auto flex max-w-xl flex-col gap-2 text-sm text-stone-500">
        <div className="flex items-center gap-2">
          <Spinner className="h-4 w-4" />
          {jobState === "parsing" || jobState === "uploaded"
            ? "Parsing Excel workbook… wide reports can take up to a minute."
            : "Reloading column mapping for this job…"}
        </div>
      </div>
    );
  }

  if (contextError && suggestions.length === 0) {
    return (
      <div className="mx-auto max-w-xl text-center">
        <p className="text-sm text-stone-500">{contextError}</p>
        <button type="button" className="btn-primary mt-4" onClick={() => navigate(jobId ? `/upload?replace=${jobId}` : "/upload")}>
          Replace files / Back to upload
        </button>
      </div>
    );
  }

  const handleSubmit = async () => {
    const nextErrors = validateAndCollectErrors();
    setFieldErrors(nextErrors);
    const keys = Object.keys(nextErrors);
    if (keys.length > 0) {
      setError(
        keys.length === 1
          ? nextErrors[keys[0]] ?? "Fix the highlighted field to continue."
          : `Fix ${keys.length} required fields below, then continue.`,
      );
      jumpToField(keys[0]);
      return;
    }

    const { equipment_ratings, architecture, strings_per_scb_fallback } =
      buildRatingsAndArchitecture(equipment, plant.modules_per_string ?? null);

    setSubmitting(true);
    setError(null);
    setFieldErrors({});
    try {
      await submitMapping(jobId, mapping);
      const { modules_per_string: _mps, ...plantPayload } = plant;
      await submitPlantConfig({
        job_id: jobId,
        ...plantPayload,
        strings_per_scb: plant.strings_per_scb ?? strings_per_scb_fallback,
        equipment_ratings,
        architecture,
      });
      navigate(`/jobs/${jobId}/validate`);
    } catch (err) {
      const msg =
        err instanceof ApiError
          ? err.status === 409 && /running|queued|generating/i.test(err.message)
            ? "Analysis is still running. Wait for it to finish, then edit mapping or plant details and Continue again. This will re-validate and require a re-run."
            : err.message
          : "Could not save setup details. Try again.";
      setError(msg);
    } finally {
      setSubmitting(false);
    }
  };

  const errorChipKeys = Object.keys(fieldErrors);
  const revisingCompleted = jobState === "completed";
  const errorsOnStep = (step: SetupStep) =>
    errorChipKeys.filter((k) => sectionForField(k) === step).length;

  return (
    <div className="tool-enter mx-auto w-full max-w-3xl pb-24">
      <StepIndicator current={2} jobId={jobId} />
      <PageHeader
        className="mb-4"
        eyebrow="Configure job"
        title="Confirm columns and plant details"
        description={
          <>
            Work through Mapping, Plant, then Architecture. All detected columns are listed below — map what you
            need, then confirm plant fields before continuing.
            {revisingCompleted
              ? " Editing a completed job clears prior results and re-runs validation."
              : " Returning from validation or results: edit below and Continue to re-validate."}
          </>
        }
        actions={
          <Link to={`/upload?replace=${encodeURIComponent(jobId)}`} className="btn-ghost text-xs">
            Replace files / Back to upload
          </Link>
        }
      />

      {looksLikePack === true && (
        <InfoBanner className="mb-3" tone="success" title="Complete Analysis Pack detected">
          Headers match the official pack ({Math.round(packMatchRatio * 100)}% overlap). Columns are auto-mapped
          where confidence is high — you can still edit any row below.
        </InfoBanner>
      )}

      {looksLikePack === false && (
        <InfoBanner
          className="mb-3"
          tone="warning"
          title={
            choseTemplatePath
              ? "These files don’t look like the Complete Analysis Pack"
              : "Own SCADA format — map columns in Setup"
          }
        >
          {choseTemplatePath
            ? "You chose the template path, but uploaded headers don’t match the pack. You’ll map columns below (nothing is assumed to be pack layout)."
            : "Map each detected column to a PIC Lite field. Nothing is hidden — every column from the upload is listed."}
        </InfoBanner>
      )}

      {revisingCompleted && (
        <InfoBanner className="mb-3" tone="warning" title="Edit and re-run">
          This job already finished. Saving mapping or plant changes clears prior results and returns you to
          validation. Run analysis again after validation.
        </InfoBanner>
      )}

      {timestampIsGarbage && (
        <InfoBanner className="mb-3" tone="warning" title="Timestamp mapping">
          Timestamp is mapped to a placeholder column (Unnamed / Column_N), often from Excel title rows. Map Timestamp
          to the real date/time column (for example &quot;Date And Time&quot;) before continuing.
        </InfoBanner>
      )}

      <div className="setup-workspace mb-3">
        <div className="setup-workspace-tabs">
          <SubnavTabs
            inset
            items={SETUP_STEPS.map((s) => ({
              id: s.id,
              label: errorsOnStep(s.id) > 0 ? `${s.label} (${errorsOnStep(s.id)})` : s.label,
            }))}
            activeId={activeStep}
            onSelect={(id) => setActiveStep(id as SetupStep)}
            ariaLabel="Setup steps"
          />
        </div>

        <div className="setup-workspace-body min-w-0">
      {activeStep === "mapping" && (
        <>
          {allColumns.length === 0 ? (
            <div
              id="mapping"
              className="scroll-mt-44 px-4 py-4 text-xs text-stone-500 sm:px-5 dark:text-stone-400"
            >
              No columns detected.{" "}
              <Link to={`/upload?replace=${encodeURIComponent(jobId)}`} className="font-semibold underline">
                Replace files / Back to upload
              </Link>
            </div>
          ) : (
            <SectionPanel
              id="mapping"
              embedded
              scrollMargin
              title="Column mapping"
              description={`${allColumns.length} detected column${allColumns.length === 1 ? "" : "s"} — review every row (auto-mapped included)`}
            >
              {fieldErrors.timestamp && (
                <p className="mb-3 text-xs font-medium text-amber-800 dark:text-amber-200" role="alert">
                  {fieldErrors.timestamp}
                </p>
              )}
              <div className="divide-y divide-stone-100 dark:divide-stone-800">
                {allColumns.map((s: ColumnMappingSuggestion) => {
                  const mappedAs = mapping[s.column_name];
                  const isTs = mappedAs === "timestamp" || s.canonical_field === "timestamp";
                  const isAuto =
                    s.band === "auto" && !isGarbageHeader(s.column_name) && s.canonical_field !== "timestamp";
                  const rowId = isTs
                    ? setupFieldDomId("timestamp")
                    : mappedAs && mappedAs !== "ignore"
                      ? setupFieldDomId(`canonical:${mappedAs}`)
                      : setupFieldDomId(`column:${s.column_name}`);
                  const invalid = isTs && Boolean(fieldErrors.timestamp);
                  const flash = flashField === `canonical:${mappedAs}` || flashField === `column:${s.column_name}`;
                  return (
                    <div
                      key={s.column_name}
                      id={rowId}
                      className={`flex items-center justify-between gap-4 py-2.5 ${
                        invalid || flash ? "setup-field-flash rounded px-1" : ""
                      }`}
                    >
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-sm text-stone-700 dark:text-stone-200">{s.column_name}</p>
                        <div className="mt-0.5 flex flex-wrap gap-1">
                          {isAuto ? (
                            <Badge tone="success">Auto-mapped</Badge>
                          ) : (
                            <Badge
                              tone={s.band === "confirm" || s.canonical_field === "timestamp" ? "warning" : "danger"}
                            >
                              {s.canonical_field === "timestamp"
                                ? "Timestamp: confirm"
                                : s.band === "confirm"
                                  ? `${Math.round(s.confidence * 100)}% confidence`
                                  : "Needs mapping"}
                            </Badge>
                          )}
                          {isGarbageHeader(s.column_name) && <Badge tone="danger">Broken header</Badge>}
                        </div>
                      </div>
                      <select
                        className={`input max-w-xs ${invalid ? "border-amber-500 ring-2 ring-amber-400/70" : ""}`}
                        aria-invalid={invalid}
                        value={mapping[s.column_name] ?? "ignore"}
                        onChange={(e) => {
                          autoDetectDone.current = false;
                          clearFieldError("timestamp");
                          setMapping((m) => ({ ...m, [s.column_name]: e.target.value }));
                        }}
                      >
                        {CANONICAL_FIELD_OPTIONS.map((opt) => (
                          <option key={opt.value} value={opt.value}>
                            {opt.label}
                          </option>
                        ))}
                      </select>
                    </div>
                  );
                })}
              </div>
            </SectionPanel>
          )}
        </>
      )}

      {activeStep === "plant" && (
        <SectionPanel
          id="plant"
          embedded
          scrollMargin
          title="Plant summary"
          description="Required fields marked with *"
        >
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div
              id={setupFieldDomId("plant_name")}
              className={`sm:col-span-2 rounded-lg ${isInvalid("plant_name") ? "setup-field-flash p-1" : ""}`}
            >
              <label className="label" htmlFor="plant_name_input">
                Plant name <span className="text-rose-600">*</span>
              </label>
              <input
                id="plant_name_input"
                className={inputClass(isInvalid("plant_name"))}
                aria-invalid={isInvalid("plant_name")}
                value={plant.plant_name}
                onChange={(e) => {
                  clearFieldError("plant_name");
                  setPlant((p) => ({ ...p, plant_name: e.target.value }));
                }}
              />
              <FieldError message={fieldErrors.plant_name} />
            </div>
            <div
              id={setupFieldDomId("ac_capacity_mw")}
              className={isInvalid("ac_capacity_mw") ? "setup-field-flash rounded-lg p-1" : ""}
            >
              <label className="label" htmlFor="ac_capacity_input">
                AC capacity (MW) <span className="text-rose-600">*</span>
              </label>
              <input
                id="ac_capacity_input"
                type="number"
                className={inputClass(isInvalid("ac_capacity_mw"))}
                aria-invalid={isInvalid("ac_capacity_mw")}
                value={plant.ac_capacity_mw || ""}
                onChange={(e) => {
                  clearFieldError("ac_capacity_mw");
                  setPlant((p) => ({ ...p, ac_capacity_mw: Number(e.target.value) }));
                }}
              />
              <FieldError message={fieldErrors.ac_capacity_mw} />
            </div>
            <div
              id={setupFieldDomId("dc_capacity_mwp")}
              className={isInvalid("dc_capacity_mwp") ? "setup-field-flash rounded-lg p-1" : ""}
            >
              <label className="label" htmlFor="dc_capacity_input">
                DC capacity (MWp) <span className="text-rose-600">*</span>
              </label>
              <input
                id="dc_capacity_input"
                type="number"
                className={inputClass(isInvalid("dc_capacity_mwp"))}
                aria-invalid={isInvalid("dc_capacity_mwp")}
                value={plant.dc_capacity_mwp || ""}
                onChange={(e) => {
                  clearFieldError("dc_capacity_mwp");
                  setPlant((p) => ({ ...p, dc_capacity_mwp: Number(e.target.value) }));
                }}
              />
              <FieldError message={fieldErrors.dc_capacity_mwp} />
            </div>
            <div>
              <label className="label">Module rating (Wp)</label>
              <input
                type="number"
                className="input"
                value={plant.module_rating_wp || ""}
                onChange={(e) => setPlant((p) => ({ ...p, module_rating_wp: Number(e.target.value) }))}
              />
            </div>
            <div
              id={setupFieldDomId("inverter_capacity_kw")}
              className={isInvalid("inverter_capacity_kw") ? "setup-field-flash rounded-lg p-1" : ""}
            >
              <label className="label" htmlFor="inverter_rating_input">
                Default inverter rating (kW) <span className="text-rose-600">*</span>
              </label>
              <input
                id="inverter_rating_input"
                type="number"
                className={inputClass(isInvalid("inverter_capacity_kw"))}
                aria-invalid={isInvalid("inverter_capacity_kw")}
                value={plant.inverter_capacity_kw || ""}
                onChange={(e) => {
                  clearFieldError("inverter_capacity_kw");
                  setPlant((p) => ({ ...p, inverter_capacity_kw: Number(e.target.value) }));
                }}
              />
              <FieldError message={fieldErrors.inverter_capacity_kw} />
              {!fieldErrors.inverter_capacity_kw && (
                <p className="mt-1 text-xs text-stone-400">
                  Fallback when a specific inverter has no rating. Use “Apply to all” on the Architecture step for mixed
                  plants that share one rating.
                </p>
              )}
            </div>
            <div>
              <label className="label">Module technology</label>
              <select
                className="input"
                value={plant.module_technology}
                onChange={(e) => setPlant((p) => ({ ...p, module_technology: e.target.value }))}
              >
                {MODULE_TECHNOLOGY_OPTIONS.map((t) => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="label">Plant type</label>
              <select
                className="input"
                value={plant.plant_type}
                onChange={(e) => setPlant((p) => ({ ...p, plant_type: e.target.value }))}
              >
                {PLANT_TYPE_OPTIONS.map((t) => (
                  <option key={t.value} value={t.value}>
                    {t.label}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="label">Timezone (IANA)</label>
              <input
                className="input"
                value={plant.timezone}
                onChange={(e) => setPlant((p) => ({ ...p, timezone: e.target.value }))}
              />
            </div>
            <div className="flex items-center gap-2 pt-6">
              <input
                id="bifacial"
                type="checkbox"
                checked={plant.bifacial}
                onChange={(e) => setPlant((p) => ({ ...p, bifacial: e.target.checked }))}
                className="h-4 w-4 rounded border-stone-300 text-brand-600 focus:ring-brand-500"
              />
              <label htmlFor="bifacial" className="text-sm text-stone-600 dark:text-stone-300">
                Bifacial modules
              </label>
            </div>
          </div>

          <details className="mt-4" open={isInvalid("tariff_inr_per_kwh") || flashField === "tariff_inr_per_kwh"}>
            <summary className="cursor-pointer text-xs font-medium uppercase tracking-wide text-stone-500">
              Optional details
            </summary>
            <div className="mt-3 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <div>
                <label className="label">Fallback strings / SCB</label>
                <input
                  type="number"
                  className="input"
                  placeholder="Auto from structure"
                  value={plant.strings_per_scb ?? ""}
                  onChange={(e) =>
                    setPlant((p) => ({
                      ...p,
                      strings_per_scb: e.target.value ? Number(e.target.value) : null,
                    }))
                  }
                />
                <p className="mt-1 text-xs text-stone-400">Only used when a SCB has no string count.</p>
              </div>
              <div>
                <label className="label">Modules per string</label>
                <input
                  type="number"
                  className="input"
                  value={plant.modules_per_string ?? ""}
                  onChange={(e) =>
                    setPlant((p) => ({
                      ...p,
                      modules_per_string: e.target.value ? Number(e.target.value) : null,
                    }))
                  }
                />
                <p className="mt-1 text-xs text-stone-400">Needed for module-damage loss magnitude.</p>
              </div>
              <div
                id={setupFieldDomId("tariff_inr_per_kwh")}
                className={flashField === "tariff_inr_per_kwh" ? "setup-field-flash rounded-lg p-1" : ""}
              >
                <label className="label">Tariff (₹/kWh)</label>
                <input
                  type="number"
                  className={inputClass(flashField === "tariff_inr_per_kwh")}
                  value={plant.tariff_inr_per_kwh ?? ""}
                  onChange={(e) =>
                    setPlant((p) => ({
                      ...p,
                      tariff_inr_per_kwh: e.target.value ? Number(e.target.value) : null,
                    }))
                  }
                />
              </div>
              <div>
                <label className="label">PR benchmark (%)</label>
                <input
                  type="number"
                  className="input"
                  value={plant.pr_benchmark_pct ?? ""}
                  onChange={(e) =>
                    setPlant((p) => ({
                      ...p,
                      pr_benchmark_pct: e.target.value ? Number(e.target.value) : null,
                    }))
                  }
                />
              </div>
            </div>
          </details>
        </SectionPanel>
      )}

      {activeStep === "architecture" && (
        <EquipmentStructurePanel
          embedded
          equipment={equipment}
          onChange={(next) => {
            clearFieldError("architecture");
            setEquipment(next);
          }}
          defaultRatingKw={plant.inverter_capacity_kw}
          detected={detected}
          detecting={detecting}
          notes={detectNotes}
          architectureError={fieldErrors.architecture}
          highlightDefaultRating={isInvalid("inverter_capacity_kw")}
          onDetect={() => {
            autoDetectDone.current = true;
            void runDetect();
          }}
          onJumpToInverterRating={() => jumpToField("inverter_capacity_kw")}
        />
      )}
        </div>
      </div>

      {/* Sticky primary action + validation summary — same max width as workspace */}
      <div className="pointer-events-none fixed bottom-0 left-0 right-0 z-30">
        <div className="pointer-events-auto border-t border-stone-200/90 bg-white/95 shadow-[0_-4px_16px_rgba(28,25,23,0.06)] backdrop-blur-md dark:border-stone-800 dark:bg-stone-950 dark:shadow-[0_-4px_16px_rgba(0,0,0,0.35)]">
          <div className="mx-auto w-full max-w-6xl px-4 sm:px-6">
            <div className="mx-auto flex w-full max-w-3xl flex-col gap-2 py-3 sm:flex-row sm:items-center sm:justify-between">
              <div className="min-w-0 flex-1">
                {errorChipKeys.length > 0 ? (
                  <div>
                    <p className="text-[11px] font-semibold uppercase tracking-wide text-amber-800 dark:text-amber-200">
                      Fix {errorChipKeys.length} required field{errorChipKeys.length === 1 ? "" : "s"}
                    </p>
                    <div className="mt-1 flex flex-wrap gap-1.5">
                      {errorChipKeys.map((key) => (
                        <button
                          key={key}
                          type="button"
                          className="rounded border border-amber-400/80 bg-amber-50 px-2 py-0.5 text-[11px] font-semibold text-amber-900 hover:bg-amber-100 dark:border-amber-700 dark:bg-amber-950/60 dark:text-amber-100 dark:hover:bg-amber-900/50"
                          onClick={() => jumpToField(key)}
                        >
                          {SETUP_FIELD_LABELS[key] ?? key}
                        </button>
                      ))}
                    </div>
                  </div>
                ) : error ? (
                  <p className="text-sm text-rose-600 dark:text-rose-400" role="alert">
                    {error}
                  </p>
                ) : (
                  <p className="text-xs text-stone-500">
                    Step {stepIndex + 1} of {SETUP_STEPS.length}: {SETUP_STEPS[stepIndex].label}
                  </p>
                )}
              </div>
              <div className="flex shrink-0 items-center justify-end gap-2">
                {stepIndex > 0 && (
                  <button type="button" className="btn-secondary text-sm" onClick={goPrevStep} disabled={submitting}>
                    Back
                  </button>
                )}
                {stepIndex < SETUP_STEPS.length - 1 && (
                  <button type="button" className="btn-secondary text-sm" onClick={goNextStep} disabled={submitting}>
                    Next
                  </button>
                )}
                <button
                  type="button"
                  className="btn-primary"
                  onClick={handleSubmit}
                  disabled={submitting || detecting}
                >
                  {submitting ? <Spinner className="h-4 w-4" /> : null}
                  {revisingCompleted ? "Save & re-validate" : "Continue"}
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
