"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";
import { useAuth } from "@/components/auth/AuthProvider";

type UserStatus = "active" | "paused" | string;
type UserRole = "admin" | "customer" | "user" | string;

type AdminUser = {
  id: string;
  email: string;
  role: UserRole;
  status: UserStatus;
  allowed_ip: string | null;
  created_at: string;
};

type UserListReply = { users: AdminUser[] };

const API_BASE_URL = (
  process.env.NEXT_PUBLIC_API_BASE_URL?.trim() ||
  (process.env.NODE_ENV === "development"
    ? "http://localhost:8000"
    : "https://allsafe-ai-api.onrender.com")
).replace(/\/+$/, "");

async function responseMessage(response: Response): Promise<string> {
  try {
    const body: unknown = await response.json();
    if (typeof body === "string") return body;
    if (typeof body === "object" && body !== null) {
      const record = body as Record<string, unknown>;
      for (const key of ["detail", "message", "error"]) {
        const value = record[key];
        if (typeof value === "string") return value;
        if (Array.isArray(value) && value.length > 0) {
          const first = value[0];
          if (typeof first === "object" && first !== null) {
            const message = (first as Record<string, unknown>).msg;
            if (typeof message === "string") return message;
          }
        }
      }
    }
  } catch {
    // Use the HTTP status below when the server response is not JSON.
  }
  return `The admin service returned HTTP ${response.status}.`;
}

async function adminRequest<T>(
  accessToken: string,
  path: string,
  options: { method?: "GET" | "POST" | "PATCH" | "DELETE"; body?: unknown } = {},
): Promise<T> {
  const hasBody = options.body !== undefined;
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: options.method ?? "GET",
    headers: {
      Accept: "application/json",
      Authorization: `Bearer ${accessToken}`,
      ...(hasBody ? { "Content-Type": "application/json" } : {}),
    },
    ...(hasBody ? { body: JSON.stringify(options.body) } : {}),
    cache: "no-store",
    credentials: "omit",
  });

  if (!response.ok) throw new Error(await responseMessage(response));
  if (response.status === 204) return {} as T;
  return response.json() as Promise<T>;
}

function isCustomer(user: AdminUser): boolean {
  return user.role === "customer" || user.role === "user";
}

function formatDate(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "—" : date.toLocaleDateString();
}

type UserActionsProps = {
  user: AdminUser;
  busy: boolean;
  onStatusChange: (user: AdminUser) => void;
  onAllowedIpChange: (user: AdminUser, allowedIp: string) => Promise<boolean>;
  onDelete: (user: AdminUser) => void;
};

