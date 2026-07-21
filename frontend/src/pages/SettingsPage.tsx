import { FormEvent, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ApiError } from "@/api/client";
import { RequireAuth } from "@/components/RequireAuth";
import { useAuth } from "@/context/AuthContext";
import { useDemoTour } from "@/context/DemoTourContext";
import { useJob } from "@/context/JobContext";

function SettingsForm() {
  const { user, updateProfile, changePassword } = useAuth();
  const { prepareReplay, tourDone } = useDemoTour();
  const { jobId } = useJob();
  const navigate = useNavigate();
  const [name, setName] = useState(user?.name || "");
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [tourBusy, setTourBusy] = useState(false);

  const saveProfile = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setMsg(null);
    try {
      await updateProfile(name.trim());
      setMsg("Profile updated.");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Update failed.");
    } finally {
      setBusy(false);
    }
  };

  const savePassword = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setMsg(null);
    try {
      await changePassword(currentPassword, newPassword);
      setCurrentPassword("");
      setNewPassword("");
      setMsg("Password changed.");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Password change failed.");
    } finally {
      setBusy(false);
    }
  };

  const replayTour = async () => {
    setTourBusy(true);
    setError(null);
    setMsg(null);
    try {
      if (jobId) {
        await prepareReplay(jobId);
        navigate(`/jobs/${jobId}/dashboard`);
        setMsg("Demo tour restarted.");
      } else {
        await prepareReplay(null);
        setMsg("Tour unlocked. Open a completed job or run the demo to walk through again.");
        navigate("/#demo");
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not reset the tour.");
    } finally {
      setTourBusy(false);
    }
  };

  return (
    <div className="tool-enter mx-auto max-w-lg space-y-10 py-6">
      <div>
        <h1 className="font-display text-2xl font-semibold text-stone-900 dark:text-stone-50">Profile settings</h1>
        <p className="mt-2 text-sm text-stone-500">Manage your display name and password.</p>
      </div>

      <form onSubmit={saveProfile} className="space-y-4">
        <div>
          <label className="label" htmlFor="email">
            Email
          </label>
          <input id="email" className="input" value={user?.email || ""} disabled />
        </div>
        <div>
          <label className="label" htmlFor="name">
            Name
          </label>
          <input id="name" className="input" value={name} onChange={(e) => setName(e.target.value)} required />
        </div>
        <button type="submit" className="btn-primary" disabled={busy}>
          Save profile
        </button>
      </form>

      <form onSubmit={savePassword} className="space-y-4 border-t border-stone-200 pt-8 dark:border-stone-800">
        <h2 className="font-display text-lg font-semibold">Change password</h2>
        <div>
          <label className="label" htmlFor="current">
            Current password
          </label>
          <input
            id="current"
            className="input"
            type="password"
            value={currentPassword}
            onChange={(e) => setCurrentPassword(e.target.value)}
            required
          />
        </div>
        <div>
          <label className="label" htmlFor="new">
            New password
          </label>
          <input
            id="new"
            className="input"
            type="password"
            minLength={8}
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
            required
          />
        </div>
        <button type="submit" className="btn-secondary" disabled={busy}>
          Update password
        </button>
      </form>

      <div className="space-y-3 border-t border-stone-200 pt-8 dark:border-stone-800">
        <h2 className="font-display text-lg font-semibold">Demo tour</h2>
        <p className="text-sm text-stone-500 dark:text-stone-400">
          {tourDone
            ? "You’ve completed the interactive walkthrough. Replay it anytime on a results workspace."
            : "The guided tour runs once after you start a demo — or you can launch it here."}
        </p>
        <button type="button" className="btn-secondary text-sm" onClick={() => void replayTour()} disabled={tourBusy}>
          {tourBusy ? "Starting…" : "Replay tour"}
        </button>
      </div>

      {msg ? <p className="text-sm text-emerald-700 dark:text-emerald-400">{msg}</p> : null}
      {error ? <p className="text-sm text-rose-600 dark:text-rose-400">{error}</p> : null}

      {user?.role === "superadmin" ? (
        <p className="text-sm">
          <Link to="/admin" className="text-brand-700 hover:underline dark:text-brand-400">
            Open superadmin console
          </Link>
        </p>
      ) : null}
    </div>
  );
}

export function SettingsPage() {
  return (
    <RequireAuth>
      <SettingsForm />
    </RequireAuth>
  );
}
