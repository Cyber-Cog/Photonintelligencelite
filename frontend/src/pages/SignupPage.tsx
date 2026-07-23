import { FormEvent, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { ApiError } from "@/api/client";
import { BrandWordmark } from "@/components/BrandWordmark";
import { useAuth } from "@/context/AuthContext";

export function SignupPage() {
  const { signup } = useAuth();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const next = params.get("next") || "/upload";
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [devLink, setDevLink] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setInfo(null);
    setDevLink(null);
    try {
      const res = await signup(email.trim(), password, name.trim());
      if (res.verificationLink) {
        setDevLink(res.verificationLink);
        setInfo(res.message || "Account created. Verify your email to continue.");
      } else {
        navigate(next.startsWith("/") ? next : "/upload");
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not sign up.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="tool-enter mx-auto max-w-md py-10">
      <BrandWordmark variant="inline" className="mb-6 text-sm" />
      <h1 className="font-display text-2xl font-semibold text-stone-900 dark:text-stone-50">Sign up</h1>
      <p className="mt-2 text-sm text-stone-500 dark:text-stone-400">
        Anyone can create an account with email and password.
      </p>
      <form onSubmit={onSubmit} className="mt-8 space-y-4">
        <div>
          <label className="label" htmlFor="name">
            Name
          </label>
          <input id="name" className="input" value={name} onChange={(e) => setName(e.target.value)} />
        </div>
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
            Password (min 8 characters)
          </label>
          <input
            id="password"
            className="input"
            type="password"
            autoComplete="new-password"
            required
            minLength={8}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </div>
        {error ? <p className="text-sm text-rose-600 dark:text-rose-400">{error}</p> : null}
        {info ? <p className="text-sm text-emerald-700 dark:text-emerald-400">{info}</p> : null}
        {devLink ? (
          <p className="break-all rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900 dark:border-amber-800/50 dark:bg-stone-900 dark:text-amber-100">
            DEV verification link:{" "}
            <a className="underline" href={devLink}>
              {devLink}
            </a>
          </p>
        ) : null}
        <button type="submit" className="btn-primary w-full" disabled={busy}>
          {busy ? "Creating…" : "Create account"}
        </button>
      </form>
      <p className="mt-6 text-sm text-stone-500">
        Already have an account?{" "}
        <Link to={`/login?next=${encodeURIComponent(next)}`} className="font-medium text-brand-700 hover:underline dark:text-brand-400">
          Log in
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
