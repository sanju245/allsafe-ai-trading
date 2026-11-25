"use client";

import { memo, useState } from "react";
import Link from "next/link";
import BrandLink from "@/components/BrandLink";
import { useAuth } from "@/components/auth/AuthProvider";
import type { MarketCalendar } from "@/lib/indianMarketStatus";
import IndianMarketStatusBadge from "@/components/landing/IndianMarketStatusBadge";
import LiveIstClock from "@/components/landing/LiveIstClock";
import ScrollReveal from "@/components/landing/ScrollReveal";

export interface WhatWeDonePageProps {
  serverTimeUtc?: string | null;
  backendOnline?: boolean;
  backendVersion?: string;
  marketCalendar?: MarketCalendar;
}

type ConsensusMode = "BUY" | "SELL" | "WAIT";

interface SignalCheckSpec {
  id: string;
  badge: string;
  name: string;
  marketCheckDimension: string;
  whatItChecks: string;
  buyCondition: string;
  sellCondition: string;
  waitCondition: string;
}

const SIGNAL_CHECKS: SignalCheckSpec[] = [
  {
    id: "check-01",
    badge: "SIGNAL CHECK 01",
    name: "Primary Signal Trigger",
    marketCheckDimension: "Candidate direction",
    whatItChecks:
      "Looks for a candidate BUY or SELL trigger using validated, closed 15-minute candles. A trigger alone does not produce a final signal.",
    buyCondition:
      "BUY CANDIDATE — A buy trigger is present on the confirmed candle.",
    sellCondition:
      "SELL CANDIDATE — A sell trigger is present on the confirmed candle.",
    waitCondition:
      "NO TRIGGER — No candidate direction is present on the confirmed candle.",
  },
  {
    id: "check-02",
    badge: "SIGNAL CHECK 02",
    name: "Trend Direction Confirmation",
    marketCheckDimension: "Direction agreement",
    whatItChecks:
      "Checks whether the candle trend agrees with the candidate direction. The live terminal evaluates 15-minute candles; higher-timeframe models are not shown here.",
    buyCondition:
      "BUY CONFIRMATION — The trend check agrees with the buy candidate.",
    sellCondition:
      "SELL CONFIRMATION — The trend check agrees with the sell candidate.",
    waitCondition:
      "NO AGREEMENT — The trend check does not confirm the candidate direction.",
  },
  {
    id: "check-03",
    badge: "SIGNAL CHECK 03",
    name: "Momentum Range Confirmation",
    marketCheckDimension: "Momentum agreement",
    whatItChecks:
      "Checks whether recent candle momentum supports the candidate direction. Insufficient candle history is reported as unavailable.",
    buyCondition:
      "BUY CONFIRMATION — Momentum agrees with the buy candidate.",
    sellCondition:
      "SELL CONFIRMATION — Momentum agrees with the sell candidate.",
    waitCondition:
      "NO AGREEMENT — Momentum does not confirm the candidate direction.",
  },
  {
    id: "check-04",
    badge: "SIGNAL CHECK 04",
    name: "Momentum Direction Confirmation",
    marketCheckDimension: "Directional momentum",
    whatItChecks:
      "Checks a second momentum measure against the candidate direction using the same confirmed candle series.",
    buyCondition:
      "BUY CONFIRMATION — Directional momentum agrees with the buy candidate.",
    sellCondition:
      "SELL CONFIRMATION — Directional momentum agrees with the sell candidate.",
    waitCondition:
      "NO AGREEMENT — Directional momentum does not confirm the candidate direction.",
  },
  {
    id: "check-05",
    badge: "SIGNAL CHECK 05",
    name: "Trend Filter Confirmation",
    marketCheckDimension: "Final direction check",
    whatItChecks:
      "Applies a final trend filter to the candidate direction. This does not calculate account-specific position size or cap financial risk.",
    buyCondition:
      "BUY CONFIRMATION — The trend filter agrees with the buy candidate.",
    sellCondition:
      "SELL CONFIRMATION — The trend filter agrees with the sell candidate.",
    waitCondition:
      "NO AGREEMENT — The trend filter does not confirm the candidate direction.",
  },
];

/**
 * Overview of the current deterministic five-check signal engine.
 * It is one rule engine, not a collection of independent AI services.
 */
