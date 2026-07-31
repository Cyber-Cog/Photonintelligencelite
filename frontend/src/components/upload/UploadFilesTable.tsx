import { Fragment, useState } from "react";
import { Badge } from "@/components/ui/Badge";
import { SignalChips } from "@/components/upload/UploadIntelligencePanel";
import type { UploadFileInventoryItem } from "@/types";

function detectedTone(label: string): "success" | "warning" | "neutral" {
  const n = label.toLowerCase();
  if (n.includes("could not")) return "neutral";
  if (n.includes("unmapped") || n.includes("registry")) return "warning";
  return "success";
}

function formatRange(start?: string | null, end?: string | null): string {
  if (start && end) return `${start} → ${end}`;
  if (start) return start;
  if (end) return end;
  return "—";
}

function formatRows(n: number): string {
  return n.toLocaleString();
}

function hierarchySummary(levels: UploadFileInventoryItem["hierarchy_levels"]): string {
  if (!levels?.length) return "—";
  return levels.map((l) => `${l.detected_count}/${l.total_count}`).join(" · ");
}

type Props = {
  files: UploadFileInventoryItem[];
  totalRows: number;
  fileCountLabel?: string;
};

export function UploadFilesTable({ files, totalRows, fileCountLabel }: Props) {
  const [expanded, setExpanded] = useState<string | null>(null);

  if (files.length === 0) return null;

  return (
    <div className="rounded-xl border border-[color:var(--pic-border)] bg-[color:var(--pic-surface-raised)]">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[color:var(--pic-border-subtle)] px-4 py-3">
        <p className="font-display text-[10px] font-semibold uppercase tracking-[0.14em] text-[color:var(--pic-text-muted)]">
          Files in this job
        </p>
        <p className="text-xs tabular-nums text-[color:var(--pic-text-muted)]">
          {fileCountLabel ?? `${files.length} file${files.length === 1 ? "" : "s"}`} · {formatRows(totalRows)} rows
        </p>
      </div>
      <table className="w-full table-fixed text-left text-sm">
        <colgroup>
          <col className="w-[3rem]" />
          <col className="w-[26%]" />
          <col className="w-[10%]" />
          <col className="w-[8%]" />
          <col className="w-[22%]" />
          <col className="w-[14%]" />
          <col className="w-[18%]" />
        </colgroup>
        <thead>
          <tr className="border-b border-[color:var(--pic-border-subtle)] text-[10px] font-semibold uppercase tracking-wider text-[color:var(--pic-text-muted)]">
            <th className="px-2 py-2.5" aria-label="Expand" />
            <th className="px-3 py-2.5 font-display">File</th>
            <th className="px-3 py-2.5 font-display">Sheet</th>
            <th className="px-3 py-2.5 font-display text-right">Rows</th>
            <th className="px-3 py-2.5 font-display">Range (UTC)</th>
            <th className="px-3 py-2.5 font-display">Signals</th>
            <th className="px-4 py-2.5 font-display">Detected as</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-[color:var(--pic-border-subtle)]">
          {files.map((f) => {
            const isOpen = expanded === f.filename;
            return (
              <Fragment key={f.filename}>
                <tr className="text-[color:var(--pic-text-secondary)]">
                  <td className="px-2 py-3 text-center align-top">
                    {(f.hierarchy_levels?.length ?? 0) > 0 ? (
                      <button
                        type="button"
                        className="rounded p-1 text-xs text-[color:var(--pic-text-muted)] hover:bg-stone-100 dark:hover:bg-stone-800"
                        aria-expanded={isOpen}
                        aria-label={isOpen ? "Collapse signal detail" : "Expand signal detail"}
                        onClick={() => setExpanded(isOpen ? null : f.filename)}
                      >
                        {isOpen ? "▾" : "▸"}
                      </button>
                    ) : null}
                  </td>
                  <td className="truncate px-3 py-3 font-medium text-[color:var(--pic-text)]" title={f.filename}>
                    {f.filename}
                  </td>
                  <td className="px-3 py-3 text-xs">{f.sheet_name || "—"}</td>
                  <td className="px-3 py-3 text-right tabular-nums">{formatRows(f.row_count)}</td>
                  <td className="px-3 py-3 text-xs">{formatRange(f.date_range_start, f.date_range_end)}</td>
                  <td className="px-3 py-3 text-xs tabular-nums">{hierarchySummary(f.hierarchy_levels)}</td>
                  <td className="px-4 py-3">
                    <Badge tone={detectedTone(f.detected_as)}>{f.detected_as}</Badge>
                  </td>
                </tr>
                {isOpen && f.hierarchy_levels?.length ? (
                  <tr className="bg-[color:var(--pic-surface-muted)]">
                    <td colSpan={7} className="border-t border-[color:var(--pic-border-subtle)] px-4 py-3">
                      <SignalChips levels={f.hierarchy_levels} dense />
                    </td>
                  </tr>
                ) : null}
              </Fragment>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
