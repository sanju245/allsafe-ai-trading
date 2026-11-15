type Summary = {
  signals: number;
  accuracy_pct: number | null;
  mean_gross_bps: number | null;
  mean_net_2bps?: number | null;
};
type StrategyResult = Summary & {
  id: string;
  label: string;
  evaluation_label: string;
  buy_signals: number;
  sell_signals: number;
  accuracy_after_cost_pct?: Record<string, number | null>;
  nonoverlapping_signals?: number;
  forward?: Summary | null;
};
export type StrategyResearchData = {
  version: string;
  audit_start: string;
  audit_end: string;
  horizon_minutes: number;
  evidence_status: string;
  walk_forward?: Summary & { blocks: number; wait_blocks: number };
  target_gates?: Record<string, { passed_retrospective_gate: boolean; production_eligible: boolean }>;
  instruments: Record<string, {
    strategies: StrategyResult[];
    coverage?: { sessions: number; candles: number; first: string; last: string };
  }>;
};

function metric(value: number | null | undefined, suffix = ""): string {
  return typeof value === "number" && Number.isFinite(value) ? `${value.toFixed(2)}${suffix}` : "N/A";
}

export default function StrategyResearchReport({ data }: { data: StrategyResearchData }) {
  const forward = data.walk_forward;
  const gates = Object.values(data.target_gates ?? {});
  const candidates = Object.values(data.instruments).flatMap((instrument) => instrument.strategies.filter((strategy) => !strategy.id.startsWith("decision_")));
  const allNegativeAfterCost = candidates.length > 0 && candidates.every((strategy) => typeof strategy.forward?.mean_net_2bps === "number" && strategy.forward.mean_net_2bps < 0);
  return (
    <div className="space-y-8">
      <section className="rounded-xl border border-amber-300/25 bg-amber-300/[0.04] p-5">
        <h2 className="text-xl font-semibold">Exploratory results · verification pending</h2>
        <p className="mt-3 text-sm leading-6 text-slate-300">This study reuses the previously examined {data.audit_start} to {data.audit_end} dataset. Chronological test blocks are retrospective checks on that same year. They are not unseen future validation, a live win probability, or an executed trading return.</p>
        <p className="mt-3 text-sm text-amber-200">The live research panel stays at WAIT while strategies await independent forward verification.</p>
        {gates.length > 0 && gates.every((gate) => !gate.passed_retrospective_gate) && <p className="mt-3 text-sm text-slate-300">None of the {gates.length} research candidates passed the retrospective performance, cost, and observation-count checks.</p>}
        {allNegativeAfterCost && <p className="mt-3 text-sm text-slate-300">Each research candidate had a negative average after the illustrative 2 bps cost in the later test blocks for both indices.</p>}
      </section>
      <section>
        <h2 className="text-xl font-semibold">Chronological strategy-selection test</h2>
        <p className="mt-2 text-sm leading-6 text-slate-400">Each block selects using earlier observations, then measures later observations. A block can choose WAIT when its selection rules are not satisfied.</p>
        {forward ? (
          <dl className="mt-4 grid gap-3 rounded-xl border border-white/10 p-5 sm:grid-cols-4">
            <div><dt className="text-xs text-slate-400">Test observations</dt><dd className="mt-1 text-xl">{forward.signals}</dd></div>
            <div><dt className="text-xs text-slate-400">Correct direction</dt><dd className="mt-1 text-xl">{metric(forward.accuracy_pct, "%")}</dd></div>
            <div><dt className="text-xs text-slate-400">Mean after 2 bps cost</dt><dd className="mt-1 text-xl">{metric(forward.mean_net_2bps, " bps")}</dd></div>
            <div><dt className="text-xs text-slate-400">WAIT blocks / total</dt><dd className="mt-1 text-xl">{forward.wait_blocks} / {forward.blocks}</dd></div>
          </dl>
        ) : <p className="mt-3 text-sm text-slate-400">Chronological selection results are not available yet.</p>}
        {forward?.signals === 0 && <p className="mt-3 text-sm text-slate-400">No qualifying test observations. Accuracy is unavailable; zero observations do not establish performance.</p>}
      </section>
      {Object.entries(data.instruments).map(([symbol, instrument]) => (
        <section key={symbol}>
          <h2 className="text-xl font-semibold">{symbol === "NIFTY50" ? "NIFTY 50" : symbol === "BANKNIFTY" ? "BANK NIFTY" : symbol}</h2>
          {instrument.coverage && <p className="mt-2 text-sm text-slate-400">Provider coverage: {instrument.coverage.first} to {instrument.coverage.last} · {instrument.coverage.sessions} sessions · {instrument.coverage.candles.toLocaleString("en-IN")} candles. Regular weekday sessions checked against the official exchange holiday calendar; special sessions are excluded.</p>}
          <div className="mt-4 overflow-x-auto rounded-xl border border-white/10">
            <table className="min-w-[680px] w-full text-left text-sm">
              <caption className="px-4 py-3 text-left text-xs text-slate-400">Later chronological test blocks for each fixed rule. Individual rules can be measured even when the selection policy chooses WAIT.</caption>
              <thead className="border-y border-white/10 bg-white/[0.03] text-slate-300"><tr><th className="p-4">Strategy</th><th className="p-4">Test observations</th><th className="p-4">Correct direction</th><th className="p-4">Mean gross</th><th className="p-4">Mean after 2 bps</th></tr></thead>
              <tbody>{instrument.strategies.map((strategy) => <tr key={strategy.id} className="border-b border-white/5 last:border-0"><th scope="row" className="p-4 font-medium">{strategy.label}</th><td className="p-4 tabular-nums">{strategy.forward?.signals ?? "N/A"}</td><td className="p-4 tabular-nums">{metric(strategy.forward?.accuracy_pct, "%")}</td><td className="p-4 tabular-nums">{metric(strategy.forward?.mean_gross_bps, " bps")}</td><td className="p-4 tabular-nums">{metric(strategy.forward?.mean_net_2bps, " bps")}</td></tr>)}</tbody>
            </table>
          </div>
          <details className="mt-4 rounded-xl border border-white/10 p-4">
            <summary className="cursor-pointer text-sm text-emerald-300">View all-year descriptive observations</summary>
            <p className="mt-3 text-xs leading-5 text-slate-400">The complete year was already used during research. These descriptive figures cannot establish future accuracy. Buy and sell counts describe independent signal events, which can overlap.</p>
            <div className="mt-3 overflow-x-auto"><table className="min-w-[730px] w-full text-left text-sm"><thead className="text-slate-400"><tr><th className="py-3 pr-4">Strategy</th><th className="pr-4">Observations</th><th className="pr-4">BUY / SELL</th><th className="pr-4">Gross accuracy</th><th className="pr-4">After 2 / 5 / 10 bps</th></tr></thead><tbody>{instrument.strategies.map((strategy) => <tr key={strategy.id} className="border-t border-white/5"><th scope="row" className="py-3 pr-4 font-medium">{strategy.label}</th><td className="pr-4">{strategy.signals}</td><td className="pr-4">{strategy.buy_signals} / {strategy.sell_signals}</td><td className="pr-4">{metric(strategy.accuracy_pct, "%")}</td><td className="pr-4">{["2", "5", "10"].map((cost) => metric(strategy.accuracy_after_cost_pct?.[cost], "%")).join(" / ")}</td></tr>)}</tbody></table></div>
          </details>
        </section>
      ))}
      <section className="rounded-xl border border-white/10 p-5">
        <h2 className="text-xl font-semibold">How observations are scored</h2>
        <ul className="mt-3 list-disc space-y-2 pl-5 text-sm leading-6 text-slate-400">
          <li>A signal uses a complete 5-minute candle. Entry uses the next candle&apos;s open; exit uses the close after {data.horizon_minutes} minutes in the same session.</li>
          <li>BUY is correct when the exit is higher than the entry; SELL is correct when it is lower. Flat outcomes are not wins. Missing bars and unavailable indicators do not produce scored trades.</li>
          <li>Costs are illustrative total round-trip basis points. Two basis points equal 0.02%. Actual fees, spreads and slippage vary.</li>
          <li>NIFTY and BANK NIFTY index direction does not measure options or futures trade profit. Overlapping events are correlated. No orders are placed by this site.</li>
          <li>Each strategy needs newly collected forward data before any predictive accuracy claim. Past results do not guarantee future outcomes.</li>
        </ul>
      </section>
      <section className="text-sm text-slate-400">
        <h2 className="text-xl font-semibold text-slate-100">Sources and protocol references</h2>
        <ul className="mt-3 list-disc space-y-2 pl-5">
          <li><a className="text-emerald-300 underline" href="https://upstox.com/developer/api-documentation/v3/get-historical-candle-data/">Upstox historical candle data and request limits</a></li>
          <li><a className="text-emerald-300 underline" href="https://nsearchives.nseindia.com/content/circulars/CMTR65587.pdf">NSE 2025 holiday circular</a>; <a className="text-emerald-300 underline" href="https://nsearchives.nseindia.com/content/circulars/CMTR71775.pdf">NSE 2026 holiday circular</a>; <a className="text-emerald-300 underline" href="https://nsearchives.nseindia.com/content/circulars/CMTR72260.pdf">additional January 2026 holiday</a></li>
          <li><a className="text-emerald-300 underline" href="https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf">The Probability of Backtest Overfitting</a> explains why repeated strategy selection can produce misleading historical results.</li>
          <li><a className="text-emerald-300 underline" href="https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html">Chronological evaluation reference</a>: preserve observation order when comparing earlier training and later test periods.</li>
        </ul>
      </section>
    </div>
  );
}
