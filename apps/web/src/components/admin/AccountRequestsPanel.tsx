"use client";

import { useCallback, useEffect, useState } from "react";

type AccountRequest = {
  id: string;
  full_name: string;
  date_of_birth: string;
  email: string;
  phone_number: string;
  whatsapp_number: string;
  request_ip: string | null;
  status: "pending" | "processing" | "approved" | "declined";
  notification_status: "pending" | "sent" | "failed";
  notification_status_saved?: boolean | null;
  created_at: string;
  decided_at: string | null;
};

const API_BASE_URL = (
  process.env.NEXT_PUBLIC_API_BASE_URL?.trim() ||
  (process.env.NODE_ENV === "development" ? "http://localhost:8000" : "https://allsafe-ai-api.onrender.com")
).replace(/\/+$/, "");

async function apiRequest<T>(token: string, path: string, method: "GET" | "POST" = "GET"): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method,
    headers: { Authorization: `Bearer ${token}`, Accept: "application/json" },
    cache: "no-store",
    credentials: "omit",
  });
  if (!response.ok) {
    let message = `Account request service returned HTTP ${response.status}.`;
    try {
      const body: unknown = await response.json();
      if (typeof body === "object" && body !== null && "detail" in body) {
        const detail = (body as { detail: unknown }).detail;
        if (typeof detail === "string") message = detail;
      }
    } catch { /* Keep the HTTP message. */ }
    throw new Error(message);
  }
  return response.json() as Promise<T>;
}

