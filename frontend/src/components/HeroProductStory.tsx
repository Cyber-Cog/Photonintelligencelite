/**
 * Hero demo: teaches the product in three beats —
 * SCADA signal → fault band → loss bridge (Expected / losses / Actual).
 */
export function HeroProductStory() {
  return (
    <div
      className="landing-story relative w-full overflow-hidden rounded-2xl border border-stone-200/80 bg-white/75 p-4 shadow-sm backdrop-blur-sm dark:border-stone-700/60 dark:bg-stone-900/55 sm:p-5"
      role="img"
      aria-label="Product story: SCADA expected versus actual, a fault band appears, then a loss bridge from Expected through losses to Actual"
    >
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <p className="font-display text-xs font-semibold tracking-[0.12em] text-stone-500 uppercase">
          How PIC Lite reads a plant
        </p>
        <div className="landing-story-phases flex items-center gap-1.5 text-[10px] font-semibold tracking-wide uppercase">
          <span className="landing-story-phase landing-story-phase-1 rounded-full px-2 py-0.5">Signal</span>
          <span className="text-stone-300 dark:text-stone-600" aria-hidden>
            →
          </span>
          <span className="landing-story-phase landing-story-phase-2 rounded-full px-2 py-0.5">Fault</span>
          <span className="text-stone-300 dark:text-stone-600" aria-hidden>
            →
          </span>
          <span className="landing-story-phase landing-story-phase-3 rounded-full px-2 py-0.5">Loss</span>
        </div>
      </div>

      {/* Beat 1–2: expected vs actual + fault band */}
      <div className="relative">
        <div className="mb-1.5 flex flex-wrap items-center gap-3 text-[10px] text-stone-500">
          <span className="inline-flex items-center gap-1">
            <span className="h-0.5 w-3 rounded bg-brand-500" aria-hidden /> Expected
          </span>
          <span className="inline-flex items-center gap-1">
            <span className="h-0.5 w-3 rounded bg-accent-500" aria-hidden /> Actual
          </span>
          <span className="inline-flex items-center gap-1">
            <span className="h-2 w-2 rounded-sm bg-rose-500/50" aria-hidden /> Fault window
          </span>
        </div>

        <svg viewBox="0 0 420 150" className="h-auto w-full" aria-hidden>
          <defs>
            <linearGradient id="storyExpected" x1="0" y1="0" x2="1" y2="0">
              <stop offset="0%" stopColor="#f59e0b" stopOpacity="0.15" />
              <stop offset="40%" stopColor="#f59e0b" stopOpacity="0.95" />
              <stop offset="100%" stopColor="#d97706" stopOpacity="0.7" />
            </linearGradient>
            <linearGradient id="storyActual" x1="0" y1="0" x2="1" y2="0">
              <stop offset="0%" stopColor="#10b981" stopOpacity="0.15" />
              <stop offset="50%" stopColor="#10b981" stopOpacity="0.95" />
              <stop offset="100%" stopColor="#059669" stopOpacity="0.7" />
            </linearGradient>
          </defs>

          {[30, 60, 90, 120].map((y) => (
            <line key={y} x1="24" y1={y} x2="400" y2={y} stroke="#a8a29e" strokeOpacity="0.15" strokeWidth="1" />
          ))}

          <rect
            className="landing-story-fault-band"
            x="168"
            y="18"
            width="78"
            height="114"
            rx="4"
            fill="#f43f5e"
            opacity="0"
          />

          <path
            className="landing-story-line-expected"
            d="M28 118 C 70 110, 95 48, 140 42 S 210 38, 250 44 S 320 70, 360 55 S 395 48, 400 52"
            fill="none"
            stroke="url(#storyExpected)"
            strokeWidth="2.5"
            strokeLinecap="round"
          />

          <path
            className="landing-story-line-actual"
            d="M28 122 C 70 114, 95 55, 140 50 S 175 52, 190 88 S 230 95, 250 58 S 320 78, 360 62 S 395 55, 400 58"
            fill="none"
            stroke="url(#storyActual)"
            strokeWidth="2.5"
            strokeLinecap="round"
          />

          <text x="28" y="16" className="fill-stone-400" fontSize="9" fontFamily="DM Sans, sans-serif">
            INV-03 · AC power
          </text>
        </svg>
      </div>

      {/* Beat 3: loss bridge Expected → losses → Actual */}
      <div className="mt-4 border-t border-stone-200/80 pt-3 dark:border-stone-700/60">
        <div className="mb-2 flex items-baseline justify-between gap-2">
          <p className="text-[11px] font-semibold text-stone-600 dark:text-stone-300">Energy loss bridge</p>
          <p className="landing-story-loss-total font-display text-sm font-bold tabular-nums text-rose-600 dark:text-rose-400">
            −142 kWh
          </p>
        </div>
        <div className="flex h-[4.25rem] items-end gap-1.5 sm:gap-2">
          <div className="flex flex-[1.15] flex-col items-center gap-1">
            <div className="landing-story-bar landing-story-bar-expected w-full rounded-t-md bg-brand-500" />
            <span className="text-[9px] font-medium text-stone-500">Expected</span>
          </div>
          <div className="flex flex-1 flex-col items-center gap-1">
            <div className="landing-story-bar landing-story-bar-loss landing-story-bar-loss-a w-full rounded-t-md bg-rose-400/90" />
            <span className="text-[9px] font-medium text-stone-500">Clip</span>
          </div>
          <div className="flex flex-1 flex-col items-center gap-1">
            <div className="landing-story-bar landing-story-bar-loss landing-story-bar-loss-b w-full rounded-t-md bg-rose-600/85" />
            <span className="text-[9px] font-medium text-stone-500">DS</span>
          </div>
          <div className="flex flex-[1.15] flex-col items-center gap-1">
            <div className="landing-story-bar landing-story-bar-actual w-full rounded-t-md bg-accent-500" />
            <span className="text-[9px] font-medium text-stone-500">Actual</span>
          </div>
        </div>
        <p className="mt-2 text-[10px] leading-relaxed text-stone-500">
          SCADA expected vs actual, a confirmed fault window, then losses bridged into the energy gap.
        </p>
      </div>
    </div>
  );
}
