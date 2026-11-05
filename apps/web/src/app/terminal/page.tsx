import ApiStatus from "@/components/ApiStatus";
import LiveMarketDashboard from "@/components/LiveMarketDashboard";
import DashboardAccessGate from "@/components/auth/DashboardAccessGate";

// Backend status must be checked per request, never cached at build time.
export const dynamic = "force-dynamic";

export default function TerminalPage() {
  return (
    <DashboardAccessGate>
      <a
        href="#main-dashboard"
        className="sr-only focus:not-sr-only focus:fixed focus:top-3 focus:left-3 focus:z-50 focus:rounded-lg focus:bg-emerald-400 focus:px-4 focus:py-2 focus:text-sm focus:font-semibold focus:text-slate-950"
      >
        Skip to live market dashboard
      </a>

      <div className="mx-auto flex min-h-screen max-w-7xl flex-col px-4 py-5 sm:px-6 lg:px-8">
        <header className="flex flex-wrap items-center justify-between gap-3 border-b border-white/10 pb-4">
          <div className="flex items-center gap-3">
            <span className="inline-flex h-8 w-8 items-center justify-center rounded-lg border border-emerald-500/30 bg-emerald-500/10 text-sm font-bold text-emerald-400">
              AS
            </span>
            <div>
              <span className="text-lg font-semibold tracking-tight text-white">
                AllSafe <span className="text-emerald-400">AI Trading</span>
              </span>
              <span className="ml-2.5 hidden rounded border border-white/10 bg-white/[0.04] px-2 py-0.5 text-[11px] font-medium text-slate-300 sm:inline-block">
                NSE Index Terminal
              </span>
            </div>
          </div>
          <ApiStatus />
        </header>

        <main id="main-dashboard" className="flex-1 py-6 sm:py-8">
          <section className="flex flex-col justify-between gap-4 border-b border-white/5 pb-6 lg:flex-row lg:items-end">
            <div>
              <p className="text-xs font-semibold uppercase tracking-widest text-emerald-400">
                Groww Live Market Data &middot; 5-Indicator Rule Engine
              </p>
              <h1 className="mt-2 text-2xl font-bold tracking-tight text-white sm:text-3xl lg:text-4xl">
                Rule-based analysis for NIFTY 50 and BANK NIFTY
              </h1>
              <p className="mt-2 max-w-3xl text-sm text-slate-300 sm:text-base">
                Real-time 5-minute IST candlestick charts and unanimous 5-AI-Agent
                consensus confirmation across trend, pressure, breakout range, regime, and risk,
                with confirmed candles strictly separated from the forming candle.
              </p>
            </div>

            <div className="flex flex-wrap items-center gap-2 text-xs text-slate-300">
              <span className="rounded-lg border border-white/10 bg-white/[0.03] px-3 py-1.5">
                Session: <strong className="text-white">09:15–15:30 IST</strong>
              </span>
              <span className="rounded-lg border border-white/10 bg-white/[0.03] px-3 py-1.5">
                Mode: <strong className="text-emerald-300">Read-Only Analysis</strong>
              </span>
            </div>
          </section>

          <section className="mt-6">
            <LiveMarketDashboard />
          </section>
        </main>

        <footer className="border-t border-white/10 pt-4 text-xs leading-relaxed text-slate-400">
          Educational market analysis only; not investment advice. Trading involves
          risk of loss, and no strategy guarantees profit. Signals are generated
          by fixed rules and may be wrong or delayed.
        </footer>
      </div>
    </DashboardAccessGate>
  );
}
