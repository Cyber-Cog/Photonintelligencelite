import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  ApiError,
  completeAnalysisTemplateUrl,
  completeAnalysisZipUrl,
  downloadAuthenticated,
} from "@/api/client";
import { DocsSectionExplorer, useActiveSection } from "@/components/DocsSectionExplorer";
import { AuthTeaser } from "@/components/RequireAuth";
import { ALGORITHM_DOCS } from "@/content/algorithms";
import { PageHeader } from "@/components/ui/PageHeader";
import { SectionPanel } from "@/components/ui/SectionPanel";

function DocsContent() {
  const sectionIds = useMemo(() => ALGORITHM_DOCS.map((d) => d.id), []);
  const { activeId, jumpTo } = useActiveSection(sectionIds);
  const [dlError, setDlError] = useState<string | null>(null);

  const download = async (kind: "excel" | "zip") => {
    setDlError(null);
    try {
      if (kind === "excel") {
        await downloadAuthenticated(completeAnalysisTemplateUrl(), "pic_lite_complete_analysis_pack.xlsx");
      } else {
        await downloadAuthenticated(completeAnalysisZipUrl(), "pic_lite_complete_analysis_pack.zip");
      }
    } catch (err) {
      setDlError(err instanceof ApiError ? err.message : "Download failed.");
    }
  };

  return (
    <div className="tool-enter">
      <PageHeader
        className="mb-5"
        eyebrow="Algorithms"
        title="Algorithm reference"
        description="Calculation logic, required inputs, outputs, and thresholds for each fault and KPI module. Download the Complete Analysis Pack for the preferred SCADA upload format that supports full module coverage."
        actions={
          <>
            <button type="button" className="btn-secondary text-xs" onClick={() => void download("excel")}>
              Download template
            </button>
            <button type="button" className="btn-ghost text-xs" onClick={() => void download("zip")}>
              Download CSV package
            </button>
            <Link to="/upload" className="btn-primary text-xs">
              Upload files
            </Link>
          </>
        }
      />
      {dlError ? <p className="mb-3 text-sm text-rose-600">{dlError}</p> : null}

      <div className="lg:grid lg:grid-cols-[15rem_minmax(0,1fr)] lg:gap-8 xl:grid-cols-[16rem_minmax(0,1fr)]">
        <aside className="mb-4 lg:mb-0">
          <div className="sticky top-20 rounded-2xl border border-stone-200/90 bg-white/90 p-3.5 shadow-sm shadow-stone-900/[0.04] backdrop-blur-md dark:border-stone-800 dark:bg-stone-950/90 dark:shadow-none lg:max-h-[calc(100vh-6rem)] lg:overflow-y-auto">
            <DocsSectionExplorer docs={ALGORITHM_DOCS} activeId={activeId} onJump={jumpTo} />
          </div>
        </aside>

        <div className="min-w-0 space-y-3.5">
          {ALGORITHM_DOCS.map((doc) => (
            <SectionPanel
              key={doc.id}
              id={doc.id}
              title={doc.title}
              description={`Version ${doc.version}`}
              accent="neutral"
              scrollMargin
              className={
                activeId === doc.id ? "ring-1 ring-brand-400/40 dark:ring-brand-500/35" : undefined
              }
            >
              <p className="text-sm leading-relaxed text-stone-600 dark:text-stone-400">{doc.summary}</p>

              <div className="mt-3.5 grid gap-3 sm:grid-cols-2">
                <div className="rounded-xl border border-stone-200/80 bg-stone-50/50 px-3 py-2.5 dark:border-stone-800 dark:bg-stone-950/40">
                  <p className="label">Required inputs</p>
                  <ul className="mt-1 list-inside list-disc text-sm text-stone-600 dark:text-stone-300">
                    {doc.inputs.map((x) => (
                      <li key={x}>{x}</li>
                    ))}
                  </ul>
                </div>
                <div className="rounded-xl border border-stone-200/80 bg-stone-50/50 px-3 py-2.5 dark:border-stone-800 dark:bg-stone-950/40">
                  <p className="label">Outputs</p>
                  <ul className="mt-1 list-inside list-disc text-sm text-stone-600 dark:text-stone-300">
                    {doc.outputs.map((x) => (
                      <li key={x}>{x}</li>
                    ))}
                  </ul>
                </div>
              </div>

              <div className="mt-3.5 rounded-xl border border-brand-200/60 bg-gradient-to-br from-brand-50/70 to-white px-3.5 py-2.5 dark:border-brand-700/45 dark:bg-stone-950/60 dark:bg-none">
                <p className="label text-brand-800 dark:text-brand-300">Core formula</p>
                <p className="font-mono text-sm text-stone-800 dark:text-stone-200">{doc.formula}</p>
              </div>

              <div className="mt-3.5">
                <p className="label">Calculation steps</p>
                <ol className="mt-1 list-inside list-decimal space-y-1 text-sm text-stone-600 dark:text-stone-300">
                  {doc.steps.map((s) => (
                    <li key={s}>{s}</li>
                  ))}
                </ol>
              </div>

              <div className="mt-3.5 border-t border-stone-200/80 pt-3 dark:border-stone-800">
                <p className="label">Key thresholds</p>
                <p className="text-sm text-stone-500 dark:text-stone-400">{doc.thresholds.join(" · ")}</p>
              </div>
            </SectionPanel>
          ))}
        </div>
      </div>
    </div>
  );
}

export function DocsPage() {
  return (
    <AuthTeaser
      title="Algorithm documentation is signed-in"
      body="Create a free account to read full module formulas, inputs, thresholds, and download the Complete Analysis Pack. The landing-page demo stays available without signing in."
    >
      <DocsContent />
    </AuthTeaser>
  );
}
