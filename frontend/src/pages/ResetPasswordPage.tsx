import { FormEvent, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { ApiError, authApi } from "@/api/client";
import { BrandWordmark } from "@/components/BrandWordmark";

export function ResetPasswordPage() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const token = params.get("token") || "";
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!token) {
      setError("Missing reset token.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await authApi.resetPassword(token, password);
      navigate("/login");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Reset failed.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="tool-enter mx-auto max-w-md py-10">
      <BrandWordmark variant="inline" className="mb-6 text-sm" />
      <h1 className="font-display text-2xl font-semibold">Choose a new password</h1>
      <form onSubmit={onSubmit} className="mt-8 space-y-4">
        <div>
          <label className="label" htmlFor="password">
            New password
          </label>
          <input
            id="password"
            className="input"
            type="password"
            required
            minLength={8}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </div>
        {error ? <p className="text-sm text-rose-600">{error}</p> : null}
        <button type="submit" className="btn-primary w-full" disabled={busy || !token}>
          {busy ? "Saving…" : "Update password"}
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
