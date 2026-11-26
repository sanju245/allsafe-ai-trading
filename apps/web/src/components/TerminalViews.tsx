"use client";

import { Activity, useState, type ReactNode } from "react";

export default function TerminalViews({ live, history }: { live: ReactNode; history: ReactNode }) {
  const [view, setView] = useState<"live" | "history">("live");
  const liveSelected = view === "live";
  return (
    <>
      <div className="as-view-switcher terminal-views" role="group" aria-label="Market dashboard view">
        <button type="button" aria-pressed={liveSelected} aria-controls="live-index-charts" onClick={() => setView("live")}>Live overview</button>
        <button type="button" aria-pressed={!liveSelected} aria-controls="historical-charts" onClick={() => setView("history")}>Historical candles</button>
      </div>
      <section id="live-index-charts" aria-label="Live index charts" hidden={!liveSelected}><Activity mode={liveSelected ? "visible" : "hidden"}>{live}</Activity></section>
      <section id="historical-charts" aria-label="Historical index charts" hidden={liveSelected}><Activity mode={liveSelected ? "hidden" : "visible"}>{history}</Activity></section>
    </>
  );
}
