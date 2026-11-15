import Link from "next/link";
import { presentConfirmedDecision, researchObservationLabel, type IndicatorDecision, type ResearchObservation } from "@/lib/strategyPresentation";

export default function StrategyDecisionPanel({ decision, research, latestConfirmed, feedCurrent, evaluatedNow }: {
  decision: IndicatorDecision | null;
  research: ResearchObservation | null;
  latestConfirmed: { timestamp: string; is_incomplete?: boolean } | undefined;
  feedCurrent: boolean;
  evaluatedNow: number;
}) {
  const confirmed = presentConfirmedDecision(decision, latestConfirmed, feedCurrent, evaluatedNow);
  return (
    <div className="mt-5 grid gap-3 sm:grid-cols-2">
      <section className="rounded-lg border border-white/10 bg-slate-950/50 p-4" aria-label="Confirmed indicator decision">
        <p className="text-xs uppercase tracking-wide text-slate-400">Five-indicator decision</p>
        <p className="mt-2 text-xl font-semibold">{confirmed.signal.replaceAll("_", " ")}</p>
        <p className="mt-2 text-sm text-slate-400">{confirmed.reason}</p>
        {confirmed.current && <p className="mt-2 text-xs text-slate-500">Evaluated from the latest complete 5-minute candle. Educational analysis.</p>}
      </section>
      <section className="rounded-lg border border-amber-300/20 bg-amber-300/[0.03] p-4" aria-label="Strategy research status">
        <p className="text-xs uppercase tracking-wide text-amber-200">Strategy research</p>
        <p className="mt-2 text-xl font-semibold">WAIT</p>
        <p className="mt-2 text-sm text-slate-300">Research pending verification. These strategy observations are exploratory and do not confirm a recommendation.</p>
        <p className="mt-2 text-xs text-slate-400">{research?.reason ?? "Waiting for research observations from confirmed candles."}</p>
        {research && (
          <details className="mt-3 text-sm">
            <summary className="cursor-pointer text-amber-200">View raw strategy observations</summary>
            <div className="mt-3 space-y-2 text-slate-400">
              <p>Market condition: {research.regime.replaceAll("_", " ")}{research.adx !== null && Number.isFinite(research.adx) ? ` · ADX ${research.adx.toFixed(1)}` : ""}</p>
              <p>Observations at the recorded candle timestamp. These are unvalidated research setups.</p>
              {research.candle_timestamp && <p>Candle opened {new Date(research.candle_timestamp).toLocaleString("en-IN", { timeZone: "Asia/Kolkata" })} IST.</p>}
              <ul className="space-y-2">
                {research.strategies.map((strategy) => <li key={strategy.id}><span className="text-slate-200">{strategy.label}</span>: {researchObservationLabel(strategy.signal)}</li>)}
              </ul>
            </div>
          </details>
        )}
        <Link href="/research" className="mt-3 inline-block text-sm text-amber-200 underline underline-offset-4">Read the research methods and results</Link>
      </section>
    </div>
  );
}
