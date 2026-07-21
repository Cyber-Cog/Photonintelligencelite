export function ProgressBar({ pct }: { pct: number }) {
  const clamped = Math.max(0, Math.min(100, pct));
  return (
    <div className="h-2 w-full overflow-hidden rounded-full bg-slate-200 dark:bg-slate-800">
      <div
        className="h-full rounded-full bg-brand-600 transition-all duration-300 dark:bg-brand-500"
        style={{ width: `${clamped}%` }}
      />
    </div>
  );
}
