"use client";

import { memo, useState } from "react";
import Link from "next/link";
import { useAuth } from "@/components/auth/AuthProvider";
import BullBearHeroArena from "@/components/landing/BullBearHeroArena";
import IndianMarketStatusBadge from "@/components/landing/IndianMarketStatusBadge";
import LiveIstClock from "@/components/landing/LiveIstClock";
import AccountRequestButton from "@/components/landing/AccountRequestButton";

export interface LandingPageProps {
  serverTimeUtc?: string | null;
  backendOnline?: boolean;
  backendVersion?: string;
}

type ExampleMode = "BUY" | "SELL" | "WAIT";
const CREATOR_NAME = "Sanjesh Singh";
const CONTRIBUTION_AMOUNT = 250;
const CONTRIBUTION_UPI_ID = "8240770247@upi";
const CONTRIBUTION_QUERY = new URLSearchParams({
  pa: CONTRIBUTION_UPI_ID,
  pn: CREATOR_NAME,
  am: CONTRIBUTION_AMOUNT.toFixed(2),
  cu: "INR",
  tn: "AllSafe AI Trading contribution",
}).toString().replaceAll("+", "%20");

const CHECK_NAMES = [
  "Candidate direction",
  "Trend agreement",
  "Momentum range",
  "Momentum direction",
  "Final trend filter",
];

const EXAMPLES: Record<ExampleMode, { summary: string; checks: string[] }> = {
  BUY: {
    summary: "A candidate BUY direction and four matching confirmations produce a BUY analysis output.",
    checks: ["BUY candidate", "Confirms BUY", "Confirms BUY", "Confirms BUY", "Confirms BUY"],
  },
  SELL: {
    summary: "A candidate SELL direction and four matching confirmations produce a SELL analysis output.",
    checks: ["SELL candidate", "Confirms SELL", "Confirms SELL", "Confirms SELL", "Confirms SELL"],
  },
  WAIT: {
    summary: "When the required checks disagree, the analysis output is WAIT. Missing history is reported separately as DATA_UNAVAILABLE.",
    checks: ["BUY candidate", "Confirms BUY", "No agreement", "Confirms BUY", "No agreement"],
  },
};

const FEATURES = [
  {
    title: "Confirmed candle analysis",
    text: "Review completed 15-minute candles for NIFTY 50 and BANK NIFTY. The candle still forming is kept separate.",
  },
  {
    title: "A clear decision state",
    text: "One rule engine checks a candidate direction against four confirmations and reports BUY, SELL, WAIT, or DATA_UNAVAILABLE.",
  },
  {
    title: "Visible feed status",
    text: "Check whether market data is connected and current before interpreting an analysis output. Stale or unavailable data is identified.",
  },
];

