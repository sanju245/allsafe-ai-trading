"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";
import { AdminUsersPanel } from "@/components/admin/AdminUsersPanel";
import { useAuth } from "@/components/auth/AuthProvider";
import { DashboardAccessGate } from "@/components/auth/DashboardAccessGate";
import { fetchApi } from "@/lib/api";

type AdminSection = "overview" | "users" | "roles" | "content" | "audit" | "health";

interface AdminStats {
  total_users: number;
  active_users: number;
  paused_users: number;
  locked_users: number;
  admin_users: number;
  super_admin_id: string;
  super_admin_username: string;
  global_ip_access_enabled: boolean;
  active_sessions: number;
  audit_events_count: number;
  error_events_count: number;
  read_only_mode: boolean;
  execution_disabled: boolean;
  market_feed_state: string;
  market_session_open: boolean;
  api_version: string;
  environment: string;
  checked_at: string;
}

interface RoleDef {
  role: string;
  label: string;
  description: string;
  is_system_role: boolean;
  permissions: string[];
  user_count: number;
}

interface ContentConfig {
  announcement_banner: string;
  announcement_enabled: boolean;
  featured_instruments: string[];
  default_timeframe: string;
  default_capital_inr: number;
  default_risk_pct: number;
  max_risk_pct_cap: number;
  min_risk_reward_ratio: number;
  educational_disclaimer: string;
  read_only_safety_lock: boolean;
  updated_at: string;
  updated_by: string;
}

interface AuditLogEntry {
  id: string;
  timestamp: string;
  actor_id: string;
  actor_email: string;
  action: string;
  target_type: string;
  target_id?: string | null;
  severity: "info" | "warning" | "critical";
  ip_address: string;
  status: "success" | "denied" | "error";
  details: string;
}

interface SystemSettings {
  admin_global_ip_access: boolean;
  session_ttl_seconds: number;
  login_rate_limit_per_minute: number;
  max_failed_login_attempts: number;
  lockout_duration_seconds: number;
  live_poll_interval_seconds: number;
  off_hours_poll_interval_seconds: number;
  require_strong_passwords: boolean;
  csrf_protection_enabled: boolean;
  maintenance_mode: boolean;
  read_only_trading_invariant: boolean;
  updated_at: string;
  updated_by: string;
}

interface HealthReport {
  status: "healthy" | "degraded" | "offline";
  service: string;
  version: string;
  environment: string;
  checked_at: string;
  uptime_seconds: number;
  database_mode: string;
  supabase_configured: boolean;
  super_admin_provisioned: boolean;
  global_ip_access_enabled: boolean;
  market_feed: Record<string, unknown>;
  security_posture: Record<string, unknown>;
  recent_errors: {
    id: string;
    timestamp: string;
    component: string;
    severity: string;
    message: string;
  }[];
}

const NAV_ITEMS: { id: AdminSection; label: string; badge?: string }[] = [
  { id: "overview", label: "Dashboard Overview" },
  { id: "users", label: "User Management" },
  { id: "roles", label: "Roles & Permissions" },
  { id: "content", label: "Content & Application" },
  { id: "audit", label: "Activity & Audit Logs" },
  { id: "health", label: "Settings & System Health" },
];

