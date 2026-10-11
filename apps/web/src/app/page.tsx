import ApiStatus from "@/components/ApiStatus";

// Backend status must be checked per request, never cached at build time.
export const dynamic = "force-dynamic";

const markets = ["NIFTY 50", "BANK NIFTY"] as const;

// Everything below is planned work. Nothing here is implemented yet.
const roadmap = [
  "Interactive candlestick charts",
  "UT Bot Alerts (primary indicator)",
  "EMA, VWAP, RSI, MACD, Supertrend, ADX, ATR, volume, support/resistance",
  "1m, 3m, 5m, 15m, 1h and daily timeframes",
  "BUY / SELL / WAIT signals with entry, stop-loss, targets and explanations",
  "Multi-timeframe trend analysis",
  "Historical backtesting and paper trading",
  "User accounts and an admin dashboard",
];

export default function Home() {
  return (
    <div className="mx-auto flex min-h-screen max-w-5xl flex-col px-4 py-6 sm:px-6">
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-white/10 pb-4">
        <span className="text-lg font-semibold tracking-tight">
          AllSafe <span className="text-emerald-400">AI Trading</span>
        </span>
        <ApiStatus />
      </header>

      <main className="flex-1 py-10">
        <section>
          <p className="text-xs font-medium uppercase tracking-widest text-emerald-400">
            Phase 1 &middot; Foundation
          </p>
          <h1 className="mt-3 text-3xl font-bold tracking-tight sm:text-5xl">
            Rule-based analysis for NIFTY 50 and BANK NIFTY
          </h1>
          <p className="mt-4 max-w-2xl text-base text-slate-300 sm:text-lg">
            A transparent, rule-driven market analysis site. Signals will be
            deterministic and based on confirmed candle closes. You always place
            trades yourself; this site never connects to a broker.
          </p>
        </section>

        <section className="mt-10">
          <h2 className="text-sm font-semibold uppercase tracking-wider text-slate-400">
            Markets
          </h2>
          <div className="mt-3 grid gap-4 sm:grid-cols-2">
            {markets.map((name) => (
              <div
                key={name}
                className="rounded-xl border border-white/10 bg-white/5 p-5"
              >
                <div className="flex items-center justify-between">
                  <span className="font-semibold">{name}</span>
                  <span className="rounded-full bg-slate-700 px-2 py-0.5 text-xs text-slate-200">
                    No data source
                  </span>
                </div>
                <p className="mt-4 text-3xl font-semibold text-slate-500">
                  &mdash;
                </p>
                <p className="mt-2 text-sm text-slate-400">
                  No market-data provider is connected yet, so no prices or
                  signals are shown.
                </p>
              </div>
            ))}
          </div>
        </section>

        <section className="mt-10">
          <h2 className="text-sm font-semibold uppercase tracking-wider text-slate-400">
            Planned features
          </h2>
          <ul className="mt-3 grid gap-2 sm:grid-cols-2">
            {roadmap.map((item) => (
              <li
                key={item}
                className="flex items-start gap-3 rounded-lg border border-white/10 px-4 py-3 text-sm text-slate-300"
              >
                <span className="mt-0.5 shrink-0 rounded bg-slate-700 px-1.5 py-0.5 text-[10px] font-medium uppercase text-slate-300">
                  Planned
                </span>
                <span>{item}</span>
              </li>
            ))}
          </ul>
        </section>
      </main>

      <footer className="border-t border-white/10 pt-4 text-xs leading-relaxed text-slate-500">
        Educational market analysis only; not investment advice. Trading involves
        risk of loss, and no strategy guarantees profit. Signals are generated
        by fixed rules and may be wrong or delayed.
      </footer>
    </div>
  );
}
