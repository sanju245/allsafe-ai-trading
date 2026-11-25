"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { useAuth } from "@/components/auth/AuthProvider";
import CustomerWarnings from "@/components/auth/CustomerWarnings";
import CustomerWorkspaceHeader from "@/components/auth/CustomerWorkspaceHeader";

export default function AccountPage() {
  const router = useRouter();
  const { session, profile, loading, signOut, changePassword } = useAuth();
  const [currentPassword, setCurrentPassword] = useState("");
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [savingPassword, setSavingPassword] = useState(false);
  const saving = useRef(false);

  useEffect(() => {
    if (!loading && !session) router.replace("/login?next=%2Faccount");
  }, [loading, router, session]);

  async function submitPassword(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (saving.current) return;
    setError(null);
    setMessage(null);
    if (password.length < 8 || password.length > 128) {
      setError("Choose a password between 8 and 128 characters.");
      return;
    }
    if (password !== confirmation) {
      setError("The password entries do not match.");
      return;
    }
    if (password === currentPassword) {
      setError("Choose a new password different from your current password.");
      return;
    }
    saving.current = true;
    setSavingPassword(true);
    try {
      await changePassword(currentPassword, password);
      setCurrentPassword("");
      setPassword("");
      setConfirmation("");
      setMessage("Password changed. Check your registered email for confirmation.");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not change the password.");
    } finally {
      saving.current = false;
      setSavingPassword(false);
    }
  }

  async function leaveAccount() {
    await signOut();
    router.replace("/login");
  }

  if (loading || !session || !profile) {
    return (
      <main className="as-page">
        <div className="as-auth">
          <p className="as-panel as-auth-card text-sm text-ui-muted" role="status">
          {loading ? "Checking your account…" : "Redirecting to sign in…"}
          </p>
        </div>
      </main>
    );
  }

  return (
    <div className="workspace-shell">
      <CustomerWorkspaceHeader email={profile.email} isAdmin={profile.role === "admin"} onSignOut={() => void leaveAccount()} />
      <main className="workspace-main">
        <header className="workspace-page-top">
          <div className="as-container workspace-page-top-inner">
            <p className="as-kicker">Settings</p>
            <h1 className="as-title">Your account</h1>
            <p className="as-subtitle mt-2 text-sm">Review your access and manage your password.</p>
          </div>
        </header>
        <div className="as-container py-6">
        <CustomerWarnings />
        <div className="as-account-grid mt-6">
          <section aria-labelledby="account-details-title" className="as-panel p-5 sm:p-6">
            <h2 id="account-details-title" className="as-section-title">Account details</h2>
            <dl className="mt-4 grid gap-4 text-sm">
              <div>
                <dt className="text-xs text-ui-muted">Sign-in email</dt>
                <dd className="mt-1 break-all font-medium text-ui-ink">{profile.email}</dd>
              </div>
              <div className="as-inset grid grid-cols-2 gap-3 p-3">
                <div><dt className="text-xs text-ui-muted">Account role</dt><dd className="mt-1 capitalize text-ui-ink">{profile.role === "user" ? "Customer" : profile.role}</dd></div>
                <div><dt className="text-xs text-ui-muted">Login status</dt><dd className={`as-pill mt-1 capitalize ${profile.status === "paused" ? "as-pill--amber" : "as-pill--green"}`}>{profile.status}</dd></div>
              </div>
            </dl>
          </section>
          <section className="as-panel p-5 sm:p-6">
            {profile.status === "paused" ? (
              <div className="mt-6 rounded-lg border border-ui-amber/25 bg-ui-amber/10 p-4 text-sm text-ui-amber">
                This login is paused. Contact the administrator to restore access.
              </div>
            ) : (
              <form id="change-password" onSubmit={submitPassword} aria-busy={savingPassword}>
                <h2 className="as-section-title">Change password</h2>
                <p className="mt-1 text-sm text-ui-muted">Use between 8 and 128 characters. We’ll email your registered address when your password changes.</p>
                <label className="mt-4 block text-sm text-ui-muted">
                  Current password
                  <input type="password" autoComplete="current-password" maxLength={128} required value={currentPassword} disabled={savingPassword}
                    onChange={(event) => setCurrentPassword(event.target.value)}
                    className="as-field mt-1 w-full" />
                </label>
                <div className="mt-4 grid gap-4 sm:grid-cols-2">
                  <label className="text-sm text-ui-muted">
                    New password
                    <input
                      type="password"
                      autoComplete="new-password"
                      minLength={8}
                      maxLength={128}
                      required
                      disabled={savingPassword}
                      value={password}
                      onChange={(event) => setPassword(event.target.value)}
                      className="as-field mt-1 w-full"
                    />
                  </label>
                  <label className="text-sm text-ui-muted">
                    Confirm password
                    <input
                      type="password"
                      autoComplete="new-password"
                      minLength={8}
                      maxLength={128}
                      required
                      disabled={savingPassword}
                      value={confirmation}
                      onChange={(event) => setConfirmation(event.target.value)}
                      className="as-field mt-1 w-full"
                    />
                  </label>
                </div>
                <button
                  type="submit"
                  disabled={savingPassword}
                  className="as-button as-button--primary mt-4"
                >
                  {savingPassword ? "Updating password…" : "Change password"}
                </button>
              </form>
            )}

            {error && (
              <p role="alert" className="mt-4 rounded-lg border border-ui-red/25 bg-ui-red/10 p-3 text-sm text-ui-red">
                {error}
              </p>
            )}
            {message && (
              <p role="status" className="mt-4 rounded-lg border border-ui-green/25 bg-ui-green/5 p-3 text-sm text-ui-green">
                {message}
              </p>
            )}
          </section>
        </div>
        </div>
      </main>
    </div>
  );
}
