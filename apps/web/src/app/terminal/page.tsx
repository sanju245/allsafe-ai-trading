import ApiStatus from "@/components/ApiStatus";
import LiveMarketDashboard from "@/components/LiveMarketDashboard";
import Upstox15mHistory from "@/components/Upstox15mHistory";
import DashboardAccessGate from "@/components/auth/DashboardAccessGate";

// Backend status must be checked per request, never cached at build time.
export const dynamic = "force-dynamic";

export default function Home() {
  return (
    <DashboardAccessGate>
      <div className="as-page">
        <main id="market-overview" className="as-container py-7 sm:py-10">
          <header className="flex flex-wrap items-end justify-between gap-4">
            <div>
              <p className="as-kicker">NSE · 15-minute candles</p>
              <h1 id="terminal-title" className="as-title">Market dashboard</h1>
              <p className="as-subtitle mt-2 text-sm">Follow NIFTY 50 and BANK NIFTY. Open either chart for a closer look at the candles and signals.</p>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <ApiStatus />
              <a href="#historical-charts" className="as-button as-button--quiet">Historical candles</a>
            </div>
          </header>
          <section aria-label="Live index charts" className="mt-6">
            <LiveMarketDashboard />
          </section>
          <section id="historical-charts" className="mt-8 scroll-mt-6" aria-label="Historical index charts">
            <Upstox15mHistory />
          </section>
        </main>
        <footer className="as-footer">
          <p className="as-container py-5 text-xs leading-relaxed text-slate-400">Educational market analysis. Signals can be wrong or delayed. Trading involves risk of loss. AllSafe does not place orders.</p>
        </footer>
      </div>
    </DashboardAccessGate>
  );
}
