import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { adminApi, ApiError } from "@/api/client";
import { RequireAuth } from "@/components/RequireAuth";
import { Badge } from "@/components/ui/Badge";
import { useAuth } from "@/context/AuthContext";
import type { AdminJob, AdminSession, AdminUser, AuditEvent, FunnelStats } from "@/types";

type EditDraft = { name: string; role: "user" | "superadmin" };

function EditUserModal({
  user,
  onClose,
  onSaved,
}: {
  user: AdminUser;
  onClose: () => void;
  onSaved: () => Promise<void>;
}) {
  const [draft, setDraft] = useState<EditDraft>({
    name: user.name || "",
    role: user.role === "superadmin" ? "superadmin" : "user",
  });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !busy) onClose();
    };
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    window.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = prev;
      window.removeEventListener("keydown", onKey);
    };
  }, [busy, onClose]);

  const save = async () => {
    setErr(null);
    const name = draft.name.trim();
    if (!name) {
      setErr("Display name is required.");
      return;
    }
    if (draft.role !== user.role) {
      const promoting = draft.role === "superadmin";
      const ok = window.confirm(
        promoting
          ? `Promote ${user.email} to superadmin? They will have full admin access.`
          : `Demote ${user.email} from superadmin to user? They will lose admin access.`,
      );
      if (!ok) return;
    }
    setBusy(true);
    try {
      const body: { name?: string; role?: "user" | "superadmin" } = {};
      if (name !== (user.name || "")) body.name = name;
      if (draft.role !== user.role) body.role = draft.role;
      if (Object.keys(body).length === 0) {
        onClose();
        return;
      }
      await adminApi.updateUser(user.id, body);
      await onSaved();
      onClose();
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Failed to update user.");
    } finally {
      setBusy(false);
    }
  };

  return createPortal(
    <div
      className="fixed inset-0 z-[100] flex items-end justify-center bg-stone-950/50 p-0 sm:items-center sm:p-6"
      role="dialog"
      aria-modal="true"
      aria-labelledby="edit-user-title"
      onClick={() => !busy && onClose()}
    >
      <div
        className="w-full max-w-md rounded-t-2xl border border-stone-200 bg-white p-5 shadow-xl dark:border-stone-700 dark:bg-stone-900 sm:rounded-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 id="edit-user-title" className="font-display text-lg font-semibold text-stone-900 dark:text-stone-50">
          Edit user
        </h2>
        <p className="mt-1 text-xs text-stone-500">{user.email}</p>

        <label className="mt-4 block text-xs font-semibold uppercase tracking-wide text-stone-400">
          Display name
          <input
            className="input mt-1 w-full"
            value={draft.name}
            onChange={(e) => setDraft((d) => ({ ...d, name: e.target.value }))}
            disabled={busy}
          />
        </label>

        <label className="mt-3 block text-xs font-semibold uppercase tracking-wide text-stone-400">
          Role
          <select
            className="input mt-1 w-full"
            value={draft.role}
            onChange={(e) => setDraft((d) => ({ ...d, role: e.target.value as "user" | "superadmin" }))}
            disabled={busy}
          >
            <option value="user">user</option>
            <option value="superadmin">superadmin</option>
          </select>
        </label>

        {err ? <p className="mt-3 text-sm text-rose-600">{err}</p> : null}

        <div className="mt-5 flex justify-end gap-2">
          <button type="button" className="btn-ghost text-xs" onClick={onClose} disabled={busy}>
            Cancel
          </button>
          <button type="button" className="btn-primary text-xs" onClick={() => void save()} disabled={busy}>
            {busy ? "Saving…" : "Save"}
          </button>
        </div>
      </div>
    </div>,
    document.body,
  );
}

