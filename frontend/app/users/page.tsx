"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { UserOut } from "@/lib/types";

const inputCls =
  "min-h-[44px] w-full rounded-lg border border-slate-700 bg-slate-900 px-3 text-sm text-slate-100";
const btnCls =
  "min-h-[44px] rounded-lg px-4 text-sm font-medium disabled:opacity-50";

function RoleBadge({ user }: { user: UserOut }) {
  return user.is_admin ? (
    <span className="rounded-md border border-emerald-500/30 bg-emerald-500/15 px-2 py-0.5 text-xs font-semibold text-emerald-300">
      admin
    </span>
  ) : (
    <span className="rounded-md border border-slate-600 bg-slate-700/40 px-2 py-0.5 text-xs font-semibold text-slate-300">
      member
    </span>
  );
}

function StatusBadge({ user }: { user: UserOut }) {
  return user.is_active ? (
    <span className="text-xs text-emerald-400">active</span>
  ) : (
    <span className="text-xs text-red-400">disabled</span>
  );
}

export default function UsersPage() {
  const { isAdmin, ready, user: me } = useAuth();
  const [users, setUsers] = useState<UserOut[]>([]);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [makeAdmin, setMakeAdmin] = useState(false);

  const [resetFor, setResetFor] = useState<number | null>(null);
  const [newPassword, setNewPassword] = useState("");

  const load = useCallback(async () => {
    try {
      setUsers(await api.listUsers());
      setError("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load users");
    }
  }, []);

  useEffect(() => {
    if (isAdmin) void load();
  }, [isAdmin, load]);

  async function act(fn: () => Promise<unknown>, ok: string) {
    setBusy(true);
    setNotice("");
    try {
      await fn();
      setNotice(ok);
      await load();
    } catch (e) {
      setNotice(e instanceof Error ? e.message : "Action failed");
    } finally {
      setBusy(false);
    }
  }

  async function addUser(e: React.FormEvent) {
    e.preventDefault();
    if (username.trim().length < 3) {
      setNotice("Username must be at least 3 characters.");
      return;
    }
    if (password.length < 8) {
      setNotice("Password must be at least 8 characters.");
      return;
    }
    await act(async () => {
      await api.createUser({ username: username.trim(), password, is_admin: makeAdmin });
      setUsername("");
      setPassword("");
      setMakeAdmin(false);
    }, `Added ${username.trim()}. They can now sign in and see live signals.`);
  }

  if (!ready) return <p className="text-sm text-slate-400">Loading…</p>;

  if (!isAdmin) {
    return (
      <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-4 text-sm text-slate-400">
        <p className="font-semibold text-slate-200">Administrator access required</p>
        <p className="mt-1 text-xs">
          Sign in with an administrator account to add or manage authorized users.
        </p>
      </div>
    );
  }

  const adminCount = users.filter((u) => u.is_admin && u.is_active).length;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold sm:text-2xl">Authorized users</h1>
        <p className="text-sm text-slate-400">
          Accounts that can sign in and see live signals. Visitors who are not signed in only ever
          see the synthetic demo dataset.
        </p>
      </div>

      {/* Add a user */}
      <form onSubmit={addUser} className="rounded-xl border border-slate-800 bg-slate-900/60 p-4">
        <h2 className="text-sm font-semibold">Add a user</h2>
        <p className="mt-1 text-xs text-slate-400">
          Give them the username and password to sign in with. Admins can also manage users, API
          keys, data refreshes and the research agent.
        </p>
        <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-3">
          <label className="block">
            <span className="mb-1 block text-xs text-slate-400">Username</span>
            <input
              className={inputCls}
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="e.g. jsmith"
              autoComplete="off"
            />
          </label>
          <label className="block">
            <span className="mb-1 block text-xs text-slate-400">Password (8+ characters)</span>
            <input
              className={inputCls}
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
              autoComplete="new-password"
            />
          </label>
          <div className="flex items-end gap-3">
            <label className="flex min-h-[44px] flex-1 items-center gap-2 text-sm text-slate-300">
              <input
                type="checkbox"
                checked={makeAdmin}
                onChange={(e) => setMakeAdmin(e.target.checked)}
                className="h-4 w-4"
              />
              Administrator
            </label>
            <button
              type="submit"
              disabled={busy || !username.trim() || !password}
              className={`${btnCls} bg-emerald-600 text-white hover:bg-emerald-500`}
            >
              Add user
            </button>
          </div>
        </div>
        {notice && <p className="mt-3 text-xs text-sky-300">{notice}</p>}
      </form>

      {/* Existing users */}
      <div className="overflow-hidden rounded-xl border border-slate-800 bg-slate-900/60">
        <div className="flex items-center justify-between border-b border-slate-800 px-4 py-3">
          <h2 className="text-sm font-semibold">Accounts ({users.length})</h2>
          <span className="text-xs text-slate-500">{adminCount} active admin(s)</span>
        </div>

        {error && <p className="px-4 py-3 text-sm text-red-400">{error}</p>}

        <ul className="divide-y divide-slate-800">
          {users.map((u) => (
            <li key={u.id} className="space-y-3 px-4 py-4">
              <div className="flex flex-wrap items-center gap-3">
                <span className="font-semibold text-slate-100">{u.username}</span>
                <RoleBadge user={u} />
                <StatusBadge user={u} />
                {me?.id === u.id && <span className="text-xs text-slate-500">(you)</span>}

                <div className="ml-auto flex flex-wrap items-center gap-2">
                  <button
                    disabled={busy}
                    onClick={() =>
                      act(
                        () => api.updateUser(u.id, { is_active: !u.is_active }),
                        u.is_active ? `Disabled ${u.username}.` : `Re-enabled ${u.username}.`,
                      )
                    }
                    className={`${btnCls} border border-slate-700 text-slate-300 hover:bg-slate-800`}
                  >
                    {u.is_active ? "Disable" : "Enable"}
                  </button>
                  <button
                    disabled={busy}
                    onClick={() =>
                      act(
                        () => api.updateUser(u.id, { is_admin: !u.is_admin }),
                        u.is_admin ? `${u.username} is now a member.` : `${u.username} is now an admin.`,
                      )
                    }
                    className={`${btnCls} border border-slate-700 text-slate-300 hover:bg-slate-800`}
                  >
                    {u.is_admin ? "Make member" : "Make admin"}
                  </button>
                  <button
                    disabled={busy}
                    onClick={() => {
                      setResetFor(resetFor === u.id ? null : u.id);
                      setNewPassword("");
                    }}
                    className={`${btnCls} border border-slate-700 text-slate-300 hover:bg-slate-800`}
                  >
                    Reset password
                  </button>
                  <button
                    disabled={busy || me?.id === u.id}
                    title={me?.id === u.id ? "You cannot delete your own account" : undefined}
                    onClick={() =>
                      act(() => api.deleteUser(u.id), `Deleted ${u.username}.`)
                    }
                    className={`${btnCls} border border-red-500/40 text-red-300 hover:bg-red-500/10`}
                  >
                    Delete
                  </button>
                </div>
              </div>

              {resetFor === u.id && (
                <div className="flex flex-wrap items-end gap-2">
                  <label className="min-w-[220px] flex-1">
                    <span className="mb-1 block text-xs text-slate-400">
                      New password for {u.username} (8+ characters)
                    </span>
                    <input
                      className={inputCls}
                      type="password"
                      value={newPassword}
                      onChange={(e) => setNewPassword(e.target.value)}
                      autoComplete="new-password"
                    />
                  </label>
                  <button
                    disabled={busy || newPassword.length < 8}
                    onClick={() =>
                      act(async () => {
                        await api.updateUser(u.id, { password: newPassword });
                        setResetFor(null);
                        setNewPassword("");
                      }, `Password updated for ${u.username}.`)
                    }
                    className={`${btnCls} bg-slate-700 text-white hover:bg-slate-600`}
                  >
                    Save password
                  </button>
                </div>
              )}
            </li>
          ))}
        </ul>
      </div>

      <p className="text-xs text-slate-500">
        Safety rules: a username must be unique, you cannot delete your own account, and the last
        active administrator can never be demoted, disabled or deleted.
      </p>
    </div>
  );
}
