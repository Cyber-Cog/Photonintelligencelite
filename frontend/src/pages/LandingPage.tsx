import { useEffect, useRef, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import {
  ApiError,
  completeAnalysisTemplateUrl,
  completeAnalysisZipUrl,
  downloadAuthenticated,
  startDemo,
} from "@/api/client";
import { BrandWordmark, PRODUCT_NAME } from "@/components/BrandWordmark";
import { HeroProductStory } from "@/components/HeroProductStory";
import { Reveal } from "@/components/Reveal";
import { Spinner } from "@/components/ui/Spinner";
import { useAuth } from "@/context/AuthContext";
import { useDemoTour } from "@/context/DemoTourContext";
import { useJob } from "@/context/JobContext";

const JOURNEY = [
  {
    step: "01",
    title: "Upload",
    body: "Use the Complete Analysis template for full coverage, or upload your own SCADA and map columns in Setup.",
  },
  {
    step: "02",
    title: "Configure",
    body: "Confirm columns, ratings, and architecture so every signal sits in the right place.",
  },
  {
    step: "03",
    title: "Diagnose",
    body: "Fault findings, loss quantification, and charts operators can defend in the field.",
  },
] as const;

const PROOF = [
  {
    title: "Evidence charts",
    body: "Reference versus actual with fault intervals marked for review.",
    visual: "chart" as const,
  },
  {
    title: "Plant KPIs",
    body: "Performance ratio, yield, availability, and a clear loss bridge.",
    visual: "kpi" as const,
  },
  {
    title: "Operator report",
    body: "A concise pack of findings ready to share with the site team.",
    visual: "report" as const,
  },
] as const;

function ProofGlyph({ kind }: { kind: (typeof PROOF)[number]["visual"] }) {
  if (kind === "chart") {
    return (
      <svg viewBox="0 0 160 72" className="h-16 w-full text-brand-500" aria-hidden>
        <rect className="landing-proof-fault" x="72" y="14" width="28" height="44" fill="#f43f5e" opacity="0.2" rx="2" />
        <path
          className="landing-draw"
          d="M8 52 C 28 48, 36 28, 52 34 S 78 58, 96 40 S 124 18, 152 22"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
        />
        <path
          d="M8 58 C 30 56, 40 44, 56 46 S 84 62, 100 50 S 128 36, 152 40"
          fill="none"
          stroke="#10b981"
          strokeWidth="2"
          strokeLinecap="round"
          opacity="0.75"
        />
      </svg>
    );
  }
  if (kind === "kpi") {
    return (
      <svg viewBox="0 0 160 72" className="h-16 w-full" aria-hidden>
        <rect className="landing-proof-bar" x="8" y="40" width="28" height="24" rx="3" fill="#f59e0b" opacity="0.85" />
        <rect className="landing-proof-bar landing-proof-bar-d1" x="44" y="28" width="28" height="36" rx="3" fill="#f43f5e" opacity="0.75" />
        <rect className="landing-proof-bar landing-proof-bar-d2" x="80" y="16" width="28" height="48" rx="3" fill="#10b981" opacity="0.75" />
        <rect className="landing-proof-bar landing-proof-bar-d3" x="116" y="34" width="28" height="30" rx="3" fill="#059669" opacity="0.55" />
      </svg>
    );
  }
  return (
    <svg viewBox="0 0 160 72" className="h-16 w-full" aria-hidden>
      <rect x="36" y="8" width="88" height="56" rx="4" fill="none" stroke="#78716c" strokeOpacity="0.35" strokeWidth="1.5" />
      <line className="landing-draw" x1="48" y1="24" x2="112" y2="24" stroke="#f59e0b" strokeWidth="2" strokeLinecap="round" />
      <line x1="48" y1="36" x2="100" y2="36" stroke="#a8a29e" strokeWidth="1.5" strokeLinecap="round" />
      <line x1="48" y1="46" x2="108" y2="46" stroke="#a8a29e" strokeWidth="1.5" strokeLinecap="round" />
      <line x1="48" y1="56" x2="88" y2="56" stroke="#10b981" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  );
}

export function LandingPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const { setJob } = useJob();
  const { user } = useAuth();
  const { armAfterDemo } = useDemoTour();
  const [demoLoading, setDemoLoading] = useState(false);
  const [demoError, setDemoError] = useState<string | null>(null);
  const [demoHighlight, setDemoHighlight] = useState(false);
  const demoButtonRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (location.hash !== "#demo") return;
    setDemoHighlight(true);
    const frame = window.requestAnimationFrame(() => {
      demoButtonRef.current?.scrollIntoView({ behavior: "smooth", block: "center" });
      demoButtonRef.current?.focus({ preventScroll: true });
    });
    const clear = window.setTimeout(() => setDemoHighlight(false), 2400);
    return () => {
      window.cancelAnimationFrame(frame);
      window.clearTimeout(clear);
    };
  }, [location.hash]);

  const goUpload = () => {
    if (!user) {
      navigate("/login?next=/upload");
      return;
    }
    navigate("/upload");
  };

  const goTemplate = async (kind: "excel" | "zip") => {
    if (!user) {
      navigate(`/login?next=${encodeURIComponent("/")}`);
      return;
    }
    try {
      if (kind === "excel") {
        await downloadAuthenticated(completeAnalysisTemplateUrl(), "pic_lite_complete_analysis_pack.xlsx");
      } else {
        await downloadAuthenticated(completeAnalysisZipUrl(), "pic_lite_complete_analysis_pack.zip");
      }
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        navigate(`/login?next=${encodeURIComponent("/")}`);
        return;
      }
      setDemoError(err instanceof ApiError ? err.message : "Download failed.");
    }
  };

  const handleDemo = async () => {
    setDemoLoading(true);
    setDemoError(null);
    try {
      const res = await startDemo();
      setJob(res.job_id, null);
      armAfterDemo(res.job_id);
      navigate(`/jobs/${res.job_id}/processing`);
    } catch (err) {
      setDemoError(err instanceof ApiError ? err.message : "Could not start the demo job. Try again.");
    } finally {
      setDemoLoading(false);
    }
  };

  return (
    <div className="flex w-full flex-col">
      {/* 1. Hook — brand + problem */}
      <section className="landing-hero relative isolate min-h-[calc(100vh-3.5rem)] overflow-hidden">
        <div className="landing-grid pointer-events-none absolute inset-0" aria-hidden />
        <div className="landing-haze pointer-events-none absolute -left-24 top-1/4 h-72 w-72 rounded-full bg-accent-500/15 blur-3xl" aria-hidden />
        <div className="landing-haze-slow pointer-events-none absolute -right-16 bottom-10 h-80 w-80 rounded-full bg-brand-400/20 blur-3xl" aria-hidden />

        <div className="relative mx-auto grid min-h-[calc(100vh-3.5rem)] max-w-6xl items-center gap-10 px-4 py-12 sm:px-6 lg:grid-cols-[1fr_1.05fr] lg:gap-12 lg:py-16">
          <div className="relative z-10 max-w-xl">
            <BrandWordmark variant="hero" />
            <p className="landing-enter landing-enter-delay-1 mt-5 text-lg font-medium leading-snug text-stone-800 dark:text-stone-100 sm:text-xl">
              Plant losses hide in SCADA noise.
            </p>
            <p className="landing-enter landing-enter-delay-2 mt-3 max-w-md text-base leading-relaxed text-stone-600 dark:text-stone-300">
              Utility-scale solar diagnostics that surface faults and put a number on the energy they cost.
            </p>

            <div id="demo" className="landing-enter landing-enter-delay-3 mt-9 flex flex-wrap items-center gap-3 scroll-mt-28">
              <button type="button" className="btn-primary landing-cta-btn px-5 py-2.5 text-sm" onClick={goUpload}>
                Upload files
              </button>
              <button
                ref={demoButtonRef}
                type="button"
                className={`btn-secondary landing-cta-btn px-5 py-2.5 text-sm ${
                  demoHighlight ? "ring-2 ring-brand-500 ring-offset-2 ring-offset-white dark:ring-offset-stone-950" : ""
                }`}
                onClick={handleDemo}
                disabled={demoLoading}
              >
                {demoLoading ? <Spinner className="h-4 w-4" /> : null}
                Run demo
              </button>
              <button type="button" className="btn-ghost landing-cta-btn px-4 py-2.5 text-sm" onClick={() => void goTemplate("excel")}>
                Download template
              </button>
            </div>
            {demoError ? <p className="mt-3 text-sm text-rose-600 dark:text-rose-400">{demoError}</p> : null}
          </div>

          <div className="landing-enter landing-enter-delay-4 relative z-10">
            <HeroProductStory />
          </div>
        </div>
      </section>

      {/* 2. Promise */}
      <section className="landing-promise relative overflow-hidden border-y border-stone-200/80 dark:border-stone-800">
        <div className="mx-auto max-w-6xl px-4 py-16 sm:px-6 sm:py-20">
          <Reveal>
            <p className="font-display text-xs font-semibold tracking-[0.18em] text-accent-700 dark:text-accent-400">
              The promise
            </p>
            <h2 className="mt-4 max-w-3xl font-display text-3xl font-semibold tracking-tight text-stone-900 dark:text-stone-50 sm:text-4xl sm:leading-tight">
              Find the fault. Quantify the loss. Hand operators evidence they can act on.
            </h2>
            <p className="mt-5 max-w-2xl text-base leading-relaxed text-stone-500 dark:text-stone-400">
              {PRODUCT_NAME} reads plant structure the way the site runs: inverters, SCBs, strings, and weather, then
              ties every finding back to measurable energy.
            </p>
          </Reveal>
        </div>
      </section>

      {/* 3. Journey */}
      <section className="relative mx-auto w-full max-w-6xl px-4 py-16 sm:px-6 sm:py-20">
        <Reveal>
          <p className="font-display text-xs font-semibold tracking-[0.18em] text-brand-700 dark:text-brand-400">
            The path
          </p>
          <h2 className="mt-3 font-display text-2xl font-semibold tracking-tight text-stone-900 dark:text-stone-50 sm:text-3xl">
            Upload. Configure. Diagnose.
          </h2>
          <p className="mt-2 max-w-xl text-sm leading-relaxed text-stone-500 dark:text-stone-400">
            Three beats from SCADA export to a decision-ready result.
          </p>
        </Reveal>

        <div className="landing-journey relative mt-12">
          <div className="landing-journey-line pointer-events-none absolute left-0 right-0 top-[1.15rem] hidden h-px sm:block" aria-hidden />
          <ol className="grid gap-10 sm:grid-cols-3 sm:gap-8">
            {JOURNEY.map((item, i) => (
              <li key={item.step}>
                <Reveal delayMs={80 + i * 90}>
                  <div className="flex items-center gap-3 sm:block">
                    <span className="landing-journey-node relative z-10 flex h-9 w-9 items-center justify-center rounded-full bg-stone-900 font-display text-xs font-bold text-brand-300 dark:bg-stone-100 dark:text-brand-800">
                      {item.step}
                    </span>
                    <h3 className="font-display text-xl font-semibold text-stone-900 dark:text-stone-50 sm:mt-5">
                      {item.title}
                    </h3>
                  </div>
                  <p className="mt-3 text-sm leading-relaxed text-stone-500 dark:text-stone-400">{item.body}</p>
                </Reveal>
              </li>
            ))}
          </ol>
        </div>
      </section>

      {/* 4. Proof */}
      <section className="landing-proof relative overflow-hidden">
        <div className="mx-auto max-w-6xl px-4 py-16 sm:px-6 sm:py-20">
          <Reveal>
            <p className="font-display text-xs font-semibold tracking-[0.18em] text-accent-700 dark:text-accent-400">
              What you get
            </p>
            <h2 className="mt-3 max-w-2xl font-display text-2xl font-semibold tracking-tight text-stone-900 dark:text-stone-50 sm:text-3xl">
              Evidence, KPIs, and a report that travels with the finding.
            </h2>
          </Reveal>

          <div className="mt-12 grid gap-12 lg:grid-cols-3 lg:gap-10">
            {PROOF.map((item, i) => (
              <Reveal key={item.title} delayMs={60 + i * 100}>
                <div className="border-t border-brand-500/40 pt-6">
                  <ProofGlyph kind={item.visual} />
                  <h3 className="mt-5 font-display text-lg font-semibold text-stone-900 dark:text-stone-50">
                    {item.title}
                  </h3>
                  <p className="mt-2 text-sm leading-relaxed text-stone-500 dark:text-stone-400">{item.body}</p>
                </div>
              </Reveal>
            ))}
          </div>

          <Reveal delayMs={120}>
            <p className="mt-12 text-sm text-stone-500 dark:text-stone-400">
              Need the formulas and thresholds?{" "}
              <Link to="/docs" className="font-semibold text-brand-700 hover:underline dark:text-brand-400">
                Open the documentation
              </Link>
              .
            </p>
          </Reveal>
        </div>
      </section>

      {/* 5. CTA */}
      <section className="landing-cta relative isolate overflow-hidden">
        <div className="landing-grid pointer-events-none absolute inset-0 opacity-60" aria-hidden />
        <div className="relative mx-auto max-w-6xl px-4 py-16 sm:px-6 sm:py-20">
          <Reveal>
            <h2 className="font-display text-3xl font-semibold tracking-tight text-stone-900 dark:text-stone-50 sm:text-4xl">
              Start with your plant data.
            </h2>
            <p className="mt-3 max-w-xl text-base leading-relaxed text-stone-600 dark:text-stone-300">
              Choose the recommended template or your own SCADA format, run the guided demo, or download the pack first.
            </p>

            <div className="mt-8 flex flex-wrap items-center gap-3">
              <button type="button" className="btn-primary landing-cta-btn px-5 py-2.5 text-sm" onClick={goUpload}>
                Upload files
              </button>
              <button
                type="button"
                className="btn-secondary landing-cta-btn px-5 py-2.5 text-sm"
                onClick={handleDemo}
                disabled={demoLoading}
              >
                {demoLoading ? <Spinner className="h-4 w-4" /> : null}
                Run demo
              </button>
              <button type="button" className="btn-secondary landing-cta-btn text-sm" onClick={() => void goTemplate("excel")}>
                Download template
              </button>
              <button type="button" className="btn-ghost landing-cta-btn text-sm" onClick={() => void goTemplate("zip")}>
                CSV package
              </button>
            </div>
            {demoError ? <p className="mt-3 text-sm text-rose-600 dark:text-rose-400">{demoError}</p> : null}
          </Reveal>
        </div>
      </section>
    </div>
  );
}
