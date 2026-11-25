"use client";

import Link from "next/link";
import { useState, type FormEvent } from "react";

const api = (process.env.NEXT_PUBLIC_API_BASE_URL ||
  (process.env.NODE_ENV === "production" ? "https://allsafe-ai-api.onrender.com" : "http://localhost:8000")).replace(/\/+$/, "");

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [status, setStatus] = useState<"idle" | "sending" | "sent" | "error">("idle");

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setStatus("sending");
    try {
      const response = await fetch(`${api}/api/v1/auth/password/recover`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: email.trim() }),
        signal: AbortSignal.timeout(15000),
      });
      setStatus(response.ok ? "sent" : "error");
    } catch {
      setStatus("error");
    }
  }

  return <main className="mx-auto flex min-h-screen max-w-xl flex-col justify-center px-4 py-10">
    <Link href="/" className="mb-6 text-sm font-semibold text-emerald-300">AllSafe AI Trading</Link>
    <section className="rounded-2xl border border-white/10 bg-white/[0.025] p-6 sm:p-8">
      <h1 className="text-3xl font-semibold text-white">Reset your password</h1>
      {status === "sent" ?
        <p role="status" className="mt-4 text-slate-300">If the email has an active AllSafe account, it will receive a password reset link.</p> :
        <form onSubmit={submit} className="mt-5 grid gap-4">
          <label className="text-sm text-slate-300">Account email
            <input type="email" required maxLength={254} autoComplete="email" value={email}
              onChange={event => setEmail(event.target.value)}
              className="mt-1 block w-full rounded-lg border border-white/15 bg-slate-950 px-3 py-2.5 text-white" />
          </label>
          {status === "error" && <p role="alert" className="text-sm text-rose-200">The request could not be sent. Try again shortly.</p>}
          <button type="submit" disabled={status === "sending"} className="rounded-lg bg-emerald-400 px-4 py-2.5 font-semibold text-slate-950 disabled:opacity-50">
            {status === "sending" ? "Requesting…" : "Send reset link"}
          </button>
        </form>}
      <Link href="/login" className="mt-5 inline-block text-sm font-semibold text-emerald-300 underline">Back to sign in</Link>
    </section>
  </main>;
}
