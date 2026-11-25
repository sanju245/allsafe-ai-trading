"use client";

import { useEffect, useRef, useState } from "react";

export type SignInEntry = {
  signed_in_at: string;
  ip_address: string | null;
};

type HistoryState =
  | { entries: SignInEntry[] }
  | { error: string }
  | null;

const loginTime = new Intl.DateTimeFormat("en-IN", {
  year: "numeric",
  month: "short",
  day: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
  hourCycle: "h23",
  timeZone: "Asia/Kolkata",
});

export default function CustomerSignInHistory({
  email, load, onClose,
}: {
  email: string;
  load: (signal: AbortSignal) => Promise<SignInEntry[]>;
  onClose: () => void;
}) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const [history, setHistory] = useState<HistoryState>(null);
  const [refresh, setRefresh] = useState(0);

  useEffect(() => {
    const dialog = dialogRef.current;
    dialog?.showModal();
    return () => dialog?.close();
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    void load(controller.signal).then((entries) => {
      if (!controller.signal.aborted) setHistory({ entries });
    }).catch((cause: unknown) => {
      if (!controller.signal.aborted) {
        setHistory({ error: cause instanceof Error ? cause.message : "Could not load sign-in history." });
      }
    });
    return () => controller.abort();
  }, [load, refresh]);

  const entries = history && "entries" in history ? history.entries : [];
  const addresses = new Set(entries.flatMap(({ ip_address }) => ip_address ? [ip_address] : []));
  const latest = entries[0]?.ip_address;
  const previous = entries[1]?.ip_address;
  const ipChanged = latest && previous && latest !== previous;

  return (
    <dialog
      ref={dialogRef}
      aria-labelledby="sign-in-history-title"
      aria-describedby="sign-in-history-account"
      onCancel={(event) => { event.preventDefault(); onClose(); }}
      className="m-auto max-h-[85dvh] w-[calc(100%-1.5rem)] max-w-xl overflow-y-auto rounded-2xl border border-white/15 bg-slate-900 text-slate-200 shadow-2xl backdrop:bg-black/75"
    >
      <div className="flex items-start justify-between gap-4 border-b border-white/10 px-4 py-4 sm:px-6">
        <div className="min-w-0">
          <h2 id="sign-in-history-title" className="text-lg font-semibold text-white">Sign-in history</h2>
          <p id="sign-in-history-account" className="mt-1 break-all text-sm text-slate-400">{email}</p>
        </div>
        <button type="button" aria-label="Close sign-in history" onClick={onClose} className="shrink-0 rounded-lg border border-white/15 px-3 py-2 text-xs font-medium text-slate-200 hover:bg-white/5">Close</button>
      </div>
      <div className="space-y-4 px-4 py-4 sm:px-6">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <p className="text-sm text-slate-400">Last 10 successful sign-ins</p>
          <button type="button" disabled={!history} onClick={() => {
            setHistory(null);
            setRefresh((value) => value + 1);
          }} className="rounded-lg border border-white/15 px-3 py-2 text-xs font-medium hover:bg-white/5 disabled:opacity-50">Refresh history</button>
        </div>
        {!history && <p role="status" className="py-5 text-sm text-slate-400">Loading sign-in history…</p>}
        {history && "error" in history && <p role="alert" className="text-sm text-rose-200">{history.error}</p>}
        {history && "entries" in history && (entries.length === 0 ? (
          <p className="rounded-lg border border-white/10 p-4 text-sm text-slate-300">No sign-ins recorded for this customer yet.</p>
        ) : (
          <>
            <p className="text-sm text-slate-200">
              {addresses.size} distinct {addresses.size === 1 ? "IP address" : "IP addresses"} across {entries.length} {entries.length === 1 ? "sign-in" : "sign-ins"}
            </p>
            {ipChanged && (
              <p className="rounded-lg border border-amber-400/20 bg-amber-400/10 px-3 py-2 text-sm text-amber-100">
                The IP address changed since the previous sign-in. Switching networks or using a VPN can also change it.
              </p>
            )}
            <table className="w-full table-fixed text-left text-sm">
              <thead className="border-b border-white/10 text-xs text-slate-400">
                <tr>
                  <th scope="col" className="w-[45%] pb-2 pr-2 font-medium">Sign-in time (IST)</th>
                  <th scope="col" className="pb-2 font-medium">IP address</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/5">
                {entries.map((entry, index) => (
                  <tr key={`${entry.signed_in_at}-${index}`}>
                    <td className="py-2.5 pr-2 tabular-nums">
                      <time dateTime={entry.signed_in_at}>{loginTime.format(new Date(entry.signed_in_at))}</time>
                    </td>
                    <td className="break-all py-2.5 font-mono text-xs">{entry.ip_address ?? "Unavailable"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        ))}
      </div>
    </dialog>
  );
}
