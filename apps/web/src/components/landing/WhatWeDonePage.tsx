"use client";

import { memo, useState } from "react";
import Link from "next/link";
import { useAuth } from "@/components/auth/AuthProvider";
import IndianMarketStatusBadge from "@/components/landing/IndianMarketStatusBadge";
import LiveIstClock from "@/components/landing/LiveIstClock";
import ScrollReveal from "@/components/landing/ScrollReveal";

export interface WhatWeDonePageProps {
  serverTimeUtc?: string | null;
  backendOnline?: boolean;
  backendVersion?: string;
}

type ConsensusMode = "BUY" | "SELL" | "WAIT";

interface AgentRoleSpec {
  id: string;
  badge: string;
  name: string;
  marketCheckDimension: string;
  whatItChecks: string;
  buyCondition: string;
  sellCondition: string;
  waitCondition: string;
}

const FIVE_AI_AGENTS: AgentRoleSpec[] = [
  {
    id: "agent-01",
    badge: "AI AGENT 01",
    name: "Dynamic Trailing & Breakout Agent",
    marketCheckDimension: "Price Crossover & Ratcheting Protection Floor",
    whatItChecks:
      "Continuously tracks confirmed 5-minute IST index closes on NIFTY 50 and BANK NIFTY against an adaptive, ratcheting trailing barrier to detect the exact bar where institutional demand or supply triggers a structural shift.",
    buyCondition:
      "BULLISH (BUY CHECK PASSED) — Confirmed 5m candle closes decisively above the adaptive trailing protection line.",
    sellCondition:
      "BEARISH (SELL CHECK PASSED) — Confirmed 5m candle breaks and closes below the adaptive trailing protection floor.",
    waitCondition:
      "HOLD / NEUTRAL — No fresh confirmed bar crossover; blocks premature entries inside noise.",
  },
  {
    id: "agent-02",
    badge: "AI AGENT 02",
    name: "Multi-Horizon Trend Structure Agent",
    marketCheckDimension: "Short, Medium & Long Intraday Trend Alignment",
    whatItChecks:
      "Inspects multi-horizon directional slope and price alignment across the Indian market session (`5m`, `15m`, and `1h` structure) to verify whether the index is trending cleanly or entangled in sideways congestion.",
    buyCondition:
      "BULLISH (BUY CHECK PASSED) — Short- and medium-horizon trend vectors are stacked upward with positive slope expansion.",
    sellCondition:
      "BEARISH (SELL CHECK PASSED) — Short- and medium-horizon trend vectors are aligned downward below structural resistance.",
    waitCondition:
      "CONFLICTING — Horizon vectors are flat or entangled inside a narrow range; vetoes trade entry.",
  },
  {
    id: "agent-03",
    badge: "AI AGENT 03",
    name: "Relative Strength & Buying Pressure Agent",
    marketCheckDimension: "Internal Session Velocity & Participation Balance",
    whatItChecks:
      "Measures the balance between upward buying velocity and downward selling pressure across recent confirmed bars in the Indian stock market to confirm genuine institutional participation.",
    buyCondition:
      "BULLISH (BUY CHECK PASSED) — Buying pressure holds above the equilibrium threshold with sustained upward strength.",
    sellCondition:
      "BEARISH (SELL CHECK PASSED) — Selling pressure dominates below the equilibrium threshold with downward conviction.",
    waitCondition:
      "NEUTRAL EQUILIBRIUM — Buying and selling pressure are balanced near midline; signals WAIT.",
  },
  {
    id: "agent-04",
    badge: "AI AGENT 04",
    name: "Impulse & Wave Convergence Agent",
    marketCheckDimension: "Momentum Acceleration & Wave Spread",
    whatItChecks:
      "Analyzes directional wave convergence, divergence, and impulse expansion across confirmed Indian market candles to verify whether market energy is accelerating or fading.",
    buyCondition:
      "BULLISH (BUY CHECK PASSED) — Positive impulse wave spread is expanding above the signal baseline.",
    sellCondition:
      "BEARISH (SELL CHECK PASSED) — Negative impulse wave spread is expanding downward below the baseline.",
    waitCondition:
      "DECAYING IMPULSE — Wave spread is contracting or contradicting trend structure; blocks signal.",
  },
  {
    id: "agent-05",
    badge: "AI AGENT 05",
    name: "Volatility Regime & Structural Band Agent",
    marketCheckDimension: "Dynamic Volatility Envelope & Support/Resistance Clearance",
    whatItChecks:
      "Maps the active session volatility envelope and key support/resistance barriers (`S1`, `S2`, `R1`, `R2`) to verify that price has cleared structural bands and that stop-loss distance fits within strict capital-risk bounds.",
    buyCondition:
      "BULLISH (BUY CHECK PASSED) — Index holds above the upward volatility regime band with clear room to overhead resistance.",
    sellCondition:
      "BEARISH (SELL CHECK PASSED) — Index trades below the downward volatility regime band with confirmed breakdown.",
    waitCondition:
      "CHOP / BARRIER PROXIMITY — Price is trapped inside compressed bands or too close to a barrier; enforces NO TRADE.",
  },
];

