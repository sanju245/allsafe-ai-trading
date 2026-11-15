export type Signal = "BUY" | "SELL" | "WAIT" | "DATA_UNAVAILABLE";

export type IndicatorDecision = {
  decision: Signal;
  is_current_signal: boolean;
  feed_state: string;
  is_stale: boolean;
  candle_timestamp: string | null;
  evaluated_at: string;
  reason: string;
};

export type ResearchObservation = {
  version: "strategy-research-v1";
  status: "research_only";
  decision: "WAIT";
  candidate_decision: Signal;
  is_current_signal: false;
  candidate_is_current: boolean;
  selected_strategy: string | null;
  regime: "trending" | "ranging" | "transition" | "warming_up";
  adx: number | null;
  reason: string;
  evidence_status: "not_validated";
  candle_timestamp: string | null;
  evaluated_at: string;
  strategies: { id: string; label: string; signal: "BUY" | "SELL" | "WAIT" }[];
};

/** A stored signal can become history between refreshes. Fail closed. */
export function presentConfirmedDecision(
  decision: IndicatorDecision | null,
  latestConfirmed: { timestamp: string; is_incomplete?: boolean } | undefined,
  feedCurrent: boolean,
  nowMs: number,
): { signal: Signal; current: boolean; reason: string } {
  if (!decision || !latestConfirmed) {
    return { signal: "DATA_UNAVAILABLE", current: false, reason: "Waiting for a complete confirmed candle and indicator history." };
  }
  const candleMs = Date.parse(decision.candle_timestamp ?? "");
  const evaluatedMs = Date.parse(decision.evaluated_at);
  const fresh = feedCurrent && decision.feed_state === "live" && !decision.is_stale
    && !latestConfirmed.is_incomplete
    && decision.candle_timestamp === latestConfirmed.timestamp
    && Number.isFinite(candleMs) && Number.isFinite(evaluatedMs)
    && nowMs >= candleMs + 300_000 && nowMs < candleMs + 600_000
    && nowMs >= evaluatedMs && nowMs - evaluatedMs < 60_000;
  if (!fresh) {
    return { signal: decision.decision === "DATA_UNAVAILABLE" ? "DATA_UNAVAILABLE" : "WAIT", current: false,
      reason: "No current confirmed signal. The feed, candle, or evaluation is not current." };
  }
  if ((decision.decision === "BUY" || decision.decision === "SELL") && !decision.is_current_signal) {
    return { signal: "WAIT", current: false, reason: "No current confirmed directional signal." };
  }
  return { signal: decision.decision, current: true, reason: decision.reason };
}

export function researchObservationLabel(signal: string): string {
  return signal === "BUY" ? "Upward setup observed" : signal === "SELL" ? "Downward setup observed" : "No directional setup";
}
