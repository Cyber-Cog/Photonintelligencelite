import type { ReactNode, RefObject } from "react";
import { JobNav } from "@/components/JobNav";

/**
 * Fill the Layout job main (header + footer already claimed).
 * Prefer flex fill over nested max-height calcs that create postage-stamp panes.
 */
export const JOB_VIEWPORT_SHELL = "h-full min-h-0 flex-1";

/**
 * One composition shell for Results / Raw data / Explorer / Architecture.
 * Nav + titlebar live in chrome; body is aside + main (or full-bleed children).
 *
 * `documentScroll`: Results mode — page scrolls as one document (no nested scroll prison).
 * Omit for locked tool panes (Explorer / Raw data) that fill the viewport.
 */
export function JobWorkspace({
  title,
  subtitle,
  actions,
  status,
  chromeExtra,
  aside,
  children,
  mainClassName = "",
  flushMain = false,
  documentScroll = false,
  hideJobNav = false,
  footer,
  className = "",
  titleTour,
  mainRef,
}: {
  title: string;
  subtitle?: ReactNode;
  actions?: ReactNode;
  /** Optional status chip (parse / mapping / ready). */
  status?: ReactNode;
  /** Sticky KPIs, mobile tabs, toolbars under the titlebar. */
  chromeExtra?: ReactNode;
  aside?: ReactNode;
  children: ReactNode;
  mainClassName?: string;
  /** Diagnostics / bridge: main pane manages its own overflow (locked viewport only). */
  flushMain?: boolean;
  /** Natural document scroll — use on Results so charts are not trapped. */
  documentScroll?: boolean;
  /** Hide top Results/Raw data/Architecture/Explorer tabs (Results uses sidebar Tools). */
  hideJobNav?: boolean;
  footer?: ReactNode;
  className?: string;
  titleTour?: string;
  mainRef?: RefObject<HTMLDivElement>;
}) {
  const shell = documentScroll ? "min-h-0 w-full flex-1" : JOB_VIEWPORT_SHELL;
  const rootOverflow = documentScroll ? "" : "overflow-hidden";

  return (
    <div className={`tool-enter flex ${shell} flex-col ${rootOverflow} ${className}`}>
      <div
        className={`job-workspace flex min-h-0 flex-1 flex-col ${
          documentScroll ? "job-workspace-document" : ""
        }`}
      >
        <header className="job-workspace-chrome">
          {!hideJobNav ? (
            <div className="job-workspace-nav">
              <JobNav />
            </div>
          ) : null}
          <div className="job-workspace-titlebar">
            <div className="min-w-0" {...(titleTour ? { "data-tour": titleTour } : {})}>
              <div className="flex flex-wrap items-center gap-2">
                <h2 className="job-workspace-title">{title}</h2>
                {status}
              </div>
              {subtitle ? <div className="job-workspace-subtitle">{subtitle}</div> : null}
            </div>
            {actions ? <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div> : null}
          </div>
          {chromeExtra}
        </header>

        {aside ? (
          <div className={`job-workspace-body ${documentScroll ? "job-workspace-body-document" : ""}`}>
            <aside className="job-workspace-aside" aria-label="Section navigation">
              {aside}
            </aside>
            <div
              ref={mainRef}
              className={`job-workspace-main ${
                documentScroll
                  ? "job-workspace-main-document"
                  : flushMain
                    ? "job-workspace-main-flush"
                    : ""
              } ${mainClassName}`}
              data-tour="results-main"
            >
              {children}
            </div>
          </div>
        ) : (
          <div
            ref={mainRef}
            className={`job-workspace-main min-h-0 flex-1 ${
              documentScroll
                ? "job-workspace-main-document"
                : flushMain
                  ? "job-workspace-main-flush"
                  : ""
            } ${mainClassName}`}
          >
            {children}
          </div>
        )}

        {footer ? (
          <div className="flex shrink-0 items-center justify-center border-t border-[color:var(--pic-border-subtle)] px-3 py-1.5">
            {footer}
          </div>
        ) : null}
      </div>
    </div>
  );
}

/** Compact status for job chrome (ready / needs data / parsing). */
export function JobStatusChip({
  tone = "neutral",
  children,
}: {
  tone?: "neutral" | "ok" | "warn";
  children: ReactNode;
}) {
  const cls =
    tone === "ok" ? "status-chip status-chip-ok" : tone === "warn" ? "status-chip status-chip-warn" : "status-chip";
  return <span className={cls}>{children}</span>;
}