/**
 * Dedicated "What We Done" Page Component.
 * Explains how AllSafe AI Trading built 5 specialized AI agents that inspect the current Indian stock market
 * (NIFTY 50 & BANK NIFTY) and reach unanimous consensus to tell users when to BUY, when to SELL, or when to WAIT.
 * Zero proprietary indicator names are disclosed anywhere on this page.
 */
function WhatWeDonePage({
  serverTimeUtc = null,
  backendOnline = false,
  backendVersion = "0.1.0",
}: WhatWeDonePageProps) {
  const { user } = useAuth();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [consensusMode, setConsensusMode] = useState<ConsensusMode>("BUY");

  const [serverTimeOffsetMs] = useState<number>(() => {
    if (!serverTimeUtc) return 0;
    const parsed = new Date(serverTimeUtc).getTime();
    if (!Number.isFinite(parsed)) return 0;
    return parsed - Date.now();
  });

  return (
    <div className="min-h-screen bg-[#06090f] text-slate-100 selection:bg-emerald-500/30 selection:text-emerald-200">
      <a
        href="#what-we-done-main"
        className="sr-only focus:not-sr-only focus:fixed focus:top-3 focus:left-3 focus:z-50 focus:rounded-lg focus:bg-emerald-400 focus:px-4 focus:py-2 focus:text-sm focus:font-bold focus:text-slate-950"
      >
        Skip to What We Done content
      </a>

      {/* Navigation Bar */}
      <header className="sticky top-0 z-40 border-b border-white/10 bg-[#06090f]/90 backdrop-blur-xl">
        <nav
          aria-label="Primary navigation"
          className="mx-auto flex max-w-7xl items-center justify-between gap-3 px-4 py-3.5 sm:px-6 lg:px-8"
        >
          <div className="flex items-center gap-3">
            <Link
              href="/"
              className="group flex items-center gap-3 rounded-lg focus:outline-none focus:ring-2 focus:ring-emerald-400"
            >
              <span className="inline-flex h-9 w-9 items-center justify-center rounded-xl border border-emerald-500/40 bg-emerald-500/15 font-mono text-sm font-bold text-emerald-300 shadow-[0_0_16px_rgba(16,185,129,0.25)]">
                AS
              </span>
              <div>
                <span className="block text-base font-bold tracking-tight text-white sm:text-lg">
                  AllSafe <span className="text-emerald-400">AI Trading</span>
                </span>
                <span className="block font-mono text-[10px] uppercase tracking-[0.16em] text-slate-400">
                  5-Agent Indian Market Intelligence
                </span>
              </div>
            </Link>
          </div>

          <div className="hidden items-center gap-1 md:flex lg:gap-2">
            <Link
              href="/"
              className="rounded-lg px-3 py-2 text-xs font-medium text-slate-300 transition hover:bg-white/[0.06] hover:text-white lg:text-sm"
            >
              Home
            </Link>
            <Link
              href="/what-we-done"
              aria-current="page"
              className="rounded-lg border border-emerald-500/30 bg-emerald-500/15 px-3 py-2 text-xs font-semibold text-emerald-300 transition lg:text-sm"
            >
              What We Done
            </Link>
            <Link
              href="/#ai-intelligence"
              className="rounded-lg px-3 py-2 text-xs font-medium text-slate-300 transition hover:bg-white/[0.06] hover:text-white lg:text-sm"
            >
              AI Intelligence
            </Link>
            <Link
              href="/#features"
              className="rounded-lg px-3 py-2 text-xs font-medium text-slate-300 transition hover:bg-white/[0.06] hover:text-white lg:text-sm"
            >
              Features
            </Link>
            <Link
              href="/#about"
              className="rounded-lg px-3 py-2 text-xs font-medium text-slate-300 transition hover:bg-white/[0.06] hover:text-white lg:text-sm"
            >
              About
            </Link>
          </div>

          <div className="flex items-center gap-2.5">
            <div className="hidden xl:block">
              <IndianMarketStatusBadge
                variant="compact"
                serverTimeOffsetMs={serverTimeOffsetMs}
                showCountdown={false}
              />
            </div>

            {user && (
              <Link
                href="/terminal"
                className="hidden min-h-[40px] items-center justify-center rounded-xl border border-white/15 bg-white/[0.05] px-3.5 py-2 text-xs font-semibold text-slate-100 transition hover:bg-white/10 sm:inline-flex"
              >
                Open Live Terminal
              </Link>
            )}

            <Link
              href="/login"
              className="inline-flex min-h-[40px] items-center justify-center gap-2 rounded-xl border border-emerald-400/50 bg-emerald-500 px-4 py-2 text-xs font-bold text-slate-950 shadow-[0_0_20px_rgba(16,185,129,0.3)] transition hover:bg-emerald-400 sm:text-sm"
            >
              <span>Customer Sign In</span>
              <span aria-hidden="true" className="font-mono text-xs">
                &rarr;
              </span>
            </Link>

            <button
              type="button"
              onClick={() => setMobileMenuOpen((prev) => !prev)}
              aria-expanded={mobileMenuOpen}
              aria-label="Toggle navigation menu"
              className="inline-flex min-h-[40px] min-w-[40px] items-center justify-center rounded-xl border border-white/15 bg-white/[0.04] p-2 text-slate-200 md:hidden"
            >
              <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path strokeLinecap="round" strokeLinejoin="round" d="M4 6h16M4 12h16M4 18h16" />
              </svg>
            </button>
          </div>
        </nav>

        {mobileMenuOpen && (
          <div className="border-t border-white/10 bg-[#080d16] px-4 py-4 md:hidden">
            <div className="flex flex-col gap-1.5">
              <Link href="/" className="flex min-h-[44px] items-center rounded-lg px-3 py-2 text-sm font-medium text-slate-200">
                Home
              </Link>
              <Link href="/what-we-done" className="flex min-h-[44px] items-center rounded-lg bg-emerald-500/15 px-3 py-2 text-sm font-bold text-emerald-300">
                What We Done
              </Link>
              <Link href="/login" className="mt-2 flex min-h-[44px] items-center justify-center rounded-xl bg-emerald-500 px-4 py-2.5 text-sm font-bold text-slate-950">
                Customer Sign In &rarr;
              </Link>
            </div>
          </div>
        )}
      </header>

      <main id="what-we-done-main" className="mx-auto max-w-7xl px-4 py-8 sm:px-6 sm:py-12 lg:px-8">
        {/* Live IST Clock & NSE/BSE Market Status Strip */}
        <div className="mb-8 grid grid-cols-1 gap-3.5 md:grid-cols-2">
          <LiveIstClock serverTimeOffsetMs={serverTimeOffsetMs} variant="hero" />
          <IndianMarketStatusBadge
            serverTimeOffsetMs={serverTimeOffsetMs}
            variant="hero"
            showCountdown
          />
        </div>

        {/* Page Hero Header: WHAT WE DONE */}
        <ScrollReveal className="rounded-3xl border border-white/10 bg-gradient-to-br from-[#0b131e] via-[#080d15] to-[#110b15] p-6 shadow-2xl sm:p-10">
          <div className="inline-flex items-center gap-2 rounded-full border border-emerald-500/30 bg-emerald-500/10 px-3.5 py-1 font-mono text-xs font-semibold text-emerald-300">
            <span>WHAT WE DONE</span>
            <span aria-hidden="true">&middot;</span>
            <span>5 AUTONOMOUS AI MARKET AGENTS</span>
          </div>

          <h1
            data-testid="what-we-done-title"
            className="mt-4 text-3xl font-extrabold tracking-tight text-white sm:text-5xl"
          >
            What We Done: Five AI Agents Built for the Indian Stock Market
          </h1>

          <p className="mt-4 max-w-3xl text-sm leading-relaxed text-slate-300 sm:text-base lg:text-lg">
            We engineered <strong>Five Specialized AI Agents</strong> that continuously
            inspect multiple live dimensions of the Indian stock market (
            <strong className="text-white">NIFTY 50</strong> and{" "}
            <strong className="text-white">BANK NIFTY</strong> during official NSE/BSE
            trading hours). Instead of relying on a single signal or guesswork, all
            five AI agents check distinct market conditions on confirmed 5-minute IST
            candles and work together to tell you <strong>when to BUY</strong>,{" "}
            <strong>when to SELL</strong>, and <strong>when to stay out (WAIT)</strong>.
          </p>

          <div className="mt-6 grid grid-cols-1 gap-3 sm:grid-cols-3">
            <div className="rounded-xl border border-emerald-500/30 bg-emerald-500/10 p-4">
              <div className="font-mono text-xs font-bold uppercase text-emerald-300">
                When to BUY
              </div>
              <div className="mt-1 text-sm font-bold text-white">
                5 / 5 AI Agents Bullish
              </div>
              <p className="mt-1 text-xs text-slate-300">
                Triggered only when every single AI agent confirms upward breakout,
                trend alignment, buying pressure, wave acceleration, and volatility
                clearance.
              </p>
            </div>

            <div className="rounded-xl border border-rose-500/30 bg-rose-500/10 p-4">
              <div className="font-mono text-xs font-bold uppercase text-rose-300">
                When to SELL
              </div>
              <div className="mt-1 text-sm font-bold text-white">
                5 / 5 AI Agents Bearish
              </div>
              <p className="mt-1 text-xs text-slate-300">
                Triggered only when all five AI agents unanimously verify a structural
                breakdown, downward trend slope, selling dominance, and bearish regime
                control.
              </p>
            </div>

            <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 p-4">
              <div className="font-mono text-xs font-bold uppercase text-amber-300">
                When to WAIT (Capital Lock)
              </div>
              <div className="mt-1 text-sm font-bold text-white">
                Any Agent Disagrees
              </div>
              <p className="mt-1 text-xs text-slate-300">
                If even one AI agent detects sideways chop, conflicting momentum, or
                stale feed data, the system locks the output to{" "}
                <code className="text-amber-200">NO_TRADE</code> to protect capital.
              </p>
            </div>
          </div>
        </ScrollReveal>

        {/* Interactive 5-Agent Buy / Sell Consensus Inspector */}
        <section className="mt-12">
          <ScrollReveal className="flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
            <div>
              <p className="font-mono text-xs font-semibold uppercase tracking-[0.2em] text-emerald-400">
                Interactive 5-Agent Consensus Architecture
              </p>
              <h2 className="mt-2 text-2xl font-bold text-white sm:text-3xl">
                How Our 5 AI Agents Check the Market &amp; Decide Buy vs. Sell
              </h2>
              <p className="mt-1 text-xs text-slate-300 sm:text-sm">
                Select a market decision state below to inspect what each of the 5 AI
                agents verifies before issuing a Buy, Sell, or Wait signal.
              </p>
            </div>

            <div
              role="group"
              aria-label="Select 5-Agent consensus state"
              className="inline-flex rounded-xl border border-white/10 bg-[#0b1018] p-1"
            >
              {(["BUY", "SELL", "WAIT"] as const).map((mode) => (
                <button
                  key={mode}
                  type="button"
                  onClick={() => setConsensusMode(mode)}
                  aria-pressed={consensusMode === mode}
                  className={`min-h-[38px] rounded-lg px-4 py-1.5 font-mono text-xs font-bold transition ${
                    consensusMode === mode
                      ? mode === "BUY"
                        ? "bg-emerald-500 text-slate-950"
                        : mode === "SELL"
                          ? "bg-rose-500 text-white"
                          : "bg-amber-400 text-slate-950"
                      : "text-slate-300 hover:text-white"
                  }`}
                >
                  {mode === "BUY"
                    ? "WHEN TO BUY (5/5)"
                    : mode === "SELL"
                      ? "WHEN TO SELL (5/5)"
                      : "WHEN TO WAIT"}
                </button>
              ))}
            </div>
          </ScrollReveal>

          {/* 5 AI Agent Cards */}
          <div className="mt-6 grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
            {FIVE_AI_AGENTS.map((agent, idx) => {
              const activeText =
                consensusMode === "BUY"
                  ? agent.buyCondition
                  : consensusMode === "SELL"
                    ? agent.sellCondition
                    : agent.waitCondition;

              const statusColor =
                consensusMode === "BUY"
                  ? "border-emerald-500/35 bg-emerald-500/10 text-emerald-300"
                  : consensusMode === "SELL"
                    ? "border-rose-500/35 bg-rose-500/10 text-rose-300"
                    : "border-amber-500/35 bg-amber-500/10 text-amber-300";

              return (
                <ScrollReveal
                  key={agent.id}
                  delayMs={idx * 60}
                  className="flex flex-col justify-between rounded-2xl border border-white/10 bg-[#0b1018] p-5"
                >
                  <div>
                    <div className="flex items-center justify-between gap-2">
                      <span className="rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-2.5 py-1 font-mono text-[11px] font-bold text-emerald-300">
                        {agent.badge}
                      </span>
                      <span className="font-mono text-[11px] text-slate-400">
                        Indian Market Check #{idx + 1}
                      </span>
                    </div>

                    <h3 className="mt-3 text-lg font-bold text-white">
                      {agent.name}
                    </h3>
                    <div className="mt-1 font-mono text-[11px] text-slate-400">
                      Checks: {agent.marketCheckDimension}
                    </div>

                    <p className="mt-3 text-xs leading-relaxed text-slate-300 sm:text-sm">
                      {agent.whatItChecks}
                    </p>
                  </div>

                  <div className={`mt-4 rounded-xl border p-3 text-xs font-medium ${statusColor}`}>
                    {activeText}
                  </div>
                </ScrollReveal>
              );
            })}

            {/* 6th Card: The Master Consensus Coordinator */}
            <ScrollReveal
              delayMs={300}
              className="flex flex-col justify-between rounded-2xl border border-emerald-500/35 bg-gradient-to-br from-[#0c1824] to-[#0b1018] p-5"
            >
              <div>
                <div className="flex items-center justify-between gap-2">
                  <span className="rounded-lg border border-emerald-400/40 bg-emerald-500/20 px-2.5 py-1 font-mono text-[11px] font-bold text-emerald-200">
                    MASTER COORDINATOR
                  </span>
                  <span className="font-mono text-[11px] text-emerald-300">
                    Unanimous Gate + Risk Cap
                  </span>
                </div>

                <h3 className="mt-3 text-lg font-bold text-white">
                  Unanimous Buy / Sell Decision &amp; Risk Guard
                </h3>
                <p className="mt-2 text-xs leading-relaxed text-slate-300 sm:text-sm">
                  Aggregates the real-time verdicts of all 5 AI agents on confirmed
                  5-minute IST candles, cross-checks 15-minute and 1-hour market
                  regimes, and calculates lot-rounded position sizing (`75` for NIFTY
                  50, `30` for BANK NIFTY) capped at &le; 2.0% capital risk.
                </p>
              </div>

              <div className="mt-4 flex items-center justify-between border-t border-white/10 pt-3">
                <Link
                  href="/login"
                  className="inline-flex items-center gap-1.5 rounded-lg bg-emerald-500 px-3.5 py-2 text-xs font-bold text-slate-950 transition hover:bg-emerald-400"
                >
                  <span>Sign In to View Live Agents</span>
                  <span aria-hidden="true">&rarr;</span>
                </Link>
                <Link
                  href="/"
                  className="text-xs font-semibold text-slate-300 hover:text-white"
                >
                  &larr; Landing Page
                </Link>
              </div>
            </ScrollReveal>
          </div>
        </section>
      </main>

      {/* Footer */}
      <footer className="mt-12 border-t border-white/10 bg-[#05080d] py-8 text-xs text-slate-400">
        <div className="mx-auto flex max-w-7xl flex-col items-center justify-between gap-4 px-4 sm:flex-row sm:px-6 lg:px-8">
          <div>
            <strong className="text-white">AllSafe AI Trading</strong> &middot; Five
            AI Agents for Indian Stock Market Decision Support (Read-Only Analysis)
          </div>
          <div className="flex flex-wrap items-center gap-4">
            <Link href="/" className="hover:text-white">
              Home
            </Link>
            <Link href="/what-we-done" className="text-emerald-300">
              What We Done
            </Link>
            <Link href="/login" className="hover:text-white">
              Customer Sign In
            </Link>
            <span className="font-mono text-[11px] text-slate-500">
              API: {backendOnline ? `Online (v${backendVersion})` : "Read-Only Mode"}
            </span>
          </div>
        </div>
      </footer>
    </div>
  );
}

export default memo(WhatWeDonePage);
