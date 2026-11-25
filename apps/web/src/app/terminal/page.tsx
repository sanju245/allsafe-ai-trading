import ApiStatus from "@/components/ApiStatus";
import LiveMarketDashboard from "@/components/LiveMarketDashboard";
import Upstox15mHistory from "@/components/Upstox15mHistory";
import DashboardAccessGate from "@/components/auth/DashboardAccessGate";
import TerminalViews from "@/components/TerminalViews";

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
          </div>
        </div>
      </header>
      <main id="market-overview" className="as-container py-6 sm:pb-9">
        <TerminalViews live={<LiveMarketDashboard />} history={<Upstox15mHistory />} />
      </main>
      <footer className="as-footer">
        <p className="as-container py-5 text-xs leading-relaxed text-ui-muted">Educational market analysis. Signals can be wrong or delayed. Trading involves risk of loss. AllSafe does not place orders.</p>
      </footer>
    </DashboardAccessGate>
  );
}
