"use client";

import { memo, useState } from "react";
import Link from "next/link";
import BrandLink from "@/components/BrandLink";
import { useAuth } from "@/components/auth/AuthProvider";
import LandingChartPreview from "@/components/landing/LandingChartPreview";
import type { MarketCalendar } from "@/lib/indianMarketStatus";
import IndianMarketStatusBadge from "@/components/landing/IndianMarketStatusBadge";
import LiveIstClock from "@/components/landing/LiveIstClock";
import AccountRequestButton from "@/components/landing/AccountRequestButton";

export interface LandingPageProps {
  serverTimeUtc?: string | null;
  backendOnline?: boolean;
  backendVersion?: string;
  marketCalendar?: MarketCalendar;
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
    summary: "When the required checks disagree, the result is Wait. If there is too little history to run the checks, the terminal shows Data unavailable.",
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
    text: "See Buy, Sell, or Wait once the checks have run. The terminal also tells you when there is too little data for a decision.",
  },
  {
    title: "Visible feed status",
    text: "Check whether market data is connected and current before interpreting an analysis output. Stale or unavailable data is identified.",
  },
];

function LandingPage({
  serverTimeUtc = null,
  backendOnline = false,
  marketCalendar,
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
    <div className="landing-page selection:bg-ui-green/30">
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:fixed focus:left-3 focus:top-3 focus:z-50 focus:rounded-lg focus:bg-emerald-400 focus:px-4 focus:py-3 focus:text-ui-ink"
      >
        Skip to main content
      </a>

      <header className="as-topbar">
        <div className="as-container as-topbar-inner">
          <BrandLink />
          <nav aria-label="Primary navigation" className="as-nav-group landing-navigation">
            <Link href="/what-we-done" className="as-nav-link">How It Works</Link>
            <a href="#dashboard-preview" className="as-nav-link">Preview</a>
            <a href="#contribute" className="as-nav-link">Contribute</a>
          </nav>
          <Link href={session ? "/terminal" : "/login"} className="as-button as-button--quiet">
            {session ? "Open Terminal" : "Customer Sign In"}
          </Link>
        </div>
      </header>

      <main id="main-content">
        <section className="landing-hero">
          <div className="as-container">
            <div className="landing-hero-inner">
              <div>
                <p className="as-kicker">NIFTY 50 · BANK NIFTY</p>
                <h1>NSE index charts. <span>Every 15 minutes.</span></h1>
              </div>
              <div className="landing-intro-side">
                <p className="landing-hero-copy">Review completed candles, see where Buy and Sell signals appeared, and check when the feed last updated.</p>
                <div className="mt-5 flex flex-wrap gap-2.5">
                  <AccountRequestButton />
                  <Link href="/what-we-done" className="as-button as-button--quiet">Explore how the analysis works</Link>
                </div>
                <p className="mt-4 text-xs leading-relaxed text-ui-muted">Account access starts after administrator approval.</p>
              </div>
            </div>
            <LandingChartPreview />
          </div>

          <div className="as-container landing-health">
            <LiveIstClock initialEpochMs={initialEpochMs} serverTimeOffsetMs={serverTimeOffsetMs} />
            <IndianMarketStatusBadge calendar={marketCalendar} initialEpochMs={initialEpochMs} serverTimeOffsetMs={serverTimeOffsetMs} />
            <div className="as-panel px-4 py-3">
              <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-ui-muted">Account service</p>
              <p className={`mt-2 font-mono text-lg font-semibold ${backendOnline ? "text-ui-green" : "text-ui-amber"}`}>{backendOnline ? "Reachable" : "Currently unavailable"}</p>
              <p className="mt-1 text-xs leading-relaxed text-ui-muted">Sign-in and application service</p>
            </div>
          </div>
        </section>

        <section id="features" className="as-container landing-section">
          <h2>What you’ll see in the terminal</h2>
          <div className="landing-features mt-6">
            {FEATURES.map((feature) => (
              <article key={feature.title} className="as-panel landing-feature">
                <h3 className="text-lg font-semibold">{feature.title}</h3>
                <p className="mt-3 text-sm leading-relaxed text-ui-muted">{feature.text}</p>
              </article>
            ))}
          </div>
        </section>

        <section id="dashboard-preview" className="landing-example scroll-mt-6">
          <div className="as-container landing-section">
            <div className="max-w-2xl">
              <h2>How a signal is confirmed</h2>
              <p className="mt-3 text-sm leading-relaxed text-ui-muted">Choose a sample decision to see how its checks work.</p>
              <p className="as-pill as-pill--amber mt-3" aria-label="ILLUSTRATIVE TERMINAL SIMULATION">NOT LIVE MARKET PRICES</p>
            </div>
            <div className="as-panel mt-6 grid gap-6 p-5 sm:p-7 lg:grid-cols-[0.7fr_1.3fr]">
              <div>
                <fieldset>
                  <legend className="text-sm font-semibold text-ui-muted">Choose an example</legend>
                  <div className="mt-3 flex flex-wrap gap-2">
                    {(["WAIT", "BUY", "SELL"] as const).map((mode) => (
                      <button type="button" key={mode} aria-pressed={exampleMode === mode} onClick={() => setExampleMode(mode)} className={`as-button ${exampleMode === mode ? "as-button--primary" : "as-button--quiet"}`}>{mode}</button>
                    ))}
                  </div>
                </fieldset>
                <div aria-live="polite" aria-atomic="true" className="mt-6">
                  <p className="as-kicker">Example result</p>
                  <p className="mt-2 font-mono text-3xl font-bold text-ui-ink">{exampleMode}</p>
                  <p className="mt-3 text-sm leading-relaxed text-ui-muted">{example.summary}</p>
                </div>
              </div>
              <ol aria-label="Five example signal checks" className="space-y-2">
                {CHECK_NAMES.map((name, index) => (
                  <li key={name} className="as-inset flex flex-wrap items-center justify-between gap-2 px-4 py-3 text-sm">
                    <span>{name}</span>
                    <span className="font-mono text-xs text-ui-muted">{example.checks[index]}</span>
                  </li>
                ))}
              </ol>
            </div>
            <p className="mt-5 text-xs leading-relaxed text-ui-muted">The terminal evaluates actual available candle history. This example does not calculate account-specific position size, entry prices, stop losses, or profit targets.</p>
          </div>
        </section>

        <section id="access" className="as-container landing-section grid gap-8 lg:grid-cols-2">
          <div>
            <h2>Sign in to AllSafe</h2>
            <p className="mt-4 text-sm leading-relaxed text-ui-muted">Customers sign in with an active account provided by the administrator and can access it from any network.</p>
            <p className="mt-3 text-sm leading-relaxed text-ui-muted">Administrator tools remain available only to accounts assigned the admin role.</p>
            <div className="mt-6 flex flex-wrap gap-4">
              <Link href="/login" className="as-button as-button--primary">Customer Sign In</Link>
              <Link href="/admin/login" className="as-button as-button--quiet">Administrator Sign In</Link>
            </div>
          </div>
          <div className="as-panel p-6">
            <h3 className="text-lg font-semibold">Before using the analysis</h3>
            <div className="mt-5 space-y-3 text-sm leading-relaxed text-ui-muted">
              <p>Check the feed status and timestamp. A scheduled market session does not confirm that your data feed is connected.</p>
              <p>BUY and SELL are rule-based analysis outputs. AllSafe provides no broker order execution or account-specific risk sizing.</p>
              <p>Signals can be wrong or delayed. Trading involves risk of loss, and no strategy guarantees a profit. This service provides information, not personalized investment advice.</p>
            </div>
          </div>
        </section>

        <section id="contribute" aria-labelledby="contribute-title" className="as-container scroll-mt-6 pb-12 sm:pb-16">
          <div className="as-panel flex flex-col gap-6 p-6 sm:p-8 md:flex-row md:items-center md:justify-between">
            <div>
              <h2 id="contribute-title" className="text-2xl font-bold tracking-tight">Buy me a beer</h2>
              <p id="contribution-amount" className="mt-2 max-w-lg text-sm leading-relaxed text-ui-muted">
                If you like this project, you can make a one-time contribution of ₹{CONTRIBUTION_AMOUNT} via UPI.
              </p>
              <p className="mt-3 text-sm text-ui-muted">
                Choose Pay now to open your UPI app with ₹{CONTRIBUTION_AMOUNT} pre-filled. You can review the payment before continuing.
              </p>
            </div>
            <div className="flex flex-col items-start gap-3">
              <a
                href={`upi://pay?${CONTRIBUTION_QUERY}`}
                aria-describedby="contribution-amount"
                className="as-button as-button--primary"
              >
                Pay now
              </a>
              <a
                href={`gpay://upi/pay?${CONTRIBUTION_QUERY}`}
                aria-describedby="contribution-amount"
                className="rounded text-xs text-ui-green underline underline-offset-4 hover:text-ui-green focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-emerald-300"
              >
                Google Pay on iPhone
              </a>
            </div>
          </div>
        </section>
      </main>

      <footer className="as-footer">
        <div className="as-container flex flex-wrap items-center justify-between gap-5 py-7 text-xs text-ui-muted">
          <div>
            <p>AllSafe AI Trading · Supervised, read-only market analysis</p>
            <p className="mt-2 font-medium text-ui-muted">Made by {CREATOR_NAME}</p>
          </div>
          <nav aria-label="Footer navigation" className="flex flex-wrap gap-5">
            <Link href="/what-we-done" className="rounded py-2 hover:text-ui-ink focus-visible:outline-2 focus-visible:outline-emerald-400">How It Works</Link>
            <Link href="/login" className="rounded py-2 hover:text-ui-ink focus-visible:outline-2 focus-visible:outline-emerald-400">Customer Sign In</Link>
            <Link href="/admin/login" className="rounded py-2 hover:text-ui-ink focus-visible:outline-2 focus-visible:outline-emerald-400">Administrator Sign In</Link>
            <Link href="/privacy" className="rounded py-2 hover:text-ui-ink focus-visible:outline-2 focus-visible:outline-emerald-400">Privacy</Link>
          </nav>
        </div>
      </footer>
    </div>
  );
}

export default memo(LandingPage);
