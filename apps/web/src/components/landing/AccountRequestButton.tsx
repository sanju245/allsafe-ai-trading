"use client";

import Link from "next/link";
import { useEffect, useRef, useState, type FormEvent } from "react";

const API_BASE_URL = (
  process.env.NEXT_PUBLIC_API_BASE_URL ||
  (process.env.NODE_ENV === "production" ? "https://allsafe-ai-api.onrender.com" : "http://localhost:8000")
).trim().replace(/\/+$/, "");

async function errorMessage(response: Response): Promise<string> {
  try {
    const body: unknown = await response.json();
    if (typeof body === "object" && body !== null && "detail" in body) {
      const detail = (body as { detail: unknown }).detail;
      if (typeof detail === "string") return detail;
    }
  } catch { /* Show the generic message below. */ }
  return `Could not submit the request (HTTP ${response.status}).`;
}

export default function AccountRequestButton() {
  const [open, setOpen] = useState(false);
  const trigger = useRef<HTMLButtonElement>(null);
  const dialog = useRef<HTMLDialogElement>(null);
  const [fullName, setFullName] = useState("");
  const [dateOfBirth, setDateOfBirth] = useState("");
  const [email, setEmail] = useState("");
  const [phoneNumber, setPhoneNumber] = useState("");
  const [whatsappNumber, setWhatsappNumber] = useState("");
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [codeEmail, setCodeEmail] = useState("");
  const [emailCode, setEmailCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [submitted, setSubmitted] = useState(false);
  const [resultMessage, setResultMessage] = useState("");
  const address = email.trim().toLowerCase();
  const awaitingCode = Boolean(codeEmail && address === codeEmail);

  useEffect(() => {
    const panel = dialog.current;
    const opener = trigger.current;
    if (!open || !panel) return;
    panel.showModal();
    panel.querySelector("input")?.focus();
    return () => {
      panel.close();
      opener?.focus();
    };
  }, [open]);

  function close() {
    setPassword("");
    setConfirmation("");
    setEmailCode("");
    setCodeEmail("");
    setOpen(false);
  }

  async function sendCode() {
    const response = await fetch(`${API_BASE_URL}/api/v1/account-requests/email-code`, {
      method: "POST",
      headers: { Accept: "application/json", "Content-Type": "application/json" },
      body: JSON.stringify({ email: address }),
      cache: "no-store",
      credentials: "omit",
    });
    if (!response.ok) throw new Error(await errorMessage(response));
    setCodeEmail(address);
    setEmailCode("");
  }

  async function resendCode() {
    setBusy(true);
    setError(null);
    try {
      await sendCode();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not send the verification code.");
    } finally {
      setBusy(false);
    }
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    if (password !== confirmation) {
      setError("Passwords do not match.");
      return;
    }
    if (Array.from(password).length < 8 || new TextEncoder().encode(password).length > 72) {
      setError("Use at least 8 characters and 72 bytes or fewer. Some characters use more than one byte.");
      return;
    }
    if (!awaitingCode) {
      await resendCode();
      return;
    }
    setBusy(true);
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/account-requests`, {
        method: "POST",
        headers: { Accept: "application/json", "Content-Type": "application/json" },
        body: JSON.stringify({
          full_name: fullName.trim(),
          date_of_birth: dateOfBirth,
          email: address,
          phone_number: phoneNumber.trim(),
          whatsapp_number: whatsappNumber.trim(),
          password,
          email_code: emailCode,
        }),
        cache: "no-store",
        credentials: "omit",
      });
      if (!response.ok) throw new Error(await errorMessage(response));
      const body: unknown = await response.json();
      const message = typeof body === "object" && body !== null && "message" in body
        ? (body as { message: unknown }).message : null;
      setResultMessage(typeof message === "string" ? message : "Your request is awaiting administrator review.");
      setSubmitted(true);
      setFullName("");
      setDateOfBirth("");
      setEmail("");
      setPhoneNumber("");
      setWhatsappNumber("");
      setPassword("");
      setConfirmation("");
      setEmailCode("");
      setCodeEmail("");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not submit the request.");
    } finally {
      setBusy(false);
    }
  }

  const inputClass = "mt-1 block w-full rounded-lg border border-white/15 bg-[#0b1118] px-3 py-2.5 text-sm text-white outline-none focus:border-emerald-400";
  return (
    <>
      <button ref={trigger} type="button" onClick={() => { setSubmitted(false); setError(null); setOpen(true); }} className="inline-flex min-h-12 items-center justify-center rounded-xl border border-emerald-300/40 bg-emerald-300/10 px-6 py-3 text-sm font-semibold text-emerald-200 transition hover:bg-emerald-300/20 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-300">
        Create account with us
      </button>
      {open && (
        <dialog ref={dialog} aria-labelledby="account-request-title" onCancel={(event) => {
          event.preventDefault();
          if (!busy) close();
        }} className="fixed inset-0 m-auto max-h-[90dvh] w-[calc(100%_-_2rem)] max-w-2xl overflow-y-auto rounded-2xl border border-white/15 bg-[#101820] p-5 shadow-2xl backdrop:bg-black/80 sm:p-8">
            <div className="flex items-start justify-between gap-4">
              <div>
                <p className="text-xs font-semibold uppercase tracking-widest text-emerald-300">Customer access</p>
                <h2 id="account-request-title" className="mt-2 text-2xl font-semibold text-white">Request an account</h2>
              </div>
              <button type="button" aria-label="Close request form" disabled={busy} onClick={close} className="rounded-lg border border-white/15 px-3 py-1.5 text-slate-300 hover:text-white disabled:opacity-50">✕</button>
            </div>
            {submitted ? (
              <div role="status" className="mt-6 rounded-xl border border-emerald-400/20 bg-emerald-400/10 p-5 text-sm leading-6 text-emerald-100">
                {resultMessage} We’ll send sign-in instructions if your request is approved.
              </div>
            ) : (
              <>
                <p className="mt-3 text-sm leading-6 text-slate-400">Choose a password and verify your email address to submit your request. After approval, use that email and password to sign in.</p>
                <form onSubmit={submit} className="mt-6 grid gap-4 sm:grid-cols-2">
                  <label className="text-sm text-slate-300">Full name
                    <input className={inputClass} type="text" autoComplete="name" required maxLength={120} value={fullName} onChange={(event) => setFullName(event.target.value)} />
                  </label>
                  <label className="text-sm text-slate-300">Date of birth
                    <input className={inputClass} type="date" autoComplete="bday" required max={new Date().toISOString().slice(0, 10)} value={dateOfBirth} onChange={(event) => setDateOfBirth(event.target.value)} />
                  </label>
                  <label className="text-sm text-slate-300 sm:col-span-2">Email
                    <input className={inputClass} type="email" autoComplete="email" required maxLength={254} value={email} onChange={(event) => setEmail(event.target.value)} />
                  </label>
                  <label className="text-sm text-slate-300">Phone number
                    <input className={inputClass} type="tel" autoComplete="tel" required maxLength={20} value={phoneNumber} onChange={(event) => setPhoneNumber(event.target.value)} />
                  </label>
                  <label className="text-sm text-slate-300">WhatsApp number
                    <input className={inputClass} type="tel" required maxLength={20} value={whatsappNumber} onChange={(event) => setWhatsappNumber(event.target.value)} />
                  </label>
                  <div>
                    <label className="text-sm text-slate-300">Password
                      <input className={inputClass} name="password" type="password" autoComplete="new-password" aria-describedby="account-request-password-help" required minLength={8} maxLength={72} value={password} onChange={(event) => setPassword(event.target.value)} />
                    </label>
                    <p id="account-request-password-help" className="mt-1 text-xs text-slate-400">Use at least 8 characters.</p>
                  </div>
                  <label className="text-sm text-slate-300">Confirm password
                    <input className={inputClass} name="confirm-password" type="password" autoComplete="new-password" required minLength={8} maxLength={72} value={confirmation} onChange={(event) => setConfirmation(event.target.value)} />
                  </label>
                  {awaitingCode && (
                    <div className="rounded-lg border border-white/15 p-3 sm:col-span-2">
                      <p role="status" className="text-sm text-slate-300">Enter the verification code we emailed to {codeEmail}.</p>
                      <div className="mt-3 flex flex-wrap items-end gap-3">
                        <label className="min-w-40 flex-1 text-sm text-slate-300">Email verification code
                          <input className={inputClass} name="email-code" type="text" autoComplete="one-time-code" autoCapitalize="characters" spellCheck={false} required pattern="[A-Z2-7]{8}" maxLength={8} value={emailCode} onChange={(event) => setEmailCode(event.target.value.trim().toUpperCase())} />
                        </label>
                        <button type="button" disabled={busy} onClick={() => void resendCode()} className="rounded-lg border border-white/15 px-3 py-2.5 text-sm text-emerald-300 hover:bg-white/5 disabled:opacity-50">Resend code</button>
                      </div>
                    </div>
                  )}
                  {error && <p role="alert" className="rounded-lg border border-rose-400/25 bg-rose-400/10 p-3 text-sm text-rose-100 sm:col-span-2">{error}</p>}
                  <p className="text-xs leading-5 text-slate-500 sm:col-span-2">We use these details to review your request and email a decision. See our <Link href="/privacy" className="text-emerald-300 underline">Privacy Policy</Link>.</p>
                  <button type="submit" disabled={busy} className="rounded-lg bg-emerald-400 px-5 py-3 text-sm font-semibold text-slate-950 hover:bg-emerald-300 disabled:cursor-wait disabled:opacity-60 sm:col-span-2">{busy ? "Please wait…" : awaitingCode ? "Verify email and submit request" : "Send email verification code"}</button>
                </form>
              </>
            )}
        </dialog>
      )}
    </>
  );
}
