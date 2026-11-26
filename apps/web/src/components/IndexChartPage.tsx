"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useMemo, useState, useSyncExternalStore } from "react";
import { useAuth } from "@/components/auth/AuthProvider";
import { useIndexChart } from "./useIndexChart";
import { chartHistory, currentSignal, decisionChecks, epoch, formatPrice, formatStamp, formingBar, freshQuote } from "@/lib/indexChart";
import "./indexChart.css";

const ChartCanvas = dynamic(() => import("./IndexChartCanvas"), { ssr: false, loading: () => <div className="chart-loading" role="status">Opening chart…</div> });
type Provider = "groww" | "upstox";
const providers = { upstox: "Upstox", groww: "Groww" };
const instruments = { NIFTY50: "NIFTY 50", BANKNIFTY: "BANK NIFTY" };
type SymbolId = keyof typeof instruments;

function subscribeProvider(change: () => void) {
  window.addEventListener("storage", change);
  window.addEventListener("allsafe-market-provider-change", change);
  return () => {
    window.removeEventListener("storage", change);
    window.removeEventListener("allsafe-market-provider-change", change);
  };
}
function savedProvider(): Provider {
  try { return localStorage.getItem("allsafe-market-provider") === "groww" ? "groww" : "upstox"; }
  catch { return "upstox"; }
}
function updateQuery(provider: Provider, days?: number) {
  const url = new URL(window.location.href);
  url.searchParams.set("provider", provider);
  if (days !== undefined) url.searchParams.set("days", String(days));
  else if (provider === "groww") url.searchParams.delete("days");
  window.history.replaceState(null, "", url);
  try { localStorage.setItem("allsafe-market-provider", provider); } catch { /* URL preserves the selection. */ }
  window.dispatchEvent(new Event("allsafe-market-provider-change"));
}

