import { FormEvent, useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { ApiError } from "@/api/client";
import { BrandWordmark } from "@/components/BrandWordmark";
import { useAuth } from "@/context/AuthContext";

export function LoginPage() {
  const { login, connecting } = useAuth();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const next = params.get("next") || "/upload";
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [loginAttempt, setLoginAttempt] = useState(0);
  const [loginElapsedSec, setLoginElapsedSec] = useState(0);

  useEffect(() => {
    if (!busy) {
      setLoginElapsedSec(0);
      return;
    }
    const started = Date.now();
    const id = window.setInterval(() => {
      setLoginElapsedSec(Math.floor((Date.now() - started) / 1000));
    }, 500);
    return () => window.clearInterval(id);
  }, [busy]);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setLoginAttempt(0);
    try {
      await login(email.trim(), password, (p) => setLoginAttempt(p.attempt));
      navigate(next.startsWith("/") ? next : "/upload");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not log in.");
    } finally {
      setBusy(false);
    }
  };

  const showSlowHint = busy && (loginAttempt > 1 || loginElapsedSec >= 3 || connecting);

  return (
    <div className="tool-enter mx-auto max-w-md py-10">
      <BrandWordmark variant="inline" className="mb-6 text-sm" />
      <h1 className="font-display text-2xl font-semibold text-stone-900 dark:text-stone-50">Log in</h1>
      <p className="mt-2 text-sm text-stone-500 dark:text-stone-400">
        Continue to upload files, download templates, or open algorithm docs.
      </p>
      <form onSubmit={onSubmit} className="mt-8 space-y-4">
        <div>
          <label className="label" htmlFor="email">
            Email
          </label>
          <input
            id="email"
            className="input"
            type="text"
            inputMode="email"
            autoComplete="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </div>
        <div>
          <label className="label" htmlFor="password">
            Password
          </label>
          <input
            id="password"
            className="input"
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </div>
        {error ? <p className="text-sm text-rose-600 dark:text-rose-400">{error}</p> : null}
        <button type="submit" className="btn-primary w-full" disabled={busy}>
          {busy
            ? loginAttempt > 1
              ? `Waking API… (${loginAttempt})`
              : "Signing in…"
            : "Log in"}
        </button>
        {showSlowHint ? (
          <p className="text-center text-xs text-stone-500 dark:text-stone-400">
            {loginAttempt > 1
              ? "Free-tier API may be waking from sleep — this can take up to a couple of minutes."
              : "Still signing in… retries automatically if the network drops."}
          </p>
        ) : null}
      </form>
      <p className="mt-6 text-sm text-stone-500">
        No account?{" "}
        <Link to={`/signup?next=${encodeURIComponent(next)}`} className="font-medium text-brand-700 hover:underline dark:text-brand-400">
          Sign up
        </Link>
        {" · "}
        <Link to="/forgot-password" className="font-medium text-brand-700 hover:underline dark:text-brand-400">
          Forgot password
        </Link>
      </p>
      <p className="mt-4 text-sm text-stone-500 dark:text-stone-400">
        Want to try first?{" "}
        <Link to="/#demo" className="font-medium text-brand-700 hover:underline dark:text-brand-400">
          Run the demo
        </Link>
        {" — "}
        no account required.
      </p>
    </div>
  );
}
