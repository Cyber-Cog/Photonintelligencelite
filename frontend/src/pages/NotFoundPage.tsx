import { Link } from "react-router-dom";

export function NotFoundPage() {
  return (
    <div className="tool-enter flex flex-1 flex-col items-center justify-center gap-4 text-center">
      <p className="tool-eyebrow">404</p>
      <h1 className="font-display text-2xl font-semibold tracking-tight text-stone-900 dark:text-stone-50">
        Page not found
      </h1>
      <p className="text-sm text-stone-500 dark:text-stone-400">The page you're looking for doesn't exist or has expired.</p>
      <Link to="/" className="btn-primary">
        Back to home
      </Link>
    </div>
  );
}
