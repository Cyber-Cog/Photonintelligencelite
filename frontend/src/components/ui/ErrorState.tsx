export function ErrorState({ title, message, hint }: { title: string; message: string; hint?: string }) {
  return (
    <div className="card border-rose-200 bg-rose-50 p-6 dark:border-rose-900/60 dark:bg-rose-950/30">
      <h3 className="text-sm font-semibold text-rose-800 dark:text-rose-300">{title}</h3>
      <p className="mt-1 text-sm text-rose-700 dark:text-rose-400">{message}</p>
      {hint && <p className="mt-2 text-xs text-rose-600/80 dark:text-rose-400/70">{hint}</p>}
    </div>
  );
}