function LandingPage({
  serverTimeUtc = null,
  backendOnline = false,
}: LandingPageProps) {
  const { session } = useAuth();
  const [exampleMode, setExampleMode] = useState<ExampleMode>("WAIT");
  const parsedEpoch = serverTimeUtc ? Date.parse(serverTimeUtc) : Number.NaN;
  const initialEpochMs = Number.isFinite(parsedEpoch) ? parsedEpoch : undefined;
  const [serverTimeOffsetMs] = useState(() =>
    initialEpochMs === undefined ? 0 : initialEpochMs - Date.now(),
  );
  const example = EXAMPLES[exampleMode];

  return (
    <div className="min-h-screen bg-[#06090f] text-slate-100 selection:bg-emerald-500/30">
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:fixed focus:left-3 focus:top-3 focus:z-50 focus:rounded-lg focus:bg-emerald-400 focus:px-4 focus:py-3 focus:text-slate-950"
      >
        Skip to main content
      </a>

      <header className="border-b border-white/10 bg-[#06090f]/95">
        <nav aria-label="Primary navigation" className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-4 px-4 py-5 sm:px-6 lg:px-8">
          <Link href="/" aria-label="AllSafe AI Trading home" className="flex items-center gap-3 rounded-lg focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-emerald-400">
            <span aria-hidden="true" className="flex h-10 w-10 items-center justify-center rounded-xl border border-emerald-500/30 bg-emerald-500/10 font-mono font-bold text-emerald-300">AS</span>
            <span className="text-lg font-bold tracking-tight">AllSafe <span className="text-emerald-400">AI Trading</span></span>
          </Link>
          <div className="flex flex-wrap items-center gap-x-5 gap-y-3 text-sm">
            <Link href="/what-we-done" className="rounded py-2 text-slate-300 hover:text-white focus-visible:outline-2 focus-visible:outline-emerald-400">How It Works</Link>
            <a href="#dashboard-preview" className="rounded py-2 text-slate-300 hover:text-white focus-visible:outline-2 focus-visible:outline-emerald-400">Preview</a>
            <a href="#contribute" className="rounded py-2 text-slate-300 hover:text-white focus-visible:outline-2 focus-visible:outline-emerald-400">Contribute</a>
            <Link href={session ? "/terminal" : "/login"} className="rounded-lg bg-emerald-400 px-4 py-2.5 font-semibold text-slate-950 hover:bg-emerald-300 focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-emerald-300">
              {session ? "Open Terminal" : "Customer Sign In"}
            </Link>
          </div>
        </nav>
      </header>

      <main id="main-content">
        <section className="relative overflow-hidden border-b border-white/10">
          <div aria-hidden="true" className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_top_left,rgba(16,185,129,0.12),transparent_60%)]" />
          <div className="relative mx-auto grid max-w-7xl items-center gap-10 px-4 py-14 sm:px-6 sm:py-20 lg:grid-cols-[0.9fr_1.1fr] lg:px-8">
            <div>
              <p className="font-mono text-xs font-semibold uppercase tracking-[0.2em] text-emerald-300">NIFTY 50 · BANK NIFTY</p>
              <h1 className="mt-5 max-w-2xl text-4xl font-bold leading-tight tracking-tight sm:text-5xl">A clearer view of the market. <span className="text-emerald-400">One confirmed candle at a time.</span></h1>
              <p className="mt-6 max-w-xl text-base leading-relaxed text-slate-300">Review index candles, feed freshness, and rule-based analysis in one terminal. Every output remains under your supervision. No broker orders are placed.</p>
              <div className="mt-8 flex flex-wrap gap-3">
                <Link href={session ? "/terminal" : "/login"} className="rounded-xl bg-emerald-400 px-6 py-3.5 text-sm font-bold text-slate-950 hover:bg-emerald-300 focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-emerald-300">{session ? "Open Terminal" : "Customer Sign In"}</Link>
                <AccountRequestButton />
                <Link href="/what-we-done" className="rounded-xl border border-white/20 px-6 py-3.5 text-sm font-semibold text-white hover:bg-white/5 focus-visible:outline-2 focus-visible:outline-emerald-400">Explore how the analysis works</Link>
              </div>
              <p className="mt-5 text-xs leading-relaxed text-slate-500">Account requests are reviewed by an administrator. Market analysis is informational and can be wrong or delayed.</p>
            </div>
            <BullBearHeroArena />
          </div>

          <div className="mx-auto grid max-w-7xl gap-3 px-4 pb-10 sm:px-6 md:grid-cols-3 lg:px-8">
            <LiveIstClock initialEpochMs={initialEpochMs} serverTimeOffsetMs={serverTimeOffsetMs} />
            <IndianMarketStatusBadge initialEpochMs={initialEpochMs} serverTimeOffsetMs={serverTimeOffsetMs} />
            <div className="rounded-xl border border-white/10 bg-[#0b1018]/90 px-4 py-3">
              <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-slate-400">Account service</p>
              <p className={`mt-2 font-mono text-lg font-semibold ${backendOnline ? "text-emerald-300" : "text-amber-200"}`}>{backendOnline ? "Reachable" : "Currently unavailable"}</p>
              <p className="mt-1 text-xs leading-relaxed text-slate-400">The session schedule above is a calendar estimate. Provider connectivity is shown separately in the terminal.</p>
            </div>
          </div>
        </section>

        <section id="features" className="mx-auto max-w-7xl px-4 py-14 sm:px-6 sm:py-20 lg:px-8">
          <p className="font-mono text-xs uppercase tracking-[0.2em] text-emerald-300">A focused analysis workspace</p>
          <h2 className="mt-3 text-3xl font-bold tracking-tight">Know what each result is based on.</h2>
          <div className="mt-8 grid gap-4 md:grid-cols-3">
            {FEATURES.map((feature, index) => (
              <article key={feature.title} className="rounded-2xl border border-white/10 bg-[#0b1018] p-6">
                <p aria-hidden="true" className="font-mono text-sm text-emerald-400">0{index + 1}</p>
                <h3 className="mt-5 text-lg font-semibold">{feature.title}</h3>
                <p className="mt-3 text-sm leading-relaxed text-slate-400">{feature.text}</p>
              </article>
            ))}
          </div>
        </section>

        <section id="dashboard-preview" className="border-y border-white/10 bg-[#080c14]">
          <div className="mx-auto max-w-7xl px-4 py-14 sm:px-6 sm:py-20 lg:px-8">
            <div className="max-w-2xl">
              <p className="font-mono text-xs uppercase tracking-[0.16em] text-emerald-300">ILLUSTRATIVE TERMINAL SIMULATION</p>
              <h2 className="mt-3 text-3xl font-bold tracking-tight">Explore a decision, step by step.</h2>
              <p className="mt-4 text-sm leading-relaxed text-slate-400">Select a static example to see how five checks contribute to the result. This preview contains no current market quote or trading instruction.</p>
              <p className="mt-3 inline-block rounded border border-amber-500/25 bg-amber-500/10 px-3 py-1.5 font-mono text-[11px] text-amber-200">NOT LIVE MARKET PRICES</p>
            </div>
            <div className="mt-8 grid gap-6 rounded-2xl border border-white/10 bg-[#06090f] p-5 sm:p-8 lg:grid-cols-[0.7fr_1.3fr]">
              <div>
                <fieldset>
                  <legend className="text-sm font-semibold text-slate-300">Choose an example</legend>
                  <div className="mt-3 flex flex-wrap gap-2">
                    {(["WAIT", "BUY", "SELL"] as const).map((mode) => (
                      <button type="button" key={mode} aria-pressed={exampleMode === mode} onClick={() => setExampleMode(mode)} className={`min-h-11 rounded-lg border px-4 py-2 font-mono text-sm font-semibold focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-300 ${exampleMode === mode ? "border-emerald-400/60 bg-emerald-400/10 text-emerald-200" : "border-white/15 text-slate-400 hover:bg-white/5"}`}>{mode}</button>
                    ))}
                  </div>
                </fieldset>
                <div aria-live="polite" aria-atomic="true" className="mt-6">
                  <p className="text-xs uppercase tracking-wider text-slate-500">Example result</p>
                  <p className="mt-2 font-mono text-3xl font-bold text-white">{exampleMode}</p>
                  <p className="mt-3 text-sm leading-relaxed text-slate-400">{example.summary}</p>
                </div>
              </div>
              <ol aria-label="Five example signal checks" className="space-y-2">
                {CHECK_NAMES.map((name, index) => (
                  <li key={name} className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-white/10 bg-[#0b1018] p-4 text-sm">
                    <span><span aria-hidden="true" className="mr-3 font-mono text-xs text-emerald-400">0{index + 1}</span>{name}</span>
                    <span className="font-mono text-xs text-slate-400">{example.checks[index]}</span>
                  </li>
                ))}
              </ol>
            </div>
            <p className="mt-5 text-xs leading-relaxed text-slate-500">The terminal evaluates actual available candle history. This example does not calculate account-specific position size, entry prices, stop losses, or profit targets.</p>
          </div>
        </section>

        <section id="access" className="mx-auto grid max-w-7xl gap-8 px-4 py-14 sm:px-6 sm:py-20 lg:grid-cols-2 lg:px-8">
          <div>
            <p className="font-mono text-xs uppercase tracking-[0.2em] text-emerald-300">Your account, your workspace</p>
            <h2 className="mt-3 text-3xl font-bold tracking-tight">Access for customers and administrators.</h2>
            <p className="mt-4 text-sm leading-relaxed text-slate-400">Customers sign in with an active account provided by the administrator and can access it from any network.</p>
            <p className="mt-3 text-sm leading-relaxed text-slate-400">Administrator tools remain available only to accounts assigned the admin role.</p>
            <div className="mt-6 flex flex-wrap gap-4">
              <Link href="/login" className="rounded-lg border border-emerald-400/30 px-5 py-3 text-sm font-semibold text-emerald-300 hover:bg-emerald-400/5 focus-visible:outline-2 focus-visible:outline-emerald-400">Customer Sign In</Link>
              <Link href="/admin/login" className="rounded-lg border border-white/15 px-5 py-3 text-sm font-semibold text-slate-300 hover:bg-white/5 focus-visible:outline-2 focus-visible:outline-emerald-400">Administrator Sign In</Link>
            </div>
          </div>
          <div className="rounded-2xl border border-white/10 bg-[#0b1018] p-6">
            <h3 className="text-lg font-semibold">Before using the analysis</h3>
            <div className="mt-5 space-y-3 text-sm leading-relaxed text-slate-400">
              <p>Check the feed status and timestamp. A scheduled market session does not confirm that your data feed is connected.</p>
              <p>BUY and SELL are rule-based analysis outputs. AllSafe provides no broker order execution or account-specific risk sizing.</p>
              <p>Signals can be wrong or delayed. Trading involves risk of loss, and no strategy guarantees a profit. This service provides information, not personalized investment advice.</p>
            </div>
          </div>
        </section>

        <section id="contribute" aria-labelledby="contribute-title" className="mx-auto max-w-7xl scroll-mt-6 px-4 pb-14 sm:px-6 sm:pb-20 lg:px-8">
          <div className="flex flex-col gap-6 rounded-2xl border border-emerald-400/20 bg-[#0b1018] p-6 sm:p-8 md:flex-row md:items-center md:justify-between">
            <div>
              <h2 id="contribute-title" className="text-2xl font-bold tracking-tight">Buy me a beer</h2>
              <p id="contribution-amount" className="mt-2 max-w-lg text-sm leading-relaxed text-slate-300">
                If you like this project, you can make a one-time contribution of ₹{CONTRIBUTION_AMOUNT} via UPI.
              </p>
              <p className="mt-3 text-sm text-slate-400">
                Choose Pay now to open your UPI app with ₹{CONTRIBUTION_AMOUNT} pre-filled. You can review the payment before continuing.
              </p>
            </div>
            <div className="flex flex-col items-start gap-3">
              <a
                href={`upi://pay?${CONTRIBUTION_QUERY}`}
                aria-describedby="contribution-amount"
                className="inline-flex min-h-11 items-center justify-center rounded-lg bg-emerald-400 px-6 py-3 text-sm font-bold text-slate-950 hover:bg-emerald-300 focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-emerald-300"
              >
                Pay now
              </a>
              <a
                href={`gpay://upi/pay?${CONTRIBUTION_QUERY}`}
                aria-describedby="contribution-amount"
                className="rounded text-xs text-emerald-300 underline underline-offset-4 hover:text-emerald-200 focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-emerald-300"
              >
                Google Pay on iPhone
              </a>
            </div>
          </div>
        </section>
      </main>

      <footer className="border-t border-white/10 bg-[#05080d]">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-5 px-4 py-8 text-xs text-slate-500 sm:px-6 lg:px-8">
          <div>
            <p>AllSafe AI Trading · Supervised, read-only market analysis</p>
            <p className="mt-2 font-medium text-slate-300">Made by {CREATOR_NAME}</p>
          </div>
          <nav aria-label="Footer navigation" className="flex flex-wrap gap-5">
            <Link href="/what-we-done" className="rounded py-2 hover:text-white focus-visible:outline-2 focus-visible:outline-emerald-400">How It Works</Link>
            <Link href="/login" className="rounded py-2 hover:text-white focus-visible:outline-2 focus-visible:outline-emerald-400">Customer Sign In</Link>
            <Link href="/admin/login" className="rounded py-2 hover:text-white focus-visible:outline-2 focus-visible:outline-emerald-400">Administrator Sign In</Link>
            <Link href="/privacy" className="rounded py-2 hover:text-white focus-visible:outline-2 focus-visible:outline-emerald-400">Privacy</Link>
          </nav>
        </div>
      </footer>
    </div>
  );
}

export default memo(LandingPage);
