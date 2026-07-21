import { useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { ApiError, authApi } from "@/api/client";
import { BrandWordmark } from "@/components/BrandWordmark";
import { useAuth } from "@/context/AuthContext";

export function VerifyEmailPage() {
  const { user, refresh } = useAuth();
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const token = params.get("token");
  const next = params.get("next") || "/upload";
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [devLink, setDevLink] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    (async () => {
      setBusy(true);
      try {
        const res = await authApi.verifyEmail(token);
        if (!cancelled) {
          setMessage(res.message);
          await refresh();
          navigate(next.startsWith("/") ? next : "/upload");
        }
      } catch (err) {
        if (!cancelled) setError(err instanceof ApiError ? err.message : "Verification failed.");
      } finally {
        if (!cancelled) setBusy(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [token, navigate, next, refresh]);

  const resend = async () => {
    setBusy(true);
    setError(null);
    try {
      const res = await authApi.resendVerification();
      setMessage(res.message);
      if (res.verification_link) setDevLink(res.verification_link);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not resend.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="tool-enter mx-auto max-w-md py-10">
      <BrandWordmark variant="inline" className="mb-6 text-sm" />
      <h1 className="font-display text-2xl font-semibold text-stone-900 dark:text-stone-50">Verify email</h1>
      <p className="mt-2 text-sm text-stone-500 dark:text-stone-400">
        {user
          ? `Signed in as ${user.email}. Verify your email to unlock uploads and documentation.`
          : "Open the verification link from your email (or the DEV link shown at signup)."}
      </p>
      {busy && token ? <p className="mt-4 text-sm text-stone-500">Verifying…</p> : null}
      {message ? <p className="mt-4 text-sm text-emerald-700 dark:text-emerald-400">{message}</p> : null}
      {error ? <p className="mt-4 text-sm text-rose-600 dark:text-rose-400">{error}</p> : null}
      {devLink ? (
        <p className="mt-4 break-all rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900 dark:border-amber-800/50 dark:bg-stone-900 dark:text-amber-100">
          <a className="underline" href={devLink}>
            {devLink}
          </a>
        </p>
      ) : null}
      {user && !user.email_verified ? (
        <button type="button" className="btn-primary mt-6" onClick={resend} disabled={busy}>
          Resend verification
        </button>
      ) : null}
      <p className="mt-6 text-sm">
        <Link to="/" className="text-brand-700 hover:underline dark:text-brand-400">
          Back home
        </Link>
      </p>
    </div>
  );
}
