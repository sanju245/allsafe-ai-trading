"""Evidence gate for new strategy observations; no promotion or order execution.

The available year was already inspected. Research observations cannot be
advertised as validated signals or converted into a probability of success.
"""
from dataclasses import dataclass
from datetime import datetime

from app.indicators.strategies import STRATEGY_IDS, STRATEGY_LABELS, StrategyPoint


@dataclass(frozen=True)
class ResearchSignalSummary:
    id: str
    label: str
    signal: str


@dataclass(frozen=True)
class ResearchDecisionSummary:
    version: str
    status: str
    decision: str
    candidate_decision: str
    is_current_signal: bool
    candidate_is_current: bool
    selected_strategy: str | None
    regime: str
    adx: float | None
    reason: str
    evidence_status: str
    candle_timestamp: datetime | None
    evaluated_at: datetime
    strategies: list[ResearchSignalSummary]


def research_summary(point: StrategyPoint | None, *, evaluated_at: datetime,
                     fresh: bool = False, unavailable_reason: str | None = None) -> ResearchDecisionSummary:
    """All new rules stay research-only until prospective validation and review.

    Consensus is a fixed observation, never the post-hoc historical winner.
    A fresh observation is distinct from an eligible decision.
    """
    names = {1: "BUY", -1: "SELL", 0: "WAIT"}
    candidate = names[point.signals["regime_consensus"]] if point is not None else "DATA_UNAVAILABLE"
    reason = unavailable_reason or (
        "WAIT: new strategies have not passed prospective validation. "
        "Historical direction percentages are research results, not a live success probability."
    )
    if point is not None and not fresh:
        reason = "Current observation unavailable: feed or confirmed candle is not fresh. " + reason
    return ResearchDecisionSummary(
        version="strategy-research-v1", status="research_only", decision="WAIT",
        candidate_decision=candidate, is_current_signal=False,
        candidate_is_current=bool(point is not None and fresh and candidate in ("BUY", "SELL")),
        selected_strategy=None, regime={"warming": "warming_up", "trend": "trending", "range": "ranging", "transition": "transition"}.get(point.regime, "warming_up") if point else "warming_up",
        adx=point.adx if point else None, reason=reason, evidence_status="not_validated",
        candle_timestamp=point.timestamp if point else None, evaluated_at=evaluated_at,
        strategies=[ResearchSignalSummary(key, STRATEGY_LABELS[key], names[point.signals[key]]) for key in STRATEGY_IDS] if point else [],
    )
