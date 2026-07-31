import { useEffect, useId, useRef, useState } from "react";
import { Spinner } from "@/components/ui/Spinner";

export type TemplateKind = "excel" | "zip";

type DownloadTemplateMenuProps = {
  onSelect: (kind: TemplateKind) => void;
  /** Button visual style — outlined secondary by default for download CTAs. */
  buttonClassName?: string;
  label?: string;
  disabled?: boolean;
  downloading?: TemplateKind | null;
  align?: "left" | "right";
};

const OPTIONS: { kind: TemplateKind; label: string; hint: string }[] = [
  { kind: "excel", label: "Excel template", hint: ".xlsx workbook" },
  { kind: "zip", label: "CSV package", hint: ".zip of CSVs" },
];

export function DownloadTemplateMenu({
  onSelect,
  buttonClassName = "btn-secondary text-sm",
  label = "Download template",
  disabled = false,
  downloading = null,
  align = "left",
}: DownloadTemplateMenuProps) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const menuId = useId();
  const busy = downloading !== null;

  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  useEffect(() => {
    if (busy) setOpen(false);
  }, [busy]);

  const pick = (kind: TemplateKind) => {
    setOpen(false);
    onSelect(kind);
  };

  return (
    <div className="relative inline-flex" ref={rootRef}>
      <button
        type="button"
        className={buttonClassName}
        disabled={disabled || busy}
        aria-expanded={open}
        aria-haspopup="menu"
        aria-controls={open ? menuId : undefined}
        onClick={() => setOpen((v) => !v)}
      >
        {busy ? <Spinner className="h-3.5 w-3.5" /> : null}
        {label}
        <svg
          width="12"
          height="12"
          viewBox="0 0 12 12"
          fill="none"
          aria-hidden
          className={`shrink-0 opacity-70 transition-transform ${open ? "rotate-180" : ""}`}
        >
          <path d="M3 4.5 6 7.5 9 4.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </button>
      {open ? (
        <div
          id={menuId}
          role="menu"
          aria-label="Template format"
          className={`absolute top-full z-30 mt-1.5 min-w-[13.5rem] rounded-xl border border-stone-200 bg-white py-1 shadow-lg dark:border-stone-700 dark:bg-stone-900 ${
            align === "right" ? "right-0" : "left-0"
          }`}
        >
          {OPTIONS.map((opt) => (
            <button
              key={opt.kind}
              type="button"
              role="menuitem"
              className="flex w-full flex-col px-3 py-2 text-left hover:bg-stone-50 focus:bg-stone-50 focus:outline-none dark:hover:bg-stone-800 dark:focus:bg-stone-800"
              onClick={() => pick(opt.kind)}
            >
              <span className="text-sm font-medium text-stone-800 dark:text-stone-100">{opt.label}</span>
              <span className="text-[11px] text-stone-500 dark:text-stone-400">{opt.hint}</span>
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}
