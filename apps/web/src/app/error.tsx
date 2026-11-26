"use client";

import { useEffect } from "react";

const RELOAD_FLAG = "allsafe-auto-reload-once";

function looksLikeStaleChunk(error: Error): boolean {
  const text = `${error.name} ${error.message}`.toLowerCase();
  return (
    text.includes("chunkloaderror") ||
    text.includes("loading chunk") ||
    text.includes("failed to fetch dynamically imported module") ||
    text.includes("importing a module script failed")
  );
}

export default function GlobalError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => {
    // A fresh deploy rotates build chunk hashes. A tab that was already open (or loaded
    // from a stale cache) can fail to load a lazy chunk - e.g. the chart canvas, which is
    // dynamically imported - and crash the page with nothing visible, since there was no
    // error boundary to catch it. Reload once automatically to pick up the current build;
    // a sessionStorage flag stops a real repeated failure from reload-looping forever.
    if (looksLikeStaleChunk(error) && !sessionStorage.getItem(RELOAD_FLAG)) {
      sessionStorage.setItem(RELOAD_FLAG, "1");
      window.location.reload();
    }
  }, [error]);

  return (
    <main style={{ minHeight: "100dvh", display: "grid", placeItems: "center", padding: "24px", background: "#f2f5ef", color: "#152d25", fontFamily: "Inter, Arial, sans-serif" }}>
      <div style={{ maxWidth: 420, textAlign: "center" }}>
        <h1 style={{ fontSize: 22, fontWeight: 700, marginBottom: 8 }}>Something went wrong</h1>
        <p style={{ color: "#53695e", fontSize: 14, lineHeight: 1.5, marginBottom: 16 }}>
          This page hit an unexpected error while loading. Try again, or reload the page.
        </p>
        <div style={{ display: "flex", gap: 10, justifyContent: "center" }}>
          <button onClick={() => reset()} style={{ minHeight: 44, padding: "8px 16px", borderRadius: 10, border: "1px solid #bfcebf", background: "#fffefa", color: "#152d25", cursor: "pointer", fontWeight: 600 }}>
            Try again
          </button>
          <button onClick={() => window.location.reload()} style={{ minHeight: 44, padding: "8px 16px", borderRadius: 10, border: "1px solid #1e634a", background: "#1e634a", color: "#fff", cursor: "pointer", fontWeight: 600 }}>
            Reload page
          </button>
        </div>
      </div>
    </main>
  );
}