export default function AdminPage() {
  const { token, csrfToken, user } = useAuth();
  const [activeSection, setActiveSection] = useState<AdminSection>("overview");
  const [stats, setStats] = useState<AdminStats | null>(null);
  const [roles, setRoles] = useState<RoleDef[]>([]);
  const [content, setContent] = useState<ContentConfig | null>(null);
  const [auditLogs, setAuditLogs] = useState<AuditLogEntry[]>([]);
  const [settings, setSettings] = useState<SystemSettings | null>(null);
  const [health, setHealth] = useState<HealthReport | null>(null);

  const [auditSearch, setAuditSearch] = useState("");
  const [auditSeverity, setAuditSeverity] = useState("all");
  const [loading, setLoading] = useState(true);
  const [bannerError, setBannerError] = useState<string | null>(null);
  const [bannerSuccess, setBannerSuccess] = useState<string | null>(null);

  const loadAdminTelemetry = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    try {
      const [statsRes, rolesRes, contentRes, auditRes, settingsRes, healthRes] =
        await Promise.all([
          fetchApi<AdminStats>("/api/v1/admin/stats", { token }),
          fetchApi<RoleDef[]>("/api/v1/admin/roles", { token }),
          fetchApi<ContentConfig>("/api/v1/admin/content", { token }),
          fetchApi<AuditLogEntry[]>("/api/v1/admin/audit-logs?limit=100", { token }),
          fetchApi<SystemSettings>("/api/v1/admin/settings", { token }),
          fetchApi<HealthReport>("/api/v1/admin/health", { token }),
        ]);
      setStats(statsRes);
      setRoles(rolesRes);
      setContent(contentRes);
      setAuditLogs(auditRes);
      setSettings(settingsRes);
      setHealth(healthRes);
      setBannerError(null);
    } catch (err) {
      setBannerError(
        err instanceof Error ? err.message : "Failed to load Admin Control Center telemetry.",
      );
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    void loadAdminTelemetry();
  }, [loadAdminTelemetry]);

  const handleSaveContent = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (!token || !content) return;
    setBannerError(null);
    setBannerSuccess(null);
    try {
      const updated = await fetchApi<ContentConfig>("/api/v1/admin/content", {
        method: "PATCH",
        token,
        csrfToken,
        body: JSON.stringify({
          announcement_banner: content.announcement_banner,
          announcement_enabled: content.announcement_enabled,
          default_capital_inr: content.default_capital_inr,
          default_risk_pct: content.default_risk_pct,
          min_risk_reward_ratio: content.min_risk_reward_ratio,
          educational_disclaimer: content.educational_disclaimer,
        }),
      });
      setContent(updated);
      setBannerSuccess("Application content and risk parameters saved.");
      void loadAdminTelemetry();
    } catch (err) {
      setBannerError(err instanceof Error ? err.message : "Failed to update content settings.");
    }
  };

  const handleSaveSettings = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (!token || !settings) return;
    setBannerError(null);
    setBannerSuccess(null);
    try {
      const updated = await fetchApi<SystemSettings>("/api/v1/admin/settings", {
        method: "PATCH",
        token,
        csrfToken,
        body: JSON.stringify({
          admin_global_ip_access: settings.admin_global_ip_access,
          session_ttl_seconds: settings.session_ttl_seconds,
          login_rate_limit_per_minute: settings.login_rate_limit_per_minute,
          max_failed_login_attempts: settings.max_failed_login_attempts,
          lockout_duration_seconds: settings.lockout_duration_seconds,
          live_poll_interval_seconds: settings.live_poll_interval_seconds,
          off_hours_poll_interval_seconds: settings.off_hours_poll_interval_seconds,
          maintenance_mode: settings.maintenance_mode,
        }),
      });
      setSettings(updated);
      setBannerSuccess("System & security configuration updated.");
      void loadAdminTelemetry();
    } catch (err) {
      setBannerError(err instanceof Error ? err.message : "Failed to update system settings.");
    }
  };

  const filteredAuditLogs = auditLogs.filter((entry) => {
    const matchesSev = auditSeverity === "all" || entry.severity === auditSeverity;
    const q = auditSearch.trim().toLowerCase();
    const matchesSearch =
      !q ||
      entry.action.toLowerCase().includes(q) ||
      entry.actor_email.toLowerCase().includes(q) ||
      entry.details.toLowerCase().includes(q) ||
      entry.ip_address.toLowerCase().includes(q);
    return matchesSev && matchesSearch;
  });

  return (
    <DashboardAccessGate requireAdmin>
      <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:px-8">
        {/* Top Admin Header */}
        <header className="flex flex-wrap items-center justify-between gap-4 border-b border-white/10 pb-5">
          <div>
            <div className="flex items-center gap-2">
              <span className="rounded-md border border-emerald-500/30 bg-emerald-500/10 px-2 py-0.5 text-[11px] font-bold uppercase tracking-wider text-emerald-300">
                Admin Control Center
              </span>
              <span className="rounded-md border border-white/10 bg-white/5 px-2 py-0.5 font-mono text-[11px] text-slate-300">
                Global IP Access: {stats?.global_ip_access_enabled !== false ? "ENABLED (*)" : "RESTRICTED"}
              </span>
            </div>
            <h1 className="mt-2 text-2xl font-bold tracking-tight text-white sm:text-3xl">
              System Administration &amp; Security Governance
            </h1>
            <p className="mt-1 text-sm text-slate-400">
              Signed in as <strong className="text-slate-200">{user?.email}</strong> (
              {user?.is_super_admin ? `Permanent Super Admin · ${user.id}` : `Role: ${user?.role}`})
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-2.5">
            <button
              type="button"
              onClick={() => void loadAdminTelemetry()}
              disabled={loading}
              className="rounded-xl border border-white/10 bg-white/5 px-3.5 py-2 text-xs font-medium text-slate-200 transition hover:bg-white/10 disabled:opacity-50"
            >
              {loading ? "Refreshing..." : "Sync Telemetry"}
            </button>
          </div>
        </header>

        {bannerError && (
          <div
            role="alert"
            className="mt-5 flex items-center justify-between rounded-xl border border-rose-500/30 bg-rose-500/10 p-4 text-xs text-rose-200"
          >
            <span>{bannerError}</span>
            <button
              type="button"
              onClick={() => setBannerError(null)}
              className="font-semibold underline"
            >
              Dismiss
            </button>
          </div>
        )}

        {bannerSuccess && (
          <div
            role="status"
            className="mt-5 flex items-center justify-between rounded-xl border border-emerald-500/30 bg-emerald-500/10 p-4 text-xs text-emerald-200"
          >
            <span>{bannerSuccess}</span>
            <button
              type="button"
              onClick={() => setBannerSuccess(null)}
              className="font-semibold underline"
            >
              Dismiss
            </button>
          </div>
        )}

        {/* Responsive Sidebar + Main Content Layout */}
        <div className="mt-6 grid gap-6 lg:grid-cols-[15rem_1fr]">
          {/* Sidebar / Mobile Horizontal Nav */}
          <aside aria-label="Admin dashboard sections">
            <nav className="flex gap-1.5 overflow-x-auto rounded-2xl border border-white/10 bg-slate-900/60 p-2 lg:flex-col">
              {NAV_ITEMS.map((item) => {
                const isActive = activeSection === item.id;
                return (
                  <button
                    key={item.id}
                    type="button"
                    onClick={() => setActiveSection(item.id)}
                    aria-current={isActive ? "page" : undefined}
                    className={`whitespace-nowrap rounded-xl px-3.5 py-2.5 text-left text-xs font-medium transition ${
                      isActive
                        ? "bg-emerald-500 text-slate-950 font-semibold shadow"
                        : "text-slate-300 hover:bg-white/5 hover:text-white"
                    }`}
                  >
                    {item.label}
                  </button>
                );
              })}
            </nav>

            {/* Permanent Super Admin Identity Card */}
            <div className="mt-4 hidden rounded-2xl border border-emerald-500/20 bg-emerald-500/5 p-4 text-xs lg:block">
              <p className="font-semibold uppercase tracking-wider text-emerald-300">
                Super Admin Identity
              </p>
              <p className="mt-1.5 font-mono text-[11px] text-slate-200">
                @{stats?.super_admin_username || "superadmin"}
              </p>
              <p className="mt-1 break-all font-mono text-[10px] text-slate-400">
                ID: {stats?.super_admin_id || "00000000-0000-4000-a000-000000000001"}
              </p>
              <p className="mt-2 text-[11px] text-emerald-200/90">
                Global IP Login: <strong>Any IP (*)</strong>
              </p>
            </div>
          </aside>

          {/* Main Section Content */}
          <div className="min-w-0 space-y-6">
            {activeSection === "overview" && (
              <div className="space-y-6">
                {/* KPI Cards */}
                <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
                  <div className="rounded-2xl border border-white/10 bg-slate-900/60 p-4">
                    <p className="text-xs font-medium text-slate-400">Total Accounts</p>
                    <p className="mt-2 text-2xl font-bold tabular-nums text-white">
                      {stats?.total_users ?? 1}
                    </p>
                    <p className="mt-1 text-xs text-emerald-300">
                      {stats?.active_users ?? 1} active &middot; {stats?.paused_users ?? 0} paused &middot;{" "}
                      {stats?.locked_users ?? 0} locked
                    </p>
                  </div>

                  <div className="rounded-2xl border border-white/10 bg-slate-900/60 p-4">
                    <p className="text-xs font-medium text-slate-400">Admin &amp; Sessions</p>
                    <p className="mt-2 text-2xl font-bold tabular-nums text-white">
                      {stats?.admin_users ?? 1} Admin(s)
                    </p>
                    <p className="mt-1 text-xs text-sky-300">
                      {stats?.active_sessions ?? 1} active authenticated session(s)
                    </p>
                  </div>

                  <div className="rounded-2xl border border-white/10 bg-slate-900/60 p-4">
                    <p className="text-xs font-medium text-slate-400">Market Feed Status</p>
                    <p className="mt-2 text-2xl font-bold uppercase text-emerald-400">
                      {stats?.market_feed_state ?? "checking"}
                    </p>
                    <p className="mt-1 text-xs text-slate-300">
                      NSE Session: {stats?.market_session_open ? "OPEN" : "CLOSED"} &middot; Read-Only
                    </p>
                  </div>

                  <div className="rounded-2xl border border-white/10 bg-slate-900/60 p-4">
                    <p className="text-xs font-medium text-slate-400">Security &amp; Audit Events</p>
                    <p className="mt-2 text-2xl font-bold tabular-nums text-white">
                      {stats?.audit_events_count ?? auditLogs.length}
                    </p>
                    <p className="mt-1 text-xs text-slate-300">
                      {stats?.error_events_count ?? 0} active error alert(s)
                    </p>
                  </div>
                </div>

                {/* Embedded User Directory on Overview for instant access */}
                <AdminUsersPanel onDirectoryChanged={() => void loadAdminTelemetry()} />
              </div>
            )}

            {activeSection === "users" && (
              <AdminUsersPanel onDirectoryChanged={() => void loadAdminTelemetry()} />
            )}

            {activeSection === "roles" && (
              <section className="space-y-4 rounded-2xl border border-white/10 bg-slate-900/50 p-5 sm:p-6">
                <div>
                  <h2 className="text-lg font-bold text-white">Role &amp; Permission Management</h2>
                  <p className="text-xs text-slate-400">
                    Role-based access control (RBAC) definitions enforced across API routes and UI gates
                  </p>
                </div>

                <div className="grid gap-4">
                  {roles.map((r) => (
                    <article
                      key={r.role}
                      className="rounded-xl border border-white/10 bg-slate-950/60 p-4"
                    >
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <div>
                          <div className="flex items-center gap-2">
                            <h3 className="text-sm font-bold text-white">{r.label}</h3>
                            <span className="rounded bg-white/10 px-2 py-0.5 font-mono text-[11px] text-emerald-300">
                              {r.role}
                            </span>
                          </div>
                          <p className="mt-1 text-xs text-slate-400">{r.description}</p>
                        </div>
                        <span className="rounded-full border border-white/10 bg-white/5 px-3 py-1 text-xs text-slate-300">
                          {r.user_count} {r.user_count === 1 ? "account" : "accounts"}
                        </span>
                      </div>

                      <div className="mt-3 flex flex-wrap gap-1.5">
                        {r.permissions.map((perm) => (
                          <span
                            key={perm}
                            className="rounded-md border border-emerald-500/20 bg-emerald-500/10 px-2 py-0.5 font-mono text-[11px] text-emerald-200"
                          >
                            {perm}
                          </span>
                        ))}
                      </div>
                    </article>
                  ))}
                </div>
              </section>
            )}

            {activeSection === "content" && content && (
              <section className="space-y-4 rounded-2xl border border-white/10 bg-slate-900/50 p-5 sm:p-6">
                <div>
                  <h2 className="text-lg font-bold text-white">Content &amp; Application Management</h2>
                  <p className="text-xs text-slate-400">
                    Configure dashboard announcements, default capital &amp; risk sizing parameters, and educational disclosures
                  </p>
                </div>

                <form onSubmit={handleSaveContent} className="space-y-4">
                  <label className="block text-xs font-medium text-slate-300">
                    Dashboard Announcement Banner
                    <input
                      type="text"
                      value={content.announcement_banner}
                      onChange={(e) =>
                        setContent({ ...content, announcement_banner: e.target.value })
                      }
                      className="mt-1 block w-full rounded-lg border border-white/10 bg-slate-950 px-3 py-2 text-sm text-white focus:border-emerald-400 focus:outline-none"
                    />
                  </label>

                  <label className="inline-flex items-center gap-2 text-xs font-medium text-slate-200">
                    <input
                      type="checkbox"
                      checked={content.announcement_enabled}
                      onChange={(e) =>
                        setContent({ ...content, announcement_enabled: e.target.checked })
                      }
                      className="h-4 w-4 rounded border-white/20 bg-slate-950 text-emerald-500"
                    />
                    Display announcement banner on Live Market Terminal
                  </label>

                  <div className="grid gap-4 sm:grid-cols-3">
                    <label className="block text-xs font-medium text-slate-300">
                      Default Capital (INR)
                      <input
                        type="number"
                        min={25000}
                        max={50000000}
                        step={25000}
                        value={content.default_capital_inr}
                        onChange={(e) =>
                          setContent({
                            ...content,
                            default_capital_inr: Number(e.target.value) || 200000,
                          })
                        }
                        className="mt-1 block w-full rounded-lg border border-white/10 bg-slate-950 px-3 py-2 text-sm text-white focus:border-emerald-400 focus:outline-none"
                      />
                    </label>

                    <label className="block text-xs font-medium text-slate-300">
                      Default Risk per Trade (%)
                      <input
                        type="number"
                        min={0.1}
                        max={2.0}
                        step={0.1}
                        value={content.default_risk_pct}
                        onChange={(e) =>
                          setContent({
                            ...content,
                            default_risk_pct: Number(e.target.value) || 1.0,
                          })
                        }
                        className="mt-1 block w-full rounded-lg border border-white/10 bg-slate-950 px-3 py-2 text-sm text-white focus:border-emerald-400 focus:outline-none"
                      />
                    </label>

                    <label className="block text-xs font-medium text-slate-300">
                      Minimum Risk/Reward Ratio
                      <input
                        type="number"
                        min={1.2}
                        max={5.0}
                        step={0.1}
                        value={content.min_risk_reward_ratio}
                        onChange={(e) =>
                          setContent({
                            ...content,
                            min_risk_reward_ratio: Number(e.target.value) || 1.5,
                          })
                        }
                        className="mt-1 block w-full rounded-lg border border-white/10 bg-slate-950 px-3 py-2 text-sm text-white focus:border-emerald-400 focus:outline-none"
                      />
                    </label>
                  </div>

                  <label className="block text-xs font-medium text-slate-300">
                    Educational &amp; Regulatory Risk Disclaimer
                    <textarea
                      rows={3}
                      value={content.educational_disclaimer}
                      onChange={(e) =>
                        setContent({ ...content, educational_disclaimer: e.target.value })
                      }
                      className="mt-1 block w-full rounded-lg border border-white/10 bg-slate-950 px-3 py-2 text-sm text-white focus:border-emerald-400 focus:outline-none"
                    />
                  </label>

                  <div className="flex items-center justify-between rounded-xl border border-emerald-500/20 bg-emerald-500/5 px-4 py-3 text-xs text-emerald-200">
                    <span>
                      Core Safety Invariant: <strong>Read-Only Analytical Mode</strong> (Live order execution is permanently disabled)
                    </span>
                    <button
                      type="submit"
                      className="rounded-xl bg-emerald-500 px-4 py-2 font-semibold text-slate-950 transition hover:bg-emerald-400"
                    >
                      Save Application Config
                    </button>
                  </div>
                </form>
              </section>
            )}

            {activeSection === "audit" && (
              <section className="space-y-4 rounded-2xl border border-white/10 bg-slate-900/50 p-5 sm:p-6">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <h2 className="text-lg font-bold text-white">System Activity &amp; Security Audit Logs</h2>
                    <p className="text-xs text-slate-400">
                      Immutable record of authentication events, IP policy checks, account changes, and administrative actions
                    </p>
                  </div>
                </div>

                <div className="grid gap-3 sm:grid-cols-[1fr_12rem]">
                  <input
                    type="search"
                    value={auditSearch}
                    onChange={(e) => setAuditSearch(e.target.value)}
                    placeholder="Filter by action, email, IP, or detail..."
                    className="rounded-lg border border-white/10 bg-slate-950 px-3 py-2 text-sm text-white placeholder:text-slate-600 focus:border-emerald-400 focus:outline-none"
                  />
                  <select
                    value={auditSeverity}
                    onChange={(e) => setAuditSeverity(e.target.value)}
                    className="rounded-lg border border-white/10 bg-slate-950 px-3 py-2 text-sm text-white focus:border-emerald-400 focus:outline-none"
                  >
                    <option value="all">All severities</option>
                    <option value="info">Info</option>
                    <option value="warning">Warning</option>
                    <option value="critical">Critical</option>
                  </select>
                </div>

                <div className="overflow-x-auto rounded-xl border border-white/10">
                  <table className="w-full min-w-[760px] text-left text-xs">
                    <thead className="bg-white/5 uppercase tracking-wider text-slate-400">
                      <tr>
                        <th className="px-3.5 py-2.5">Timestamp (UTC)</th>
                        <th className="px-3.5 py-2.5">Action</th>
                        <th className="px-3.5 py-2.5">Actor</th>
                        <th className="px-3.5 py-2.5">IP Address</th>
                        <th className="px-3.5 py-2.5">Severity / Status</th>
                        <th className="px-3.5 py-2.5">Details</th>
                      </tr>
                    </thead>
                    <tbody>
                      {filteredAuditLogs.map((log) => (
                        <tr key={log.id} className="border-t border-white/5 text-slate-200">
                          <td className="whitespace-nowrap px-3.5 py-2.5 font-mono text-[11px] text-slate-400">
                            {new Date(log.timestamp).toLocaleString("en-IN", {
                              timeZone: "Asia/Kolkata",
                            })}
                          </td>
                          <td className="px-3.5 py-2.5 font-mono font-semibold text-white">
                            {log.action}
                          </td>
                          <td className="px-3.5 py-2.5">{log.actor_email}</td>
                          <td className="px-3.5 py-2.5 font-mono text-slate-300">{log.ip_address}</td>
                          <td className="px-3.5 py-2.5">
                            <span
                              className={`inline-flex rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase ${
                                log.severity === "critical"
                                  ? "bg-rose-500/20 text-rose-200"
                                  : log.severity === "warning"
                                  ? "bg-amber-500/20 text-amber-200"
                                  : "bg-emerald-500/15 text-emerald-200"
                              }`}
                            >
                              {log.severity} &middot; {log.status}
                            </span>
                          </td>
                          <td className="px-3.5 py-2.5 text-slate-300">{log.details}</td>
                        </tr>
                      ))}
                      {filteredAuditLogs.length === 0 && (
                        <tr>
                          <td colSpan={6} className="px-4 py-6 text-center text-slate-500">
                            No audit log entries match the current filter.
                          </td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>
              </section>
            )}

            {activeSection === "health" && (
              <div className="space-y-6">
                {settings && (
                  <section className="space-y-4 rounded-2xl border border-white/10 bg-slate-900/50 p-5 sm:p-6">
                    <div>
                      <h2 className="text-lg font-bold text-white">
                        Security &amp; System Configuration Management
                      </h2>
                      <p className="text-xs text-slate-400">
                        Manage global admin IP accessibility, session expiration, rate limiting, and brute-force lockout thresholds
                      </p>
                    </div>

                    <form onSubmit={handleSaveSettings} className="space-y-4">
                      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                        <label className="block text-xs font-medium text-slate-300">
                          Session Expiration (seconds)
                          <input
                            type="number"
                            min={300}
                            max={86400}
                            value={settings.session_ttl_seconds}
                            onChange={(e) =>
                              setSettings({
                                ...settings,
                                session_ttl_seconds: Number(e.target.value) || 28800,
                              })
                            }
                            className="mt-1 block w-full rounded-lg border border-white/10 bg-slate-950 px-3 py-2 text-sm text-white focus:border-emerald-400 focus:outline-none"
                          />
                        </label>

                        <label className="block text-xs font-medium text-slate-300">
                          Login Rate Limit (requests / min / IP)
                          <input
                            type="number"
                            min={3}
                            max={120}
                            value={settings.login_rate_limit_per_minute}
                            onChange={(e) =>
                              setSettings({
                                ...settings,
                                login_rate_limit_per_minute: Number(e.target.value) || 12,
                              })
                            }
                            className="mt-1 block w-full rounded-lg border border-white/10 bg-slate-950 px-3 py-2 text-sm text-white focus:border-emerald-400 focus:outline-none"
                          />
                        </label>

                        <label className="block text-xs font-medium text-slate-300">
                          Max Failed Login Attempts
                          <input
                            type="number"
                            min={3}
                            max={20}
                            value={settings.max_failed_login_attempts}
                            onChange={(e) =>
                              setSettings({
                                ...settings,
                                max_failed_login_attempts: Number(e.target.value) || 5,
                              })
                            }
                            className="mt-1 block w-full rounded-lg border border-white/10 bg-slate-950 px-3 py-2 text-sm text-white focus:border-emerald-400 focus:outline-none"
                          />
                        </label>
                      </div>

                      <div className="flex flex-wrap items-center gap-6 pt-1">
                        <label className="inline-flex items-center gap-2 text-xs font-medium text-slate-200">
                          <input
                            type="checkbox"
                            checked={settings.admin_global_ip_access}
                            onChange={(e) =>
                              setSettings({
                                ...settings,
                                admin_global_ip_access: e.target.checked,
                              })
                            }
                            className="h-4 w-4 rounded border-white/20 bg-slate-950 text-emerald-500"
                          />
                          Allow Admin Login from Any Legitimate IP Globally (Super Admin always enabled)
                        </label>

                        <label className="inline-flex items-center gap-2 text-xs font-medium text-slate-200">
                          <input
                            type="checkbox"
                            checked={settings.maintenance_mode}
                            onChange={(e) =>
                              setSettings({
                                ...settings,
                                maintenance_mode: e.target.checked,
                              })
                            }
                            className="h-4 w-4 rounded border-white/20 bg-slate-950 text-emerald-500"
                          />
                          Maintenance Banner Mode
                        </label>
                      </div>

                      <div className="flex justify-end">
                        <button
                          type="submit"
                          className="rounded-xl bg-emerald-500 px-4 py-2 text-xs font-semibold text-slate-950 transition hover:bg-emerald-400"
                        >
                          Save Security Settings
                        </button>
                      </div>
                    </form>
                  </section>
                )}

                {health && (
                  <section className="space-y-4 rounded-2xl border border-white/10 bg-slate-900/50 p-5 sm:p-6">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div>
                        <h2 className="text-lg font-bold text-white">
                          System Health &amp; Error Diagnostics
                        </h2>
                        <p className="text-xs text-slate-400">
                          Real-time backend service telemetry, security posture verification, and error reporting
                        </p>
                      </div>
                      <span className="rounded-full border border-emerald-500/30 bg-emerald-500/15 px-3 py-1 text-xs font-semibold uppercase text-emerald-300">
                        {health.status} &middot; v{health.version}
                      </span>
                    </div>

                    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4 text-xs">
                      <div className="rounded-xl border border-white/5 bg-slate-950/60 p-3.5">
                        <p className="text-slate-400">Uptime</p>
                        <p className="mt-1 font-mono text-sm font-semibold text-white">
                          {health.uptime_seconds}s
                        </p>
                      </div>
                      <div className="rounded-xl border border-white/5 bg-slate-950/60 p-3.5">
                        <p className="text-slate-400">Database Mode</p>
                        <p className="mt-1 font-mono text-sm font-semibold text-emerald-300">
                          {health.database_mode}
                        </p>
                      </div>
                      <div className="rounded-xl border border-white/5 bg-slate-950/60 p-3.5">
                        <p className="text-slate-400">Super Admin Provisioned</p>
                        <p className="mt-1 font-mono text-sm font-semibold text-emerald-300">
                          {health.super_admin_provisioned ? "VERIFIED" : "MISSING"}
                        </p>
                      </div>
                      <div className="rounded-xl border border-white/5 bg-slate-950/60 p-3.5">
                        <p className="text-slate-400">Global IP Access</p>
                        <p className="mt-1 font-mono text-sm font-semibold text-emerald-300">
                          {health.global_ip_access_enabled ? "ACTIVE (*)" : "CUSTOM"}
                        </p>
                      </div>
                    </div>

                    <div className="rounded-xl border border-white/10 bg-slate-950/60 p-4">
                      <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-300">
                        Recent System Error Reports ({health.recent_errors.length})
                      </h3>
                      {health.recent_errors.length === 0 ? (
                        <p className="mt-2 text-xs text-emerald-300">
                          Zero unhandled system errors recorded.
                        </p>
                      ) : (
                        <ul className="mt-2 space-y-2 text-xs">
                          {health.recent_errors.map((err) => (
                            <li
                              key={err.id}
                              className="rounded-lg border border-rose-500/20 bg-rose-500/10 p-2.5 text-rose-200"
                            >
                              <span className="font-mono text-[11px] text-rose-300">
                                [{err.component}]
                              </span>{" "}
                              {err.message}
                            </li>
                          ))}
                        </ul>
                      )}
                    </div>
                  </section>
                )}
              </div>
            )}
          </div>
        </div>
      </div>
    </DashboardAccessGate>
  );
}
