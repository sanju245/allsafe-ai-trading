"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";

const messageLimit = 1000;

export default function CustomerMessageDialog({
  action, email, save, onClose,
}: {
  action: "warning" | "pause";
  email: string | null;
  save: (message: string, requestId: string) => Promise<void>;
  onClose: () => void;
}) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const attempt = useRef<{ message: string; id: string } | null>(null);
  const pending = useRef(false);
  const [message, setMessage] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const pause = action === "pause";
  const actionLabel = pause ? "Pause login" : email ? "Send warning" : "Send to all customers";

  useEffect(() => {
    const dialog = dialogRef.current;
    dialog?.showModal();
    return () => dialog?.close();
  }, []);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const text = message.trim();
    if (!text || pending.current) return;
    if (attempt.current?.message !== text) attempt.current = { message: text, id: crypto.randomUUID() };
    pending.current = true;
    setSaving(true);
    setError(null);
    try {
      await save(text, attempt.current.id);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "The account service could not confirm the change.");
    } finally {
      pending.current = false;
      setSaving(false);
    }
  }

  return (
    <dialog
      ref={dialogRef}
      aria-labelledby="customer-message-title"
      aria-describedby="customer-message-audience"
      onCancel={(event) => { event.preventDefault(); if (!pending.current) onClose(); }}
      className="m-auto max-h-[85dvh] w-[calc(100%-1.5rem)] max-w-lg overflow-y-auto rounded-2xl border border-white/15 bg-slate-900 p-5 text-slate-200 shadow-2xl backdrop:bg-black/75 sm:p-6"
    >
      <h2 id="customer-message-title" className="text-lg font-semibold text-white">
        {pause ? "Pause customer login" : email ? "Send a warning" : "Warn all customers"}
      </h2>
      <p id="customer-message-audience" className="mt-1 break-words text-sm text-slate-400">{email ?? "All current customer accounts"}</p>
      <form onSubmit={submit} className="mt-5 grid gap-4">
        <label className="block text-sm font-medium text-slate-200">
          {pause ? "Reason for pausing" : "Warning message"}
          <textarea value={message} onChange={(event) => setMessage(event.target.value)} required
            maxLength={messageLimit} rows={5} disabled={saving} autoFocus
            className="mt-2 block min-h-28 w-full resize-y rounded-lg border border-white/15 bg-slate-950 px-3 py-2.5 text-sm leading-relaxed text-white outline-none focus:border-amber-300/70"/>
        </label>
        <div className="flex flex-wrap justify-between gap-2 text-xs text-slate-400">
          <p>{pause ? "The customer will see this reason at sign-in." : "Customers will see this warning in AllSafe."}</p>
          <span>{message.length}/{messageLimit}</span>
        </div>
        {error && <p role="alert" className="text-sm text-rose-200">{error}</p>}
        <div className="flex flex-wrap justify-end gap-2">
          <button type="button" disabled={saving} onClick={onClose} className="rounded-lg border border-white/15 px-4 py-2 text-sm hover:bg-white/5 disabled:opacity-60">Cancel</button>
          <button type="submit" disabled={saving || !message.trim()} className="rounded-lg bg-amber-300 px-4 py-2 text-sm font-semibold text-slate-950 hover:bg-amber-200 disabled:opacity-50">
            {saving ? "Saving…" : actionLabel}
          </button>
        </div>
      </form>
    </dialog>
  );
}
