import ApiStatus from "@/components/ApiStatus";
import LiveMarketDashboard from "@/components/LiveMarketDashboard";
import DashboardAccessGate from "@/components/auth/DashboardAccessGate";
import Link from "next/link";

// Backend status must be checked per request, never cached at build time.
export const dynamic = "force-dynamic";

export default function Home() {
  return (
    <DashboardAccessGate>
      <div className="mx-auto flex min-h-[calc(100vh-4rem)] w-full max-w-[96rem] flex-col px-4 py-5 sm:px-6 lg:px-8">
        <header className="flex flex-col gap-3 border-b border-white/10 pb-5 sm:flex-row sm:items-center sm:justify-between">
          <Link href="#market-overview" className="inline-flex w-fit rounded-md text-lg font-semibold tracking-tight focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-400 focus-visible:ring-offset-4 focus-visible:ring-offset-[#0b0f14]">
            AllSafe <span className="ml-1 text-emerald-400">AI Trading</span>
          </Link>
          <div className="flex flex-wrap items-center gap-3">
            <span className="inline-flex min-h-8 items-center rounded-full border border-emerald-400/20 bg-emerald-400/10 px-3 text-xs font-medium text-emerald-200">
              15-minute candles
            </span>
            <ApiStatus />
          </div>
        </header>

        <main id="market-overview" className="flex-1 py-8 sm:py-10">
          <section aria-labelledby="terminal-title" className="max-w-4xl">
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-emerald-400">
              Market terminal
            </p>
            <h1 id="terminal-title" className="mt-3 text-3xl font-bold tracking-tight text-white sm:text-4xl lg:text-5xl">
              NIFTY 50 &amp; BANK NIFTY
            </h1>
            <p className="mt-4 max-w-3xl text-sm leading-6 text-slate-300 sm:text-base sm:leading-7">
              Explore 15-minute candles and rule-based buy or sell signals. Open an index chart in its own tab for a larger view, and use the feed status to see whether displayed prices are current.
            </p>
            <p className="mt-3 text-xs leading-5 text-slate-400 sm:text-sm">
              Choose Groww or Upstox below. Closed candles and the candle still forming are shown separately.
            </p>
          </section>

          <section aria-label="Index charts" className="mt-8 sm:mt-10">
            <LiveMarketDashboard />
          </section>
        </main>

        <footer className="border-t border-white/10 py-5 text-xs leading-relaxed text-slate-400 sm:flex sm:items-start sm:justify-between sm:gap-8">
          <p className="max-w-3xl">
            Educational market analysis only; not investment advice. Signals use fixed rules and can be wrong or delayed. Trading involves risk of loss.
          </p>
          <p className="mt-2 shrink-0 text-slate-500 sm:mt-0">No orders are placed by this site.</p>
        </footer>
      </div>
    </DashboardAccessGate>
  );
}
