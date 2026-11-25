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
      className="as-panel m-auto max-h-[85dvh] w-[calc(100%-1.5rem)] max-w-lg overflow-y-auto p-5 text-slate-200 shadow-2xl backdrop:bg-black/75 sm:p-6"
    >
      <h2 id="customer-message-title" className="as-section-title">
        {pause ? "Pause customer login" : email ? "Send a warning" : "Warn all customers"}
      </h2>
      <p id="customer-message-audience" className="mt-1 break-words text-sm text-slate-400">{email ?? "All current customer accounts"}</p>
      <form onSubmit={submit} className="mt-5 grid gap-4">
        <label className="block text-sm font-medium text-slate-200">
          {pause ? "Reason for pausing" : "Warning message"}
          <textarea value={message} onChange={(event) => setMessage(event.target.value)} required
            maxLength={messageLimit} rows={5} disabled={saving} autoFocus
            className="as-field mt-2 min-h-28 w-full resize-y"/>
        </label>
        <div className="flex flex-wrap justify-between gap-2 text-xs text-slate-400">
          <p>{pause ? "The customer will see this reason at sign-in." : "Customers will see this warning in AllSafe."}</p>
          <span>{message.length}/{messageLimit}</span>
        </div>
        {error && <p role="alert" className="text-sm text-rose-200">{error}</p>}
        <div className="flex flex-wrap justify-end gap-2">
          <button type="button" disabled={saving} onClick={onClose} className="as-button as-button--quiet">Cancel</button>
          <button type="submit" disabled={saving || !message.trim()} className="as-button as-button--amber">
            {saving ? "Saving…" : actionLabel}
          </button>
        </div>
      </form>
    </dialog>
  );
}