function UserActions({ user, busy, onStatusChange, onAllowedIpChange, onDelete }: UserActionsProps) {
  const [editingIp, setEditingIp] = useState(false);
  const [allowedIp, setAllowedIp] = useState(user.allowed_ip ?? "");
  const customer = isCustomer(user);

  if (!customer) {
    return <span className="text-xs text-slate-500">Admin account protected</span>;
  }

  if (editingIp) {
    return (
      <form
        className="flex min-w-56 flex-wrap items-center gap-2"
        onSubmit={(event) => {
          event.preventDefault();
          void onAllowedIpChange(user, allowedIp.trim()).then((saved) => {
            if (saved) {
              setAllowedIp(allowedIp.trim());
              setEditingIp(false);
            }
          });
        }}
      >
        <label className="sr-only" htmlFor={`allowed-ip-${user.id}`}>Allowed public IP for {user.email}</label>
        <input
          id={`allowed-ip-${user.id}`}
          type="text"
          inputMode="text"
          autoComplete="off"
          required
          value={allowedIp}
          onChange={(event) => setAllowedIp(event.target.value)}
          placeholder="Customer public IPv4 or IPv6"
          className="min-w-0 flex-1 rounded-lg border border-white/10 bg-slate-950 px-3 py-2 text-xs text-white placeholder:text-slate-600 focus:border-emerald-400 focus:outline-none"
        />
        <button
          type="submit"
          disabled={busy || !allowedIp.trim()}
          className="rounded-lg bg-emerald-400 px-3 py-2 text-xs font-semibold text-slate-950 hover:bg-emerald-300 disabled:cursor-not-allowed disabled:opacity-50"
        >
          Save IP
        </button>
        <button
          type="button"
          disabled={busy}
          onClick={() => {
            setAllowedIp(user.allowed_ip ?? "");
            setEditingIp(false);
          }}
          className="rounded-lg border border-white/15 px-3 py-2 text-xs text-slate-300 hover:bg-white/5 disabled:opacity-50"
        >
          Cancel
        </button>
      </form>
    );
  }

  return (
    <div className="flex flex-wrap items-center gap-2">
      <button
        type="button"
        disabled={busy}
        onClick={() => {
          setAllowedIp(user.allowed_ip ?? "");
          setEditingIp(true);
        }}
        className="rounded-lg border border-white/15 px-3 py-2 text-xs font-medium text-slate-200 hover:bg-white/5 disabled:opacity-50"
      >
        Edit IP
      </button>
      {user.status === "active" || user.status === "paused" ? (
        <button
          type="button"
          disabled={busy}
          onClick={() => onStatusChange(user)}
          className="rounded-lg border border-amber-300/20 px-3 py-2 text-xs font-medium text-amber-200 hover:bg-amber-300/10 disabled:opacity-50"
        >
          {user.status === "active" ? "Pause login" : "Resume login"}
        </button>
      ) : null}
      <button
        type="button"
        disabled={busy}
        onClick={() => onDelete(user)}
        className="rounded-lg border border-rose-400/25 px-3 py-2 text-xs font-medium text-rose-200 hover:bg-rose-400/10 disabled:opacity-50"
      >
        Delete
      </button>
    </div>
  );
}