function Workspace({ symbol, provider, days, token, signOut }: {
  symbol: SymbolId; provider: Provider; days: number; token: string; signOut: () => unknown;
}) {
  const { series, tick, quoteError, seriesError } = useIndexChart(symbol, provider, days, token, signOut);
  const { bars, marks } = useMemo(() => chartHistory(series), [series]);
  const [levelTime, setLevelTime] = useState("latest");
  const withLevels = useMemo(() => marks.filter(mark => mark.levels), [marks]);
  const levelMark = levelTime === "latest" ? withLevels.at(-1) : withLevels.find(mark => String(mark.time) === levelTime);
  const levels = levelMark?.levels;
  const quote = quoteError ? undefined : tick;
  const live = freshQuote(quote);
  const forming = useMemo(() => formingBar(quote, bars.at(-1)), [quote, bars]);
  const confirmed = series?.candles.findLast((c) => !c.is_forming && !c.is_incomplete && c.is_confirmed !== false);
  const feed = quoteError ? "unavailable" : quote?.feed_state ?? series?.feed_state;
  const feedText = feed === "closed" ? "Market closed" : live ? "Live" : feed === "stale" ? "Feed delayed" :
    feed === "disconnected" ? "Feed disconnected" : feed ? "Feed unavailable" : "Connecting";
  const usableQuote = live ? quote?.quote : null;
  const realPrice = usableQuote?.ltp ?? confirmed?.close;
  const priceTime = usableQuote?.timestamp ?? confirmed?.timestamp;
  const priceLabel = usableQuote ? "LTP" : "Close";
  const decision = series?.indicator_decision;
  const current = !seriesError && currentSignal(series, quote);
  const direction = decision?.decision;
  const signalText = seriesError ? "Update delayed" : direction === "BUY" || direction === "SELL" ?
    (current ? "" : "Previous ") + (direction === "BUY" ? "Buy" : "Sell") :
    direction === "WAIT" ? "Wait" : decision?.reason.toLowerCase().includes("warm") ? "Warming up" :
    decision ? "Waiting for candles" : "Loading";
  const count = decision?.confirmed_candle_count;
  const checks = decisionChecks(seriesError ? undefined : decision);
  const firstBreakout = seriesError ? null : decision?.first_breakout;
  const options = [...new Set([1, 7, 14, 30, days])].sort((a,b) => a - b);
  return <main className="index-workspace">
    <nav className="chart-top" aria-label="Chart navigation"><Link href="/terminal"><span aria-hidden="true">←</span> Market dashboard</Link>
      <span className="chart-identity">Index chart</span></nav>
    <header className="chart-heading">
      <div><div className="chart-exchange">NSE <span> / </span> INDEX</div>
        <div className="chart-title-row"><h1>{instruments[symbol]}</h1><span className={`chart-state ${live ? "live" : ""}`}>{feedText}</span></div>
      </div>
      <div className="chart-quote"><label>{usableQuote ? "Last traded price" : "Last completed close"}</label>
        <strong>{realPrice == null ? "—" : formatPrice(realPrice)}</strong>
        {priceTime && <small>{formatStamp(epoch(priceTime) + (usableQuote ? 0 : 900))} IST</small>}
      </div>
      <div className="chart-filters"><label>Market data<select id="chart-provider" value={provider} onChange={(e) => updateQuery(e.target.value as Provider)}>
        <option value="upstox">Upstox</option><option value="groww">Groww</option></select></label>
        <label>History<select value={days} onChange={(e) => updateQuery(provider, Number(e.target.value))}>
          {options.map((d) => <option key={d} value={d}>{d === 1 ? "Today" : `Last ${d} days`}</option>)}</select></label></div>
    </header>
    {(seriesError || quoteError || series?.history_warning) && <p className="chart-notice" role="alert">
      {seriesError ? "Candle and signal refresh delayed. Retrying." : series?.history_warning} {quoteError && "Quote refresh delayed. Retrying."}
    </p>}
    <ChartCanvas bars={bars} marks={marks} forming={forming} realPrice={realPrice} priceLabel={priceLabel}
      loading={!series && !seriesError} levels={levels} />
    {withLevels.length > 0 && <section className="chart-levels" aria-label="Signal price levels">
      <label>Signal levels <select value={levelTime} onChange={event => setLevelTime(event.target.value)}>
        <option value="latest">Latest confirmed signal</option>
        <option value="off">Hide levels</option>
        {[...withLevels].reverse().map(mark => <option key={mark.time} value={String(mark.time)}>
          {mark.side} · {formatStamp(mark.time)} IST
        </option>)}
      </select></label>
      {levels && levelMark && <>
        <p>{levelMark.side} · {formatStamp(levelMark.time)} IST</p>
        <dl>
          <div><dt>Reference entry</dt><dd>{formatPrice(levels.entry)}</dd></div>
          <div><dt>Stop-loss</dt><dd>{formatPrice(levels.stop_loss)}</dd></div>
          <div><dt>Target (2R)</dt><dd>{formatPrice(levels.target)}</dd></div>
        </dl>
        <small>Levels use the confirmed market candle close and the opposite opening-range boundary.</small>
      </>}
    </section>}
    <div className="chart-decision-strip">
      <div><label>{current ? "Current confirmed signal" : "Last decision"}</label><strong className={current ? (direction === "BUY" ? "chart-up" : "chart-down") : ""}>{signalText}</strong></div>
      <div><label>Evaluated candle</label><strong>{decision?.candle_timestamp ? formatStamp(epoch(decision.candle_timestamp)) + " IST" : "—"}</strong></div>
      <div><label>Confirmed bars used</label><strong>{count ?? "—"}</strong></div>
      <div><label>Data source</label><strong>{providers[provider]}</strong></div>
    </div>
    <details className="chart-checks"><summary>Signal confirmation checks</summary>
      <p>{seriesError ? "Waiting for the latest signal calculation." : decision?.reason || "Waiting for completed candles."}</p>
      <p>Each session can confirm one BUY above the opening high and one SELL below the opening low. Checks run on every completed candle through the 14:15 IST candle.</p>
      {firstBreakout && <p>
        First breakout · {firstBreakout.side} · {formatStamp(epoch(firstBreakout.timestamp))} IST · {firstBreakout.decision}. {firstBreakout.reason}
      </p>}
      <dl>{checks.map(([name, reading]) =>
        <div key={name}><dt>{name}</dt><dd>{reading}</dd></div>)}</dl>
      {!seriesError && decision?.opening_range_high != null && decision.opening_range_low != null &&
        <p>Opening range · Low {formatPrice(decision.opening_range_low)} · High {formatPrice(decision.opening_range_high)}</p>}
    </details>
    <footer className="chart-credit"><span>Heikin Ashi shows averaged prices. Signals use completed 15-minute market candles.</span>
      <a href="https://www.tradingview.com/" target="_blank" rel="noreferrer">TradingView Lightweight Charts™ © 2025 TradingView, Inc.</a></footer>
  </main>;
}

export default function IndexChartPage({ symbol }: { symbol: string }) {
  const { session, signOut } = useAuth();
  const query = useSearchParams();
  const stored = useSyncExternalStore(subscribeProvider, savedProvider, () => "upstox" as Provider);
  const requested = query.get("provider");
  const provider = requested === "groww" || requested === "upstox" ? requested : stored;
  const value = Number(query.get("days"));
  const days = Number.isInteger(value) && value > 0 && value <= 30 ? value : 7;
  if (symbol !== "NIFTY50" && symbol !== "BANKNIFTY") return <main><h1>Chart unavailable</h1><Link href="/terminal">Market dashboard</Link></main>;
  if (!session) return null;
  return <Workspace key={JSON.stringify([session.user.id, symbol, provider, days])} symbol={symbol} provider={provider}
    days={days} token={session.access_token} signOut={signOut}/>;
}