function WhatWeDonePage({
  serverTimeUtc = null,
  backendOnline = false,
  marketCalendar,
}: WhatWeDonePageProps) {
  const { session } = useAuth();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [consensusMode, setConsensusMode] = useState<ConsensusMode>("BUY");

  const [serverTimeOffsetMs] = useState<number>(() => {
    if (!serverTimeUtc) return 0;
    const parsed = new Date(serverTimeUtc).getTime();
    if (!Number.isFinite(parsed)) return 0;
    return parsed - Date.now();
  });
  const parsedEpoch = serverTimeUtc ? Date.parse(serverTimeUtc) : Number.NaN;
  const initialEpochMs = Number.isFinite(parsedEpoch) ? parsedEpoch : undefined;

  return (
    <div className="as-page selection:bg-ui-green/30 selection:text-ui-green">
      <a
        href="#what-we-done-main"
        className="sr-only focus:not-sr-only focus:fixed focus:top-3 focus:left-3 focus:z-50 focus:rounded-lg focus:bg-emerald-400 focus:px-4 focus:py-2 focus:text-sm focus:font-bold focus:text-ui-ink"
      >
        Skip to how-it-works content
      </a>

      {/* Navigation Bar */}
      <header className="as-topbar sticky top-0 z-40">
        <nav
          aria-label="Primary navigation"
          className="as-container flex min-h-18 items-center justify-between gap-3 py-3"
        >
          <BrandLink />

          <div className="hidden items-center gap-1 md:flex lg:gap-2">
            <Link
              href="/"
              className="rounded-lg px-3 py-2 text-xs font-medium text-ui-muted transition hover:bg-ui-inset hover:text-ui-ink lg:text-sm"
            >
              Home
            </Link>
            <Link
              href="/what-we-done"
              aria-current="page"
              className="rounded-lg border border-ui-green/25 bg-ui-green/15 px-3 py-2 text-xs font-semibold text-ui-green transition lg:text-sm"
            >
              How It Works
            </Link>
            <Link
              href="/#market-preview"
              className="rounded-lg px-3 py-2 text-xs font-medium text-ui-muted transition hover:bg-ui-inset hover:text-ui-ink lg:text-sm"
            >
              Chart Preview
            </Link>
            <Link
              href="/#features"
              className="rounded-lg px-3 py-2 text-xs font-medium text-ui-muted transition hover:bg-ui-inset hover:text-ui-ink lg:text-sm"
            >
              Features
            </Link>
            <Link
              href="/#access"
              className="rounded-lg px-3 py-2 text-xs font-medium text-ui-muted transition hover:bg-ui-inset hover:text-ui-ink lg:text-sm"
            >
              Account Access
            </Link>
          </div>

          <div className="flex items-center gap-2.5">
            <div className="hidden xl:block">
              <IndianMarketStatusBadge
                calendar={marketCalendar}
                variant="compact"
                serverTimeOffsetMs={serverTimeOffsetMs}
                showCountdown={false}
              />
            </div>

            {session && (
              <Link
                href="/terminal"
                className="hidden min-h-[40px] items-center justify-center rounded-xl border border-ui-line bg-ui-inset px-3.5 py-2 text-xs font-semibold text-ui-ink transition hover:bg-ui-inset sm:inline-flex"
              >
                Open Live Terminal
              </Link>
            )}

            <Link
              href="/login"
              className="inline-flex min-h-[40px] items-center justify-center gap-2 rounded-xl border border-ui-green/25 bg-emerald-500 px-4 py-2 text-xs font-bold text-ui-ink shadow-[0_0_20px_rgba(16,185,129,0.3)] transition hover:bg-emerald-400 sm:text-sm"
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
              className="inline-flex min-h-[40px] min-w-[40px] items-center justify-center rounded-xl border border-ui-line bg-ui-inset p-2 text-ui-ink md:hidden"
            >
              <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path strokeLinecap="round" strokeLinejoin="round" d="M4 6h16M4 12h16M4 18h16" />
              </svg>
            </button>
          </div>
        </nav>

        {mobileMenuOpen && (
          <div className="border-t border-ui-line bg-ui-card px-4 py-4 md:hidden">
            <div className="flex flex-col gap-1.5">
              <Link href="/" className="flex min-h-[44px] items-center rounded-lg px-3 py-2 text-sm font-medium text-ui-ink">
                Home
              </Link>
              <Link href="/what-we-done" className="flex min-h-[44px] items-center rounded-lg bg-ui-green/15 px-3 py-2 text-sm font-bold text-ui-green">
                How It Works
              </Link>
              <Link href="/login" className="mt-2 flex min-h-[44px] items-center justify-center rounded-xl bg-emerald-500 px-4 py-2.5 text-sm font-bold text-ui-ink">
                Customer Sign In &rarr;
              </Link>
            </div>
          </div>
        )}
      </header>

      <main id="what-we-done-main" className="as-container py-8 sm:py-12">
        {/* Live IST Clock & NSE Market Status Strip */}
        <div className="mb-8 grid grid-cols-1 gap-3.5 md:grid-cols-2">
          <LiveIstClock
            initialEpochMs={initialEpochMs}
            serverTimeOffsetMs={serverTimeOffsetMs}
            variant="hero"
          />
          <IndianMarketStatusBadge
                calendar={marketCalendar}
            initialEpochMs={initialEpochMs}
            serverTimeOffsetMs={serverTimeOffsetMs}
            variant="hero"
            showCountdown
          />
        </div>

        {/* Page hero: how the five-check signal engine works */}
        <ScrollReveal className="as-panel p-6 sm:p-10">
          <div className="inline-flex items-center gap-2 rounded-full border border-ui-green/25 bg-ui-green/10 px-3.5 py-1 font-mono text-xs font-semibold text-ui-green">
            <span>HOW IT WORKS</span>
            <span aria-hidden="true">&middot;</span>
            <span>ONE DETERMINISTIC RULE ENGINE · FIVE CHECKS</span>
          </div>

          <h1
            data-testid="what-we-done-title"
            className="mt-4 text-3xl font-extrabold tracking-tight text-ui-ink sm:text-5xl"
          >
            How the Five Signal Checks Work
          </h1>

          <p className="mt-4 max-w-3xl text-sm leading-relaxed text-ui-muted sm:text-base lg:text-lg">
            AllSafe evaluates confirmed 15-minute candles for{" "}
            <strong className="text-ui-ink">NIFTY 50</strong> and{" "}
            <strong className="text-ui-ink">BANK NIFTY</strong> through one
            deterministic signal engine. A candidate direction needs agreement from
            four checks; otherwise the result is WAIT or DATA_UNAVAILABLE. The five
            cards below explain the checks and are not independent AI agents. No
            broker orders are placed.
          </p>

          <div className="mt-6 grid grid-cols-1 gap-3 sm:grid-cols-3">
            <div className="rounded-xl border border-ui-green/25 bg-ui-green/10 p-4">
              <div className="font-mono text-xs font-bold uppercase text-ui-green">
                When to BUY
              </div>
              <div className="mt-1 text-sm font-bold text-ui-ink">
                Trigger + 4 checks agree
              </div>
              <p className="mt-1 text-xs text-ui-muted">
                The engine returns BUY only when the primary trigger and all four
                confirmation checks agree on a confirmed candle.
              </p>
            </div>

            <div className="rounded-xl border border-ui-red/25 bg-ui-red/10 p-4">
              <div className="font-mono text-xs font-bold uppercase text-ui-red">
                When to SELL
              </div>
              <div className="mt-1 text-sm font-bold text-ui-ink">
                Trigger + 4 checks agree
              </div>
              <p className="mt-1 text-xs text-ui-muted">
                The engine returns SELL only when the primary trigger and all four
                confirmation checks agree on a confirmed candle.
              </p>
            </div>

            <div className="rounded-xl border border-ui-amber/25 bg-ui-amber/10 p-4">
              <div className="font-mono text-xs font-bold uppercase text-ui-amber">
                When to WAIT
              </div>
              <div className="mt-1 text-sm font-bold text-ui-ink">
                A check disagrees
              </div>
              <p className="mt-1 text-xs text-ui-muted">
                If a check disagrees or candle history is incomplete, the engine
                returns WAIT or DATA_UNAVAILABLE. The API also marks results as not
                current when the feed is stale or disconnected.
              </p>
            </div>
          </div>
        </ScrollReveal>

        {/* Interactive explanation of the deterministic five-check engine */}
        <section className="mt-12">
          <ScrollReveal className="flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
            <div>
              <p className="font-mono text-xs font-semibold uppercase tracking-[0.2em] text-ui-green">
                Interactive Signal-Check Explanation
              </p>
              <h2 className="mt-2 text-2xl font-bold text-ui-ink sm:text-3xl">
                How the Rule Engine Decides BUY, SELL, or WAIT
              </h2>
              <p className="mt-1 text-xs text-ui-muted sm:text-sm">
                Select an example state to see how each check contributes. This
                interactive explanation is illustrative; it does not compute a live
                signal.
              </p>
            </div>

            <div
              role="group"
              aria-label="Select an illustrative signal state"
              className="inline-flex rounded-xl border border-ui-line bg-ui-card p-1"
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
                        ? "bg-emerald-500 text-ui-ink"
                        : mode === "SELL"
                          ? "bg-rose-500 text-ui-ink"
                          : "bg-amber-400 text-ui-ink"
                      : "text-ui-muted hover:text-ui-ink"
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

          {/* Five rule-check cards */}
          <div className="mt-6 grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
            {SIGNAL_CHECKS.map((agent, idx) => {
              const activeText =
                consensusMode === "BUY"
                  ? agent.buyCondition
                  : consensusMode === "SELL"
                    ? agent.sellCondition
                    : agent.waitCondition;

              const statusColor =
                consensusMode === "BUY"
                  ? "border-ui-green/25 bg-ui-green/10 text-ui-green"
                  : consensusMode === "SELL"
                    ? "border-ui-red/25 bg-ui-red/10 text-ui-red"
                    : "border-ui-amber/25 bg-ui-amber/10 text-ui-amber";

              return (
                <ScrollReveal
                  key={agent.id}
                  delayMs={idx * 60}
                  className="flex flex-col justify-between rounded-2xl border border-ui-line bg-ui-card p-5"
                >
                  <div>
                    <div className="flex items-center justify-between gap-2">
                      <span className="rounded-lg border border-ui-green/25 bg-ui-green/10 px-2.5 py-1 font-mono text-[11px] font-bold text-ui-green">
                        {agent.badge}
                      </span>
                      <span className="font-mono text-[11px] text-ui-muted">
                        Signal check #{idx + 1}
                      </span>
                    </div>

                    <h3 className="mt-3 text-lg font-bold text-ui-ink">
                      {agent.name}
                    </h3>
                    <div className="mt-1 font-mono text-[11px] text-ui-muted">
                      Checks: {agent.marketCheckDimension}
                    </div>

                    <p className="mt-3 text-xs leading-relaxed text-ui-muted sm:text-sm">
                      {agent.whatItChecks}
                    </p>
                  </div>

                  <div className={`mt-4 rounded-xl border p-3 text-xs font-medium ${statusColor}`}>
                    {activeText}
                  </div>
                </ScrollReveal>
              );
            })}

            {/* Final card: the current decision rule */}
            <ScrollReveal
              delayMs={300}
              className="as-panel flex flex-col justify-between border-ui-green/25 bg-ui-inset p-5"
            >
              <div>
                <div className="flex items-center justify-between gap-2">
                  <span className="rounded-lg border border-ui-green/25 bg-ui-green/20 px-2.5 py-1 font-mono text-[11px] font-bold text-ui-green">
                    DECISION RULE
                  </span>
                  <span className="font-mono text-[11px] text-ui-green">
                    Five checks on 15-minute candles
                  </span>
                </div>

                <h3 className="mt-3 text-lg font-bold text-ui-ink">
                  BUY / SELL Requirements
                </h3>
                <p className="mt-2 text-xs leading-relaxed text-ui-muted sm:text-sm">
                  BUY or SELL requires a primary trigger plus agreement from all four
                  confirmation checks. Otherwise the engine returns WAIT or
                  DATA_UNAVAILABLE. This output is not an order and does not include
                  an account-specific risk limit or position-size calculation.
                </p>
              </div>

              <div className="mt-4 flex items-center justify-between border-t border-ui-line pt-3">
                <Link
                  href="/login"
                  className="inline-flex items-center gap-1.5 rounded-lg bg-emerald-500 px-3.5 py-2 text-xs font-bold text-ui-ink transition hover:bg-emerald-400"
                >
                  <span>Customer Sign In</span>
                  <span aria-hidden="true">&rarr;</span>
                </Link>
                <Link
                  href="/"
                  className="text-xs font-semibold text-ui-muted hover:text-ui-ink"
                >
                  &larr; Landing Page
                </Link>
              </div>
            </ScrollReveal>
          </div>
        </section>
      </main>

      {/* Footer */}
      <footer className="as-footer mt-12 py-8 text-xs text-ui-muted">
        <div className="mx-auto flex max-w-7xl flex-col items-center justify-between gap-4 px-4 sm:flex-row sm:px-6 lg:px-8">
          <div>
            <strong className="text-ui-ink">AllSafe AI Trading</strong> &middot; Rule-based
            signal analysis for NSE index data (read-only)
          </div>
          <div className="flex flex-wrap items-center gap-4">
            <Link href="/" className="hover:text-ui-ink">
              Home
            </Link>
            <Link href="/what-we-done" className="text-ui-green">
              How It Works
            </Link>
            <Link href="/login" className="hover:text-ui-ink">
              Customer Sign In
            </Link>
            <span className="font-mono text-[11px] text-ui-muted">
              Account service: {backendOnline ? "Reachable" : "Currently unavailable"}
            </span>
          </div>
        </div>
      </footer>
    </div>
  );
}

export default memo(WhatWeDonePage);