export default function AdminUsersPanel() {
  const { session, profile, loading: authLoading, signOut } = useAuth();
  const accessToken = session?.access_token;
  const isAdmin = profile?.role === "admin";

  const [users, setUsers] = useState<AdminUser[]>([]);
  const [loadingUsers, setLoadingUsers] = useState(false);
  const [busyUserId, setBusyUserId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<"all" | "active" | "paused">("all");
  const [createOpen, setCreateOpen] = useState(false);
  const [creating, setCreating] = useState(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [allowedIp, setAllowedIp] = useState("");
  const [deleteTarget, setDeleteTarget] = useState<AdminUser | null>(null);
  const [deleteConfirmation, setDeleteConfirmation] = useState("");

  const refreshUsers = useCallback(async () => {
    if (!accessToken || !isAdmin) return;
    setLoadingUsers(true);
    setError(null);
    try {
      const reply = await adminRequest<UserListReply>(accessToken, "/api/v1/admin/users");
      setUsers(Array.isArray(reply.users) ? reply.users : []);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not load user accounts.");
    } finally {
      setLoadingUsers(false);
    }
  }, [accessToken, isAdmin]);

  useEffect(() => {
    if (authLoading) return;
    const timer = window.setTimeout(() => {
      if (accessToken && isAdmin) {
        void refreshUsers();
      } else {
        setUsers([]);
        setLoadingUsers(false);
        setError(null);
      }
    }, 0);
    return () => window.clearTimeout(timer);
  }, [accessToken, authLoading, isAdmin, refreshUsers]);

  const visibleUsers = useMemo(() => {
    const query = search.trim().toLowerCase();
    return users.filter((user) => {
      const matchesStatus = statusFilter === "all" || user.status === statusFilter;
      const matchesSearch = !query || [user.email, user.allowed_ip ?? "", user.role]
        .some((value) => value.toLowerCase().includes(query));
      return matchesStatus && matchesSearch;
    });
  }, [search, statusFilter, users]);

  function clearNotices() {
    setError(null);
    setSuccess(null);
  }

  async function createUser(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!accessToken) return;
    setCreating(true);
    clearNotices();
    try {
      await adminRequest<unknown>(accessToken, "/api/v1/admin/users", {
        method: "POST",
        body: { email: email.trim(), password, allowed_ip: allowedIp.trim() },
      });
      setSuccess(`Created the account for ${email.trim()}.`);
      setEmail("");
      setPassword("");
      setAllowedIp("");
      setCreateOpen(false);
      await refreshUsers();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not create the account.");
    } finally {
      setCreating(false);
    }
  }

  async function changeStatus(user: AdminUser) {
    if (!accessToken || !isCustomer(user)) return;
    const status = user.status === "active" ? "paused" : "active";
    setBusyUserId(user.id);
    clearNotices();
    try {
      await adminRequest<unknown>(accessToken, `/api/v1/admin/users/${encodeURIComponent(user.id)}`, {
        method: "PATCH",
        body: { status },
      });
      setSuccess(`${user.email} login ${status === "paused" ? "paused" : "resumed"}.`);
      await refreshUsers();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not update the account status.");
    } finally {
      setBusyUserId(null);
    }
  }

  async function changeAllowedIp(user: AdminUser, nextAllowedIp: string): Promise<boolean> {
    if (!accessToken || !isCustomer(user) || !nextAllowedIp) return false;
    setBusyUserId(user.id);
    clearNotices();
    try {
      await adminRequest<unknown>(accessToken, `/api/v1/admin/users/${encodeURIComponent(user.id)}`, {
        method: "PATCH",
        body: { allowed_ip: nextAllowedIp },
      });
      setSuccess(`Allowed IP updated for ${user.email}.`);
      await refreshUsers();
      return true;
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not update the allowed IP.");
      return false;
    } finally {
      setBusyUserId(null);
    }
  }

  async function deleteUser() {
    if (!accessToken || !deleteTarget || !isCustomer(deleteTarget)) return;
    if (deleteConfirmation.trim().toLowerCase() !== deleteTarget.email.trim().toLowerCase()) return;
    setBusyUserId(deleteTarget.id);
    clearNotices();
    try {
      await adminRequest<unknown>(
        accessToken,
        `/api/v1/admin/users/${encodeURIComponent(deleteTarget.id)}`,
        { method: "DELETE" },
      );
      setSuccess(`Deleted the account for ${deleteTarget.email}.`);
      setUsers((current) => current.filter((user) => user.id !== deleteTarget.id));
      setDeleteTarget(null);
      setDeleteConfirmation("");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not delete the account.");
    } finally {
      setBusyUserId(null);
    }
  }

  if (authLoading) {
    return (
      <section aria-live="polite" className="py-16 text-center text-sm text-slate-400">
        Checking your administrator access…
      </section>
    );
  }

  if (!session || !profile) {
    return (
      <section className="mx-auto mt-10 max-w-xl rounded-2xl border border-white/10 bg-white/[0.025] p-6 sm:p-8">
        <p className="text-xs font-medium uppercase tracking-widest text-emerald-400">Sign in required</p>
        <h1 className="mt-2 text-2xl font-semibold tracking-tight text-white">Admin access</h1>
        <p className="mt-3 text-sm leading-relaxed text-slate-300">Sign in with an administrator account to manage customer access.</p>
        <Link href="/login" className="mt-5 inline-flex rounded-lg bg-emerald-400 px-4 py-2.5 text-sm font-semibold text-slate-950 hover:bg-emerald-300">
          Go to sign in
        </Link>
      </section>
    );
  }

  if (!isAdmin) {
    return (
      <section className="mx-auto mt-10 max-w-xl rounded-2xl border border-rose-400/20 bg-rose-400/5 p-6 sm:p-8">
        <p className="text-xs font-medium uppercase tracking-widest text-rose-200">Access denied</p>
        <h1 className="mt-2 text-2xl font-semibold tracking-tight text-white">Administrator account required</h1>
        <p className="mt-3 text-sm leading-relaxed text-slate-300">This account does not have access to the admin portal.</p>
        <button type="button" onClick={() => void signOut()} className="mt-5 rounded-lg border border-white/15 px-4 py-2.5 text-sm font-medium text-white hover:bg-white/5">
          Sign out
        </button>
      </section>
    );
  }

  const renderActions = (user: AdminUser) => (
    <UserActions
      key={user.id}
      user={user}
      busy={busyUserId === user.id}
      onStatusChange={changeStatus}
      onAllowedIpChange={changeAllowedIp}
      onDelete={(target) => {
        clearNotices();
        setDeleteConfirmation("");
        setDeleteTarget(target);
      }}
    />
  );

  return (
    <div className="pb-12 pt-8">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-xs font-medium uppercase tracking-widest text-emerald-400">User management</p>
          <h1 className="mt-2 text-3xl font-bold tracking-tight text-white sm:text-4xl">Customers</h1>
          <p className="mt-2 max-w-2xl text-sm leading-relaxed text-slate-300">Create customer logins, control access, and manage each account’s allowed public IP.</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button type="button" onClick={() => void refreshUsers()} disabled={loadingUsers} className="rounded-lg border border-white/15 px-4 py-2.5 text-sm font-medium text-slate-200 hover:bg-white/5 disabled:opacity-50">
            {loadingUsers ? "Refreshing…" : "Refresh list"}
          </button>
          <button type="button" onClick={() => { clearNotices(); setCreateOpen((open) => !open); }} className="rounded-lg bg-emerald-400 px-4 py-2.5 text-sm font-semibold text-slate-950 hover:bg-emerald-300">
            {createOpen ? "Close form" : "Create customer"}
          </button>
          <button type="button" onClick={() => void signOut()} className="rounded-lg border border-white/15 px-4 py-2.5 text-sm font-medium text-slate-200 hover:bg-white/5">
            Sign out
          </button>
        </div>
      </div>

      {createOpen && (
        <section aria-labelledby="create-customer-title" className="mt-7 rounded-2xl border border-emerald-400/15 bg-emerald-400/[0.035] p-5 sm:p-6">
          <h2 id="create-customer-title" className="text-lg font-semibold text-white">Create a customer login</h2>
          <p className="mt-1 text-sm text-slate-400">The email is the customer’s sign-in username. Share the initial password with them securely.</p>
          <form onSubmit={createUser} className="mt-5 grid gap-4 md:grid-cols-3">
            <label className="text-sm text-slate-300">
              Email / username
              <input type="email" required autoComplete="off" value={email} onChange={(event) => setEmail(event.target.value)} className="mt-1 block w-full rounded-lg border border-white/10 bg-slate-950 px-3 py-2.5 text-sm text-white placeholder:text-slate-600 focus:border-emerald-400 focus:outline-none" placeholder="customer@example.com" />
            </label>
            <label className="text-sm text-slate-300">
              Initial password
              <input type="password" required minLength={8} autoComplete="new-password" value={password} onChange={(event) => setPassword(event.target.value)} className="mt-1 block w-full rounded-lg border border-white/10 bg-slate-950 px-3 py-2.5 text-sm text-white focus:border-emerald-400 focus:outline-none" placeholder="At least 8 characters" />
            </label>
            <label className="text-sm text-slate-300">
              Allowed public IP
              <input type="text" required autoComplete="off" value={allowedIp} onChange={(event) => setAllowedIp(event.target.value)} className="mt-1 block w-full rounded-lg border border-white/10 bg-slate-950 px-3 py-2.5 text-sm text-white placeholder:text-slate-600 focus:border-emerald-400 focus:outline-none" placeholder="Customer’s public IPv4 or IPv6" />
              <span className="mt-1 block text-xs text-slate-500">Enter one public address; the API validates that it is allowed.</span>
            </label>
            <div className="flex flex-wrap items-center gap-3 md:col-span-3">
              <button type="submit" disabled={creating} className="rounded-lg bg-emerald-400 px-4 py-2.5 text-sm font-semibold text-slate-950 hover:bg-emerald-300 disabled:cursor-wait disabled:opacity-50">
                {creating ? "Creating account…" : "Create customer"}
              </button>
              <span className="text-xs text-slate-500">Passwords are sent only to the API and are cleared after success.</span>
            </div>
          </form>
        </section>
      )}

      {error && <p role="alert" className="mt-5 rounded-lg border border-rose-400/30 bg-rose-400/10 p-3 text-sm text-rose-100">{error}</p>}
      {success && <p role="status" className="mt-5 rounded-lg border border-emerald-400/20 bg-emerald-400/5 p-3 text-sm text-emerald-100">{success}</p>}

      <section aria-labelledby="directory-title" className="mt-7 rounded-2xl border border-white/10 bg-white/[0.025] p-4 sm:p-6">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <h2 id="directory-title" className="text-lg font-semibold text-white">Account directory</h2>
            <p className="mt-1 text-sm text-slate-400" aria-live="polite">
              {loadingUsers ? "Loading accounts…" : `${visibleUsers.length} ${visibleUsers.length === 1 ? "account" : "accounts"}`}
            </p>
          </div>
          <div className="grid gap-3 sm:grid-cols-[minmax(14rem,1fr)_10rem]">
            <label className="text-xs font-medium text-slate-400">
              Search accounts
              <input type="search" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Email or allowed IP" className="mt-1 block w-full rounded-lg border border-white/10 bg-slate-950 px-3 py-2.5 text-sm text-white placeholder:text-slate-600 focus:border-emerald-400 focus:outline-none" />
            </label>
            <label className="text-xs font-medium text-slate-400">
              Status
              <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value as typeof statusFilter)} className="mt-1 block w-full rounded-lg border border-white/10 bg-slate-950 px-3 py-2.5 text-sm text-white focus:border-emerald-400 focus:outline-none">
                <option value="all">All statuses</option>
                <option value="active">Active</option>
                <option value="paused">Paused</option>
              </select>
            </label>
          </div>
        </div>

        <div className="mt-5 hidden overflow-x-auto rounded-xl border border-white/10 md:block">
          <table className="w-full min-w-[900px] text-left text-sm">
            <thead className="bg-white/5 text-xs uppercase tracking-wide text-slate-400">
              <tr>
                <th scope="col" className="px-4 py-3">Customer</th>
                <th scope="col" className="px-4 py-3">Role</th>
                <th scope="col" className="px-4 py-3">Status</th>
                <th scope="col" className="px-4 py-3">Allowed public IP</th>
                <th scope="col" className="px-4 py-3">Created</th>
                <th scope="col" className="px-4 py-3">Actions</th>
              </tr>
            </thead>
            <tbody>
              {visibleUsers.map((user) => (
                <tr key={user.id} className="border-t border-white/5 align-top text-slate-200">
                  <td className="px-4 py-4">
                    <span className="font-medium text-white">{user.email}</span>
                    <span className="mt-1 block break-all font-mono text-[10px] text-slate-600">{user.id}</span>
                  </td>
                  <td className="px-4 py-4 capitalize">{user.role}</td>
                  <td className="px-4 py-4">
                    <span className={`inline-flex rounded-full px-2.5 py-1 text-xs font-medium ${user.status === "paused" ? "bg-amber-400/10 text-amber-200" : "bg-emerald-400/10 text-emerald-200"}`}>
                      {user.status}
                    </span>
                  </td>
                  <td className="px-4 py-4 font-mono text-xs text-slate-300">{user.allowed_ip ?? "Not set"}</td>
                  <td className="whitespace-nowrap px-4 py-4 text-slate-400">{formatDate(user.created_at)}</td>
                  <td className="px-4 py-4">{renderActions(user)}</td>
                </tr>
              ))}
              {!loadingUsers && visibleUsers.length === 0 && (
                <tr><td colSpan={6} className="px-4 py-8 text-center text-sm text-slate-500">No accounts match these filters.</td></tr>
              )}
            </tbody>
          </table>
        </div>

        <div className="mt-5 grid gap-3 md:hidden">
          {visibleUsers.map((user) => (
            <article key={user.id} className="rounded-xl border border-white/10 bg-slate-950/60 p-4">
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div className="min-w-0">
                  <h3 className="break-all font-medium text-white">{user.email}</h3>
                  <p className="mt-1 break-all font-mono text-[10px] text-slate-600">{user.id}</p>
                </div>
                <span className={`inline-flex rounded-full px-2.5 py-1 text-xs font-medium ${user.status === "paused" ? "bg-amber-400/10 text-amber-200" : "bg-emerald-400/10 text-emerald-200"}`}>
                  {user.status}
                </span>
              </div>
              <dl className="mt-4 grid grid-cols-2 gap-3 text-xs">
                <div><dt className="text-slate-500">Role</dt><dd className="mt-1 capitalize text-slate-200">{user.role}</dd></div>
                <div><dt className="text-slate-500">Created</dt><dd className="mt-1 text-slate-200">{formatDate(user.created_at)}</dd></div>
                <div className="col-span-2"><dt className="text-slate-500">Allowed public IP</dt><dd className="mt-1 break-all font-mono text-slate-200">{user.allowed_ip ?? "Not set"}</dd></div>
              </dl>
              <div className="mt-4 border-t border-white/10 pt-3">{renderActions(user)}</div>
            </article>
          ))}
          {!loadingUsers && visibleUsers.length === 0 && (
            <p className="rounded-xl border border-white/10 p-6 text-center text-sm text-slate-500">No accounts match these filters.</p>
          )}
        </div>
      </section>

      {deleteTarget && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 p-4" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget && !busyUserId) { setDeleteTarget(null); setDeleteConfirmation(""); } }}>
          <section role="dialog" aria-modal="true" aria-labelledby="delete-dialog-title" className="w-full max-w-lg rounded-2xl border border-rose-400/20 bg-slate-900 p-5 shadow-2xl sm:p-6">
            <p className="text-xs font-medium uppercase tracking-widest text-rose-200">Delete customer</p>
            <h2 id="delete-dialog-title" className="mt-2 text-xl font-semibold text-white">This will remove the login</h2>
            <p className="mt-3 text-sm leading-relaxed text-slate-300">
              To confirm, type <span className="font-semibold text-white">{deleteTarget.email}</span>. This action cannot be undone.
            </p>
            <label className="mt-4 block text-sm text-slate-300">
              Confirm email
              <input type="email" autoComplete="off" autoFocus value={deleteConfirmation} onChange={(event) => setDeleteConfirmation(event.target.value)} className="mt-1 block w-full rounded-lg border border-white/10 bg-slate-950 px-3 py-2.5 text-sm text-white focus:border-rose-300 focus:outline-none" />
            </label>
            <div className="mt-5 flex flex-wrap justify-end gap-2">
              <button type="button" disabled={busyUserId === deleteTarget.id} onClick={() => { setDeleteTarget(null); setDeleteConfirmation(""); }} className="rounded-lg border border-white/15 px-4 py-2.5 text-sm font-medium text-slate-200 hover:bg-white/5 disabled:opacity-50">Cancel</button>
              <button type="button" disabled={busyUserId === deleteTarget.id || deleteConfirmation.trim().toLowerCase() !== deleteTarget.email.trim().toLowerCase()} onClick={() => void deleteUser()} className="rounded-lg bg-rose-500 px-4 py-2.5 text-sm font-semibold text-white hover:bg-rose-400 disabled:cursor-not-allowed disabled:opacity-40">
                {busyUserId === deleteTarget.id ? "Deleting…" : "Delete customer"}
              </button>
            </div>
          </section>
        </div>
      )}

      {!API_BASE_URL && <p role="alert" className="mt-5 rounded-lg border border-amber-300/20 bg-amber-300/5 p-3 text-sm text-amber-100">Set the public API URL using <code>NEXT_PUBLIC_API_BASE_URL</code>.</p>}
    </div>
  );
}