function UserActions({
  user,
  isSelf,
  onChanged,
  onEdit,
}: {
  user: AdminUser;
  isSelf: boolean;
  onChanged: () => Promise<void>;
  onEdit: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  const run = async (fn: () => Promise<void>) => {
    setBusy(true);
    setMsg(null);
    try {
      await fn();
      await onChanged();
    } catch (e) {
      setMsg(e instanceof ApiError ? e.message : "Action failed.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex flex-col items-end gap-1">
      <div className="flex flex-wrap justify-end gap-1">
        <button type="button" className="btn-ghost px-2 py-1 text-[11px]" disabled={busy} onClick={onEdit}>
          Edit
        </button>
        <button
          type="button"
          className="btn-ghost px-2 py-1 text-[11px]"
          disabled={busy || isSelf}
          title={isSelf ? "You cannot ban yourself" : undefined}
          onClick={() => {
            const next = !user.is_active;
            const ok = window.confirm(
              next
                ? `Unban ${user.email}? They will be able to log in again.`
                : `Ban ${user.email}? They will be logged out and cannot sign in.`,
            );
            if (!ok) return;
            void run(async () => {
              await adminApi.updateUser(user.id, { is_active: next });
            });
          }}
        >
          {user.is_active ? "Ban" : "Unban"}
        </button>
        <button
          type="button"
          className="btn-ghost px-2 py-1 text-[11px] text-rose-600 dark:text-rose-400"
          disabled={busy || isSelf}
          title={isSelf ? "You cannot delete yourself" : undefined}
          onClick={() => {
            const ok = window.confirm(
              `Delete ${user.email}? This soft-deletes the account (cannot be undone from the UI).`,
            );
            if (!ok) return;
            void run(async () => {
              await adminApi.deleteUser(user.id);
            });
          }}
        >
          Delete
        </button>
      </div>
      <div className="flex flex-wrap justify-end gap-1">
        {!user.email_verified ? (
          <button
            type="button"
            className="btn-ghost px-2 py-1 text-[11px]"
            disabled={busy}
            onClick={() =>
              void run(async () => {
                await adminApi.forceVerify(user.id);
                setMsg("Verified.");
              })
            }
          >
            Force verify
          </button>
        ) : null}
        {user.is_active ? (
          <button
            type="button"
            className="btn-ghost px-2 py-1 text-[11px]"
            disabled={busy}
            onClick={() =>
              void run(async () => {
                const res = await adminApi.resendReset(user.id);
                setMsg(res.reset_link ? `Reset link: ${res.reset_link}` : res.message);
              })
            }
          >
            Reset link
          </button>
        ) : null}
      </div>
      {msg ? <p className="max-w-[220px] text-right text-[10px] text-stone-500 break-all">{msg}</p> : null}
    </div>
  );
}

function AdminConsole() {
  const { user: me } = useAuth();
  const [tab, setTab] = useState<"users" | "sessions" | "jobs" | "audit">("users");
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [sessions, setSessions] = useState<AdminSession[]>([]);
  const [jobs, setJobs] = useState<AdminJob[]>([]);
  const [audit, setAudit] = useState<AuditEvent[]>([]);
  const [funnel, setFunnel] = useState<FunnelStats | null>(null);
  const [q, setQ] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState<AdminUser | null>(null);

  const load = async () => {
    setError(null);
    try {
      const [u, s, j, f, a] = await Promise.all([
        adminApi.users(),
        adminApi.sessions(),
        adminApi.jobs(),
        adminApi.funnel(),
        adminApi.audit({ q: q || undefined, limit: 150 }),
      ]);
      setUsers(u);
      setSessions(s);
      setJobs(j);
      setFunnel(f);
      setAudit(a);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load admin data.");
    }
  };

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="tool-enter space-y-6 py-4">
      <div>
        <h1 className="font-display text-2xl font-semibold text-stone-900 dark:text-stone-50">Superadmin</h1>
        <p className="mt-1 text-sm text-stone-500">Users, sessions, job funnel, and audit log.</p>
      </div>

      {funnel ? (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-8">
          {(
            [
              ["Uploaded", funnel.uploaded],
              ["Mapping", funnel.mapping],
              ["Validating", funnel.validating],
              ["Running", funnel.queued_or_running],
              ["Completed", funnel.completed],
              ["Failed", funnel.failed],
              ["Abandoned", funnel.abandoned],
              ["Demo", funnel.demo],
            ] as const
          ).map(([label, n]) => (
            <div key={label} className="rounded-xl border border-stone-200 px-3 py-2 dark:border-stone-800">
              <p className="text-[10px] font-semibold uppercase tracking-wide text-stone-400">{label}</p>
              <p className="mt-1 font-display text-xl font-semibold">{n}</p>
            </div>
          ))}
        </div>
      ) : null}

      <div className="flex flex-wrap gap-2 border-b border-stone-200 pb-2 dark:border-stone-800">
        {(["users", "sessions", "jobs", "audit"] as const).map((t) => (
          <button
            key={t}
            type="button"
            className={tab === t ? "nav-tab-active" : "nav-tab"}
            onClick={() => setTab(t)}
          >
            {t}
          </button>
        ))}
        <button type="button" className="btn-ghost ml-auto text-xs" onClick={() => void load()}>
          Refresh
        </button>
      </div>

      {error ? <p className="text-sm text-rose-600">{error}</p> : null}

      {tab === "users" ? (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="text-xs uppercase text-stone-400">
              <tr>
                <th className="py-2 pr-3">Email</th>
                <th className="py-2 pr-3">Role</th>
                <th className="py-2 pr-3">Status</th>
                <th className="py-2 pr-3">Verified</th>
                <th className="py-2 pr-3">Jobs</th>
                <th className="py-2 pr-3">Created</th>
                <th className="py-2 text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {users.map((u) => (
                <tr key={u.id} className="border-t border-stone-100 dark:border-stone-900">
                  <td className="py-2 pr-3">
                    <div className="font-medium">{u.name || "—"}</div>
                    <div className="text-xs text-stone-500">{u.email}</div>
                  </td>
                  <td className="py-2 pr-3">{u.role}</td>
                  <td className="py-2 pr-3">
                    {u.is_active ? <Badge tone="success">Active</Badge> : <Badge tone="danger">Banned</Badge>}
                  </td>
                  <td className="py-2 pr-3">{u.email_verified ? "yes" : "no"}</td>
                  <td className="py-2 pr-3">{u.job_count}</td>
                  <td className="py-2 pr-3 text-xs text-stone-500">{u.created_at}</td>
                  <td className="py-2">
                    <UserActions
                      user={u}
                      isSelf={me?.id === u.id}
                      onChanged={load}
                      onEdit={() => setEditing(u)}
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}

      {tab === "sessions" ? (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="text-xs uppercase text-stone-400">
              <tr>
                <th className="py-2 pr-3">User</th>
                <th className="py-2 pr-3">IP</th>
                <th className="py-2 pr-3">Created</th>
                <th className="py-2">Status</th>
              </tr>
            </thead>
            <tbody>
              {sessions.map((s) => (
                <tr key={s.id} className="border-t border-stone-100 dark:border-stone-900">
                  <td className="py-2 pr-3">{s.user_email || s.user_id}</td>
                  <td className="py-2 pr-3">{s.ip || "—"}</td>
                  <td className="py-2 pr-3 text-xs">{s.created_at}</td>
                  <td className="py-2 text-xs">{s.revoked_at ? "revoked" : "active"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}

      {tab === "jobs" ? (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="text-xs uppercase text-stone-400">
              <tr>
                <th className="py-2 pr-3">Job</th>
                <th className="py-2 pr-3">State</th>
                <th className="py-2 pr-3">User</th>
                <th className="py-2">Flags</th>
              </tr>
            </thead>
            <tbody>
              {jobs.map((j) => (
                <tr key={j.id} className="border-t border-stone-100 dark:border-stone-900">
                  <td className="py-2 pr-3 font-mono text-xs">{j.id.slice(0, 8)}</td>
                  <td className="py-2 pr-3">{j.state}</td>
                  <td className="py-2 pr-3 text-xs">{j.user_email || "—"}</td>
                  <td className="py-2 text-xs">
                    {j.is_demo ? "demo " : ""}
                    {j.abandoned_at ? "abandoned" : ""}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}

      {tab === "audit" ? (
        <div className="space-y-3">
          <div className="flex gap-2">
            <input
              className="input max-w-xs"
              placeholder="Filter action…"
              value={q}
              onChange={(e) => setQ(e.target.value)}
            />
            <button type="button" className="btn-secondary text-xs" onClick={() => void load()}>
              Search
            </button>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="text-xs uppercase text-stone-400">
                <tr>
                  <th className="py-2 pr-3">When</th>
                  <th className="py-2 pr-3">Action</th>
                  <th className="py-2 pr-3">User</th>
                  <th className="py-2">Job / IP</th>
                </tr>
              </thead>
              <tbody>
                {audit.map((e) => (
                  <tr key={e.id} className="border-t border-stone-100 dark:border-stone-900">
                    <td className="py-2 pr-3 text-xs text-stone-500">{e.created_at}</td>
                    <td className="py-2 pr-3 font-medium">{e.action}</td>
                    <td className="py-2 pr-3 font-mono text-xs">{e.user_id?.slice(0, 8) || "—"}</td>
                    <td className="py-2 text-xs">
                      {e.job_id ? `job ${e.job_id.slice(0, 8)}` : ""} {e.ip || ""}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : null}

      {editing ? (
        <EditUserModal
          user={editing}
          onClose={() => setEditing(null)}
          onSaved={load}
        />
      ) : null}
    </div>
  );
}

export function AdminPage() {
  return (
    <RequireAuth requireSuperadmin>
      <AdminConsole />
    </RequireAuth>
  );
}
