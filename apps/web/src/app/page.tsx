import ApiStatus from "@/components/ApiStatus";
import LiveMarketDashboard from "@/components/LiveMarketDashboard";

// Backend status must be checked per request, never cached at build time.
export const dynamic = "force-dynamic";

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
            Groww live market data
          </p>
          <h1 className="mt-3 text-3xl font-bold tracking-tight sm:text-5xl">
            Rule-based analysis for NIFTY 50 and BANK NIFTY
          </h1>
          <p className="mt-4 max-w-2xl text-base text-slate-300 sm:text-lg">
            Live 5-minute charts for NIFTY 50 and BANK NIFTY, with confirmed
            candles kept separate from the candle still forming.
          </p>
        </section>

        <section className="mt-10">
          <LiveMarketDashboard />
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
