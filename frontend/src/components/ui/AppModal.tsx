import { useEffect, type ReactNode } from "react";
import { createPortal } from "react-dom";

type AppModalProps = {
  /** Element id referenced by aria-labelledby */
  titleId: string;
  eyebrow?: string;
  title: ReactNode;
  description?: ReactNode;
  onClose: () => void;
  children: ReactNode;
  footer?: ReactNode;
  /** Tailwind max-width class; default matches Investigate evidence modal */
  maxWidthClass?: string;
  /** When true, backdrop click and Escape do not close (e.g. busy save) */
  preventClose?: boolean;
};

/**
 * Shared large dialog shell — same overlay, sizing, Escape / body-scroll lock,
 * and close affordance as EvidenceInvestigateModal / Admin EditUserModal.
 */
export function AppModal({
  titleId,
  eyebrow,
  title,
  description,
  onClose,
  children,
  footer,
  maxWidthClass = "max-w-4xl",
  preventClose = false,
}: AppModalProps) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !preventClose) onClose();
    };
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    window.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = prevOverflow;
      window.removeEventListener("keydown", onKey);
    };
  }, [onClose, preventClose]);

  const dialog = (
    <div
      className="fixed inset-0 z-[100] flex items-end justify-center bg-stone-950/50 p-0 sm:items-center sm:p-6"
      role="dialog"
      aria-modal="true"
      aria-labelledby={titleId}
      onClick={() => {
        if (!preventClose) onClose();
      }}
    >
      <div
        className={`flex max-h-[92vh] w-full ${maxWidthClass} flex-col overflow-hidden rounded-t-2xl border border-stone-200 bg-white shadow-xl dark:border-stone-700 dark:bg-stone-900 sm:rounded-2xl`}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-3 border-b border-stone-100 bg-gradient-to-r from-brand-50/80 to-transparent px-5 py-4 dark:border-stone-800 dark:bg-stone-900 dark:bg-none">
          <div className="min-w-0">
            {eyebrow ? (
              <p className="text-xs font-semibold uppercase tracking-wide text-brand-700 dark:text-brand-300">
                {eyebrow}
              </p>
            ) : null}
            <h3
              id={titleId}
              className={`${eyebrow ? "mt-0.5" : ""} font-display text-lg font-bold text-stone-900 dark:text-stone-50`}
            >
              {title}
            </h3>
            {description ? (
              <div className="mt-1 text-sm text-stone-600 dark:text-stone-400">{description}</div>
            ) : null}
          </div>
          <button
            type="button"
            className="btn-ghost shrink-0 text-sm"
            onClick={onClose}
            disabled={preventClose}
          >
            Close
          </button>
        </div>

        <div className="min-h-0 flex-1 space-y-4 overflow-y-auto p-5">{children}</div>

        {footer ? (
          <div className="flex flex-wrap items-center justify-end gap-2 border-t border-stone-100 px-5 py-3 dark:border-stone-800">
            {footer}
          </div>
        ) : null}
      </div>
    </div>
  );

  return createPortal(dialog, document.body);
}
