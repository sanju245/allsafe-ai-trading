import ApiStatus from "@/components/ApiStatus";
import LiveMarketDashboard from "@/components/LiveMarketDashboard";
import Upstox15mHistory from "@/components/Upstox15mHistory";
import DashboardAccessGate from "@/components/auth/DashboardAccessGate";

// Backend status must be checked per request, never cached at build time.
export const dynamic = "force-dynamic";

export default function Home() {
  return (
    <DashboardAccessGate>
      <header className="workspace-page-top">
        <div className="as-container workspace-page-top-inner flex flex-wrap items-end justify-between gap-4">
          <div>
            <p className="as-kicker">NSE · 15-minute candles</p>
            <h1 id="terminal-title" className="as-title">Market dashboard</h1>
            <p className="as-subtitle mt-2 text-sm">Follow NIFTY 50 and BANK NIFTY and open either full chart for details.</p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <ApiStatus />
            <a href="#historical-charts" className="as-button as-button--quiet">Historical candles</a>
          </div>
        </div>
      </header>
      <main id="market-overview" className="as-container pb-6 sm:pb-9">
          <section aria-label="Live index charts" className="mt-6">
            <LiveMarketDashboard />
          </section>
          <section id="historical-charts" className="mt-8 scroll-mt-6" aria-label="Historical index charts">
            <Upstox15mHistory />
          </section>
      </main>
      <footer className="as-footer">
        <p className="as-container py-5 text-xs leading-relaxed text-ui-muted">Educational market analysis. Signals can be wrong or delayed. Trading involves risk of loss. AllSafe does not place orders.</p>
      </footer>
    </DashboardAccessGate>
  );
}
