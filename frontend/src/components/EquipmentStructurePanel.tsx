import { useMemo, useRef, useState } from "react";
import { ApiError, applyArchitecturePattern, architectureTemplateUrl, uploadArchitectureExcel } from "@/api/client";
import {
  emptyInverter,
  fromDetected,
  fromPatternPayload,
  generateInverterIds,
  summarizeEquipment,
  type EditableInverter,
  type EditableScb,
} from "@/lib/equipmentStructure";

interface Props {
  equipment: EditableInverter[];
  onChange: (next: EditableInverter[]) => void;
  defaultRatingKw: number;
  detected: boolean;
  detecting: boolean;
  notes: string[];
  onDetect: () => void;
  architectureError?: string | null;
  highlightDefaultRating?: boolean;
  onJumpToInverterRating?: () => void;
  /** Flatten outer card when nested in Setup’s shared step shell. */
  embedded?: boolean;
}

const DETAIL_PAGE_SIZE = 40;

export function EquipmentStructurePanel({
  equipment,
  onChange,
  defaultRatingKw,
  detected,
  detecting,
  notes,
  onDetect,
  architectureError = null,
  highlightDefaultRating = false,
  onJumpToInverterRating,
  embedded = false,
}: Props) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);
  const [patternBusy, setPatternBusy] = useState(false);
  const [localError, setLocalError] = useState<string | null>(null);
  const [showDetails, setShowDetails] = useState(false);
  const [detailLimit, setDetailLimit] = useState(DETAIL_PAGE_SIZE);

  // Pattern helper state
  const [invCount, setInvCount] = useState(2);
  const [smbsPerInv, setSmbsPerInv] = useState(16);
  const [stringsPerSmb, setStringsPerSmb] = useState(24);
  const [applyToAll, setApplyToAll] = useState(true);

  const summary = useMemo(() => summarizeEquipment(equipment), [equipment]);

  const patternTotals = useMemo(() => {
    const invForPattern =
      applyToAll && equipment.some((e) => e.inverter_id.trim())
        ? equipment.filter((e) => e.inverter_id.trim()).length
        : Math.max(0, invCount);
    return {
      inverters: invForPattern,
      smbs: invForPattern * Math.max(0, smbsPerInv),
      strings: invForPattern * Math.max(0, smbsPerInv) * Math.max(0, stringsPerSmb),
    };
  }, [applyToAll, equipment, invCount, smbsPerInv, stringsPerSmb]);

  const updateInverter = (idx: number, patch: Partial<EditableInverter>) => {
    onChange(equipment.map((inv, i) => (i === idx ? { ...inv, ...patch } : inv)));
  };

  const updateScb = (invIdx: number, scbIdx: number, patch: Partial<EditableScb>) => {
    onChange(
      equipment.map((inv, i) => {
        if (i !== invIdx) return inv;
        return {
          ...inv,
          scbs: inv.scbs.map((s, j) => (j === scbIdx ? { ...s, ...patch } : s)),
        };
      }),
    );
  };

  const applyRatingToAll = () => {
    if (!(defaultRatingKw > 0)) return;
    onChange(equipment.map((inv) => ({ ...inv, rated_kw: defaultRatingKw })));
  };

  const handleUpload = async (file: File | null) => {
    if (!file) return;
    setUploading(true);
    setLocalError(null);
    try {
      const res = await uploadArchitectureExcel(file);
      const next = fromDetected(res.inverters, res.inverter_ratings);
      onChange(next);
      setShowDetails(false);
      setDetailLimit(DETAIL_PAGE_SIZE);
    } catch (err) {
      setLocalError(err instanceof ApiError ? err.message : "Could not parse architecture Excel.");
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  const handlePattern = async () => {
    setPatternBusy(true);
    setLocalError(null);
    try {
      const ids =
        applyToAll && equipment.some((e) => e.inverter_id.trim())
          ? equipment.map((e) => e.inverter_id.trim()).filter(Boolean)
          : generateInverterIds(invCount);
      const res = await applyArchitecturePattern({
        inverter_ids: ids,
        smbs_per_inverter: smbsPerInv,
        strings_per_smb: stringsPerSmb,
        rated_kw: defaultRatingKw > 0 ? defaultRatingKw : null,
        existing_inverters: applyToAll ? [] : equipment,
      });
      onChange(fromPatternPayload(res.inverters as EditableInverter[]));
      setShowDetails(false);
    } catch (err) {
      setLocalError(err instanceof ApiError ? err.message : "Could not apply pattern.");
    } finally {
      setPatternBusy(false);
    }
  };

  const visible = equipment.slice(0, detailLimit);

  return (
    <section
      id="architecture"
      className={
        embedded
          ? "scroll-mt-44 bg-transparent"
          : "mb-3 scroll-mt-20 overflow-hidden rounded-xl border border-stone-200/90 bg-white shadow-sm dark:border-stone-800 dark:bg-stone-900/60"
      }
    >
      <div
        id="setup-field-architecture"
        className={`px-4 pb-0 pt-4 sm:px-5 sm:pt-5 ${architectureError ? "setup-field-flash rounded-t-xl" : ""}`}
      >
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="flex items-center gap-2">
              <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-brand-500" aria-hidden />
              <h3 className="font-display text-sm font-semibold tracking-tight text-stone-900 dark:text-stone-50">
                Equipment structure <span className="text-rose-600">*</span>
              </h3>
            </div>
            <p className="mt-1 pl-3.5 text-xs text-stone-500">
              For large plants, use Excel template, auto-detect from SCADA IDs, or apply a bulk pattern.
            </p>
          </div>
          <button type="button" className="btn-secondary text-xs" onClick={onDetect} disabled={detecting}>
            {detecting ? "Detecting…" : "Re-detect from data"}
          </button>
        </div>
        {architectureError && (
          <p className="mt-2 text-xs font-medium text-amber-800 dark:text-amber-200" role="alert">
            {architectureError}
          </p>
        )}
      </div>

      <div className="p-4 sm:p-5">
      {/* Summary tree */}
      <div className="mb-4 grid grid-cols-2 gap-2 sm:grid-cols-4">
        <div className="rounded-lg border border-stone-200/90 bg-stone-50 px-3 py-2 dark:border-stone-700 dark:bg-stone-800/60">
          <p className="text-xs font-medium text-stone-500">Inverters</p>
          <p className="mt-0.5 font-display text-lg font-semibold text-stone-800 dark:text-stone-100">{summary.inverterCount}</p>
        </div>
        <div className="rounded-lg border border-stone-200/90 bg-stone-50 px-3 py-2 dark:border-stone-700 dark:bg-stone-800/60">
          <p className="text-xs font-medium text-stone-500">SMBs / SCBs</p>
          <p className="mt-0.5 font-display text-lg font-semibold text-stone-800 dark:text-stone-100">{summary.scbCount}</p>
        </div>
        <div className="rounded-lg border border-stone-200/90 bg-stone-50 px-3 py-2 dark:border-stone-700 dark:bg-stone-800/60">
          <p className="text-xs font-medium text-stone-500">Strings</p>
          <p className="mt-0.5 font-display text-lg font-semibold text-stone-800 dark:text-stone-100">
            {summary.stringCount != null ? summary.stringCount.toLocaleString() : "—"}
          </p>
        </div>
        <div className="rounded-lg border border-stone-200/90 bg-stone-50 px-3 py-2 dark:border-stone-700 dark:bg-stone-800/60">
          <p className="text-xs font-medium text-stone-500">Rated inverters</p>
          <p className="mt-0.5 font-display text-lg font-semibold text-stone-800 dark:text-stone-100">{summary.ratedCount}</p>
        </div>
      </div>

      {notes.length > 0 && (
        <ul className="mb-4 space-y-1 rounded-md border border-amber-200/80 bg-amber-50 px-3 py-2 text-xs text-amber-900 dark:border-amber-800/50 dark:bg-amber-950/30 dark:text-amber-200">
          {notes.map((n) => (
            <li key={n}>{n}</li>
          ))}
        </ul>
      )}

      {/* Method A: Excel */}
      <div className="mb-3 rounded border border-stone-200 p-3 dark:border-stone-700">
        <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">Method A: Excel template</p>
        <p className="mt-1 text-xs text-slate-500">
          Download, complete offline (suitable for ~300 inverters / ~2000 SMBs), then upload. Columns: inverter_id,
          inverter_rated_kw, scb_id, strings_per_scb.
        </p>
        <div className="mt-3 flex flex-wrap gap-2">
          <a className="btn-secondary text-xs" href={architectureTemplateUrl()} download>
            Download template
          </a>
          <button
            type="button"
            className="btn-primary text-xs"
            disabled={uploading}
            onClick={() => fileRef.current?.click()}
          >
            {uploading ? "Uploading…" : "Upload files"}
          </button>
          <input
            ref={fileRef}
            type="file"
            accept=".xlsx,.xlsm"
            className="hidden"
            onChange={(e) => void handleUpload(e.target.files?.[0] ?? null)}
          />
        </div>
      </div>

      {/* Method B: Auto-detect */}
      <div className="mb-3 rounded border border-stone-200 p-3 dark:border-stone-700">
        <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">Method B: Auto-detect from SCADA</p>
        <p className="mt-1 text-xs text-slate-500">
          Map Device ID (or Inverter / SCB / String ID), then re-detect. If detection fails, the note above explains
          the next step.
        </p>
        <div className="mt-2 flex flex-wrap items-center gap-2 text-xs">
          <span className={detected ? "text-emerald-600 dark:text-emerald-400" : "text-amber-600 dark:text-amber-400"}>
            {detected ? "Structure detected from upload." : "Not detected yet. Map IDs or use Excel / pattern."}
          </span>
        </div>
      </div>

      {/* Method C: Pattern */}
      <div className="mb-3 rounded border border-stone-200 p-3 dark:border-stone-700">
        <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">
          Method C: Bulk pattern (exceptions via Excel)
        </p>
        <p className="mt-1 text-xs text-slate-500">
          Apply “N SMBs × M strings” to all / generated inverters, then download template to edit exceptions.
        </p>
        <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
          <div>
            <label className="label">Inverter count</label>
            <input
              type="number"
              className="input"
              min={1}
              max={2000}
              value={invCount}
              disabled={applyToAll && equipment.length > 0}
              onChange={(e) => setInvCount(Number(e.target.value) || 1)}
            />
          </div>
          <div>
            <label className="label">SMBs / inverter</label>
            <input
              type="number"
              className="input"
              min={1}
              max={64}
              value={smbsPerInv}
              onChange={(e) => setSmbsPerInv(Number(e.target.value) || 1)}
            />
          </div>
          <div>
            <label className="label">Strings / SMB</label>
            <input
              type="number"
              className="input"
              min={1}
              max={64}
              value={stringsPerSmb}
              onChange={(e) => setStringsPerSmb(Number(e.target.value) || 1)}
            />
          </div>
          <div className="flex items-end">
            <label className="flex items-center gap-2 pb-2 text-xs text-slate-600 dark:text-slate-300">
              <input
                type="checkbox"
                checked={applyToAll}
                onChange={(e) => setApplyToAll(e.target.checked)}
                className="h-4 w-4 rounded border-slate-300 text-brand-600"
              />
              Apply to current list
            </label>
          </div>
        </div>
        <div className="mt-3 flex flex-wrap items-center gap-3">
          <button type="button" className="btn-secondary text-xs" onClick={() => void handlePattern()} disabled={patternBusy}>
            {patternBusy ? "Applying…" : "Apply pattern"}
          </button>
          <p className="text-xs font-medium text-slate-600 dark:text-slate-300">
            {patternTotals.inverters.toLocaleString()} INV × {Math.max(0, smbsPerInv)} SMB ={" "}
            <span className="text-brand-700 dark:text-brand-300">{patternTotals.smbs.toLocaleString()} SMBs</span>
            {" · "}
            {patternTotals.strings.toLocaleString()} strings
          </p>
        </div>
      </div>

      <div
        id="setup-field-apply-default-rating"
        className={`mb-3 flex flex-wrap items-center gap-2 rounded-lg ${
          highlightDefaultRating ? "setup-field-flash border border-amber-400/80 bg-amber-50/60 p-2 dark:border-amber-700 dark:bg-amber-950/30" : ""
        }`}
      >
        <button
          type="button"
          className={`btn-secondary text-xs ${highlightDefaultRating ? "border-amber-500 ring-2 ring-amber-400/70" : ""}`}
          onClick={() => {
            if (!(defaultRatingKw > 0)) {
              onJumpToInverterRating?.();
              return;
            }
            applyRatingToAll();
          }}
          disabled={equipment.length === 0 && defaultRatingKw > 0}
          aria-invalid={highlightDefaultRating}
        >
          Apply default rating ({defaultRatingKw > 0 ? `${defaultRatingKw} kW` : "—"}) to all
        </button>
        {highlightDefaultRating && (
          <button
            type="button"
            className="text-xs font-semibold text-amber-900 underline dark:text-amber-200"
            onClick={() => onJumpToInverterRating?.()}
          >
            Set default inverter rating above
          </button>
        )}
        <button
          type="button"
          className="btn-ghost text-xs"
          onClick={() => setShowDetails((v) => !v)}
          disabled={equipment.length === 0}
        >
          {showDetails ? "Hide row editor" : `Show row editor (${summary.inverterCount} inv)`}
        </button>
      </div>

      {localError && <p className="mb-3 text-xs text-rose-600 dark:text-rose-400">{localError}</p>}

      {showDetails && (
        <div className="max-h-[480px] space-y-3 overflow-y-auto rounded-md border border-slate-200 p-2 dark:border-slate-700">
          {visible.map((inv, invIdx) => (
            <div key={`${inv.inverter_id}-${invIdx}`} className="rounded-md border border-slate-100 p-2 dark:border-slate-800">
              <div className="mb-2 grid grid-cols-1 gap-2 sm:grid-cols-[1fr_120px_auto] sm:items-end">
                <div>
                  <label className="label">Inverter ID</label>
                  <input
                    className="input"
                    value={inv.inverter_id}
                    onChange={(e) => updateInverter(invIdx, { inverter_id: e.target.value })}
                  />
                </div>
                <div>
                  <label className="label">Rated kW</label>
                  <input
                    type="number"
                    className="input"
                    placeholder="—"
                    value={inv.rated_kw ?? ""}
                    onChange={(e) =>
                      updateInverter(invIdx, {
                        rated_kw: e.target.value === "" ? null : Number(e.target.value),
                      })
                    }
                  />
                </div>
                <button
                  type="button"
                  className="btn-ghost text-xs text-rose-600"
                  onClick={() => onChange(equipment.filter((_, i) => i !== invIdx))}
                >
                  Remove
                </button>
              </div>
              <p className="mb-1 text-[10px] font-medium uppercase tracking-wide text-slate-400">
                SMBs ({inv.scbs.length})
              </p>
              {inv.scbs.slice(0, 12).map((scb, scbIdx) => (
                <div key={`${scb.scb_id}-${scbIdx}`} className="mb-1 grid grid-cols-1 gap-1 sm:grid-cols-[1fr_100px]">
                  <input
                    className="input text-xs"
                    value={scb.scb_id}
                    onChange={(e) => updateScb(invIdx, scbIdx, { scb_id: e.target.value })}
                  />
                  <input
                    type="number"
                    className="input text-xs"
                    placeholder="strings"
                    value={scb.strings_per_scb ?? ""}
                    onChange={(e) =>
                      updateScb(invIdx, scbIdx, {
                        strings_per_scb: e.target.value === "" ? null : Number(e.target.value),
                        strings_detected: false,
                      })
                    }
                  />
                </div>
              ))}
              {inv.scbs.length > 12 && (
                <p className="text-[10px] text-slate-400">
                  +{inv.scbs.length - 12} more SMBs. Edit via Excel template for bulk changes.
                </p>
              )}
            </div>
          ))}
          {equipment.length > detailLimit && (
            <button
              type="button"
              className="btn-secondary w-full text-xs"
              onClick={() => setDetailLimit((n) => n + DETAIL_PAGE_SIZE)}
            >
              Show more ({detailLimit} / {equipment.length})
            </button>
          )}
          <button
            type="button"
            className="btn-secondary text-xs"
            onClick={() => onChange([...equipment, emptyInverter(equipment.length + 1)])}
          >
            Add one inverter (small plants only)
          </button>
        </div>
      )}
      </div>
    </section>
  );
}