function formatDate(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

export default function AccountRequestsPanel({ accessToken, onApproved }: { accessToken: string; onApproved: () => Promise<void> }) {
  const [requests, setRequests] = useState<AccountRequest[]>([]);
  const [loading, setLoading] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [showHistory, setShowHistory] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const reply = await apiRequest<{ requests: AccountRequest[] }>(accessToken, "/api/v1/admin/account-requests");
      setRequests(Array.isArray(reply.requests) ? reply.requests : []);
      setError(null);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not load account requests.");
    } finally {
      setLoading(false);
    }
  }, [accessToken]);

  useEffect(() => {
    const timer = window.setTimeout(() => { void refresh(); }, 0);
    return () => window.clearTimeout(timer);
  }, [refresh]);

  async function decide(request: AccountRequest, action: "approve" | "decline" | "retry-email") {
    setBusyId(request.id);
    setError(null);
    setNotice(null);
    try {
      const updated = await apiRequest<AccountRequest>(
        accessToken,
        `/api/v1/admin/account-requests/${encodeURIComponent(request.id)}/${action}`,
        "POST",
      );
      setRequests((current) => current.map((item) => item.id === updated.id ? updated : item));
      const actionText = action === "approve" ? "approved" : action === "decline" ? "declined" : "email retried for";
      const deliveryText = updated.notification_status_saved === false
        ? "The account decision is saved, but the email status could not be recorded. Refresh and check the customer’s inbox before retrying."
        : updated.notification_status === "failed"
          ? "The decision email failed; use Retry email."
          : updated.notification_status === "pending"
            ? "The decision is saved; email delivery status is still pending."
            : "The decision email was sent.";
      setNotice(`${request.email} ${actionText}. ${deliveryText}`);
      if (action === "approve") await onApproved();
    } catch (cause) {
      const message = cause instanceof Error ? cause.message : "Could not update the request.";
      if (action === "approve") await refresh();
      setError(message);
    } finally {
      setBusyId(null);
    }
  }

  const visible = requests.filter((request) => showHistory || request.status === "pending" || request.status === "processing" || request.notification_status === "failed");
  const pendingCount = requests.filter((request) => request.status === "pending").length;

  return (
    <section aria-labelledby="request-queue-title" className="mt-7 rounded-2xl border border-emerald-400/15 bg-emerald-400/[0.035] p-4 sm:p-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 id="request-queue-title" className="text-lg font-semibold text-white">Account requests <span className="ml-1 rounded-full bg-emerald-400/15 px-2 py-0.5 text-sm text-emerald-200">{pendingCount}</span></h2>
          <p className="mt-1 text-sm text-slate-400">Accounts are created only after you approve a request.</p>
        </div>
        <div className="flex gap-2">
          <button type="button" onClick={() => setShowHistory((value) => !value)} className="rounded-lg border border-white/15 px-3 py-2 text-xs text-slate-200 hover:bg-white/5">{showHistory ? "Hide history" : "Show history"}</button>
          <button type="button" onClick={() => void refresh()} disabled={loading} className="rounded-lg border border-white/15 px-3 py-2 text-xs text-slate-200 hover:bg-white/5 disabled:opacity-50">{loading ? "Refreshing…" : "Refresh requests"}</button>
        </div>
      </div>
      {error && <p role="alert" className="mt-4 rounded-lg border border-rose-400/25 bg-rose-400/10 p-3 text-sm text-rose-100">{error}</p>}
      {notice && <p role="status" className="mt-4 rounded-lg border border-emerald-400/20 bg-emerald-400/10 p-3 text-sm text-emerald-100">{notice}</p>}
      <div className="mt-5 grid gap-3">
        {visible.map((request) => (
          <article key={request.id} className="rounded-xl border border-white/10 bg-slate-950/60 p-4">
            <div className="flex flex-wrap items-start justify-between gap-2">
              <div>
                <h3 className="font-semibold text-white">{request.full_name}</h3>
                <p className="mt-1 break-all text-sm text-emerald-200">{request.email}</p>
              </div>
              <span className={`rounded-full px-2.5 py-1 text-xs font-medium ${request.status === "pending" ? "bg-amber-400/10 text-amber-200" : request.status === "approved" ? "bg-emerald-400/10 text-emerald-200" : "bg-white/10 text-slate-300"}`}>{request.status}</span>
            </div>
            <dl className="mt-4 grid gap-3 text-xs sm:grid-cols-2 lg:grid-cols-3">
              <div><dt className="text-slate-500">Date of birth</dt><dd className="mt-1 text-slate-200">{request.date_of_birth}</dd></div>
              <div><dt className="text-slate-500">Phone</dt><dd className="mt-1 text-slate-200">{request.phone_number}</dd></div>
              <div><dt className="text-slate-500">WhatsApp</dt><dd className="mt-1 text-slate-200">{request.whatsapp_number}</dd></div>
              <div><dt className="text-slate-500">Received</dt><dd className="mt-1 text-slate-200">{formatDate(request.created_at)}</dd></div>
              <div><dt className="text-slate-500">Decision email</dt><dd className="mt-1 text-slate-200">{request.status === "pending" ? "Waiting for decision" : request.notification_status}</dd></div>
            </dl>
            {(request.status === "pending" || request.status === "processing") && (
              <div className="mt-4 flex flex-wrap gap-2 border-t border-white/10 pt-4">
                <button type="button" disabled={busyId !== null} onClick={() => void decide(request, "approve")} className="rounded-lg bg-emerald-400 px-4 py-2 text-xs font-semibold text-slate-950 hover:bg-emerald-300 disabled:opacity-50">{busyId === request.id ? "Working…" : request.status === "processing" ? "Resume approval" : "Approve and create account"}</button>
                {request.status === "pending" && <button type="button" disabled={busyId !== null} onClick={() => void decide(request, "decline")} className="rounded-lg border border-rose-400/25 px-4 py-2 text-xs font-semibold text-rose-200 hover:bg-rose-400/10 disabled:opacity-50">Decline</button>}
              </div>
            )}
            {(request.notification_status === "failed" || ((request.status === "approved" || request.status === "declined") && request.notification_status === "pending")) && (
              <button type="button" disabled={busyId !== null} onClick={() => void decide(request, "retry-email")} className="mt-4 rounded-lg border border-amber-300/25 px-4 py-2 text-xs font-semibold text-amber-200 hover:bg-amber-300/10 disabled:opacity-50">{busyId === request.id ? "Retrying…" : "Retry email"}</button>
            )}
          </article>
        ))}
        {!loading && visible.length === 0 && <p className="rounded-xl border border-white/10 p-5 text-center text-sm text-slate-500">No account requests to review.</p>}
      </div>
    </section>
  );
}
