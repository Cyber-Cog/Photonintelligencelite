import { FormEvent, useState } from "react";
import { Link } from "react-router-dom";
import { ApiError, authApi } from "@/api/client";
import { BrandWordmark } from "@/components/BrandWordmark";

export function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [resetLink, setResetLink] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const res = await authApi.forgotPassword(email.trim());
      setMessage(res.message);
      setResetLink(res.reset_link || null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Request failed.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="tool-enter mx-auto max-w-md py-10">
      <BrandWordmark variant="inline" className="mb-6 text-sm" />
      <h1 className="font-display text-2xl font-semibold">Reset password</h1>
      <p className="mt-2 text-sm text-stone-500">Enter your account email. We will issue a reset link.</p>
      <form onSubmit={onSubmit} className="mt-8 space-y-4">
        <div>
          <label className="label" htmlFor="email">
            Email
          </label>
          <input
            id="email"
            className="input"
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </div>
        {error ? <p className="text-sm text-rose-600">{error}</p> : null}
        {message ? <p className="text-sm text-emerald-700">{message}</p> : null}
        {resetLink ? (
          <p className="break-all rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900 dark:border-amber-800/50 dark:bg-stone-900 dark:text-amber-100">
            DEV reset link:{" "}
            <a className="underline" href={resetLink}>
              {resetLink}
            </a>
          </p>
        ) : null}
        <button type="submit" className="btn-primary w-full" disabled={busy}>
          {busy ? "Sending…" : "Send reset link"}
        </button>
      </form>
      <p className="mt-6 text-sm">
        <Link to="/login" className="text-brand-700 hover:underline">
          Back to login
        </Link>
      </p>
    </div>
  );
}
