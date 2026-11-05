"use client";

import { memo, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useAuth } from "@/components/auth/AuthProvider";
import BullBearHeroArena from "@/components/landing/BullBearHeroArena";
import IndianMarketStatusBadge from "@/components/landing/IndianMarketStatusBadge";
import LiveIstClock from "@/components/landing/LiveIstClock";
import ScrollReveal from "@/components/landing/ScrollReveal";

export interface LandingPageProps {
  /** Optional server UTC timestamp ISO string from /health for clock offset calibration */
  serverTimeUtc?: string | null;
  /** Optional backend online status */
  backendOnline?: boolean;
  /** Optional backend version string */
  backendVersion?: string;
}

type PreviewSymbol = "NIFTY50" | "BANKNIFTY";
type PreviewScenario = "BULLISH" | "BEARISH" | "SIDEWAYS";
type LegalDocKey = "privacy" | "terms" | "risk" | null;

interface IllustrativeMarketPreview {
  symbol: PreviewSymbol;
  displayName: string;
  exchange: string;
  lotSize: number;
  scenario: PreviewScenario;
  illustrativeSpot: string;
  illustrativeDelta: string;
  deltaPositive: boolean | null;
  regimeBadge: string;
  trendStructure: string;
  unanimousSignal: "BUY SIGNAL (ILLUSTRATIVE)" | "SELL SIGNAL (ILLUSTRATIVE)" | "WAIT / NO TRADE (ILLUSTRATIVE)";
  aiRecommendation: "LONG_SETUP" | "SHORT_SETUP" | "NO_TRADE";
  alignmentScore: number;
  volatilityMetric: string;
  volatilityRegime: string;
  momentumMetric: string;
  supportS1: string;
  supportS2: string;
  resistanceR1: string;
  resistanceR2: string;
  entryZone: string;
  stopLoss: string;
  target1: string;
  riskReward: string;
  recommendedLots: string;
  capitalRiskPct: string;
  agents: {
    name: string;
    status: "BULLISH" | "BEARISH" | "NEUTRAL";
    value: string;
    detail: string;
  }[];
  candles: {
    time: string;
    open: number;
    high: number;
    low: number;
    close: number;
    forming?: boolean;
  }[];
  aiSummary: string;
}

const ILLUSTRATIVE_PREVIEWS: Record<
  PreviewSymbol,
  Record<PreviewScenario, IllustrativeMarketPreview>
> = {
  NIFTY50: {
    BULLISH: {
      symbol: "NIFTY50",
      displayName: "NIFTY 50",
      exchange: "NSE Index",
      lotSize: 75,
      scenario: "BULLISH",
      illustrativeSpot: "24,485.60",
      illustrativeDelta: "+142.35 (+0.58%)",
      deltaPositive: true,
      regimeBadge: "BULLISH REGIME",
      trendStructure: "UPTREND (Multi-Horizon Demand Alignment)",
      unanimousSignal: "BUY SIGNAL (ILLUSTRATIVE)",
      aiRecommendation: "LONG_SETUP",
      alignmentScore: 92,
      volatilityMetric: "36.40 pts (0.15%)",
      volatilityRegime: "NORMAL (1.08x 20-bar Baseline)",
      momentumMetric: "+0.44% (Expanding Bullish Velocity)",
      supportS1: "24,420.00",
      supportS2: "24,365.00",
      resistanceR1: "24,550.00",
      resistanceR2: "24,610.00",
      entryZone: "24,480.00 – 24,488.00",
      stopLoss: "24,435.00 (Volatility-Bounded)",
      target1: "24,572.00",
      riskReward: "1.82x R:R",
      recommendedLots: "1 Lot (75 Qty)",
      capitalRiskPct: "1.90% of ₹2,00,000 Cap",
      agents: [
        {
          name: "AI Agent 01 · Dynamic Breakout & Protection",
          status: "BULLISH",
          value: "Floor 24,438.20",
          detail: "Confirmed 5m close above adaptive trailing protection line",
        },
        {
          name: "AI Agent 02 · Multi-Horizon Trend Structure",
          status: "BULLISH",
          value: "24,468 / 24,441",
          detail: "Short and medium trend vectors stacked upward",
        },
        {
          name: "AI Agent 03 · Buying Pressure & Velocity",
          status: "BULLISH",
          value: "Score 62.8",
          detail: "Sustained institutional buying participation above equilibrium",
        },
        {
          name: "AI Agent 04 · Impulse & Wave Convergence",
          status: "BULLISH",
          value: "+14.6 / +9.2",
          detail: "Positive wave spread expanding across confirmed bars",
        },
        {
          name: "AI Agent 05 · Volatility Regime & Band Guard",
          status: "BULLISH",
          value: "24,412.50 (UP)",
          detail: "Index holding above structural volatility support band",
        },
      ],
      candles: [
        { time: "09:35", open: 24390, high: 24415, low: 24382, close: 24410 },
        { time: "09:40", open: 24410, high: 24432, low: 24405, close: 24428 },
        { time: "09:45", open: 24428, high: 24450, low: 24420, close: 24446 },
        { time: "09:50", open: 24446, high: 24449, low: 24430, close: 24436 },
        { time: "09:55", open: 24436, high: 24468, low: 24434, close: 24464 },
        { time: "10:00", open: 24464, high: 24486, low: 24458, close: 24482 },
        { time: "10:05", open: 24482, high: 24494, low: 24476, close: 24486, forming: true },
      ],
      aiSummary:
        "Illustrative scenario: All 5 AI Agents are unanimously bullish on confirmed 5m candles with 15m and 1h multi-timeframe alignment, signaling a high-conviction BUY setup while isolating the forming candle (10:05 IST).",
    },
    BEARISH: {
      symbol: "NIFTY50",
      displayName: "NIFTY 50",
      exchange: "NSE Index",
      lotSize: 75,
      scenario: "BEARISH",
      illustrativeSpot: "24,192.40",
      illustrativeDelta: "−168.90 (−0.69%)",
      deltaPositive: false,
      regimeBadge: "BEARISH REGIME",
      trendStructure: "DOWNTREND (Multi-Horizon Supply Dominance)",
      unanimousSignal: "SELL SIGNAL (ILLUSTRATIVE)",
      aiRecommendation: "SHORT_SETUP",
      alignmentScore: 89,
      volatilityMetric: "42.10 pts (0.17%)",
      volatilityRegime: "HIGH (1.24x 20-bar Baseline)",
      momentumMetric: "−0.52% (Bearish Impulse Breakdown)",
      supportS1: "24,120.00",
      supportS2: "24,050.00",
      resistanceR1: "24,245.00",
      resistanceR2: "24,310.00",
      entryZone: "24,190.00 – 24,198.00",
      stopLoss: "24,245.00 (Volatility-Bounded)",
      target1: "24,102.00",
      riskReward: "1.71x R:R",
      recommendedLots: "1 Lot (75 Qty)",
      capitalRiskPct: "1.97% of ₹2,00,000 Cap",
      agents: [
        {
          name: "AI Agent 01 · Dynamic Breakout & Protection",
          status: "BEARISH",
          value: "Ceiling 24,241.80",
          detail: "Confirmed 5m breakdown below adaptive trailing barrier",
        },
        {
          name: "AI Agent 02 · Multi-Horizon Trend Structure",
          status: "BEARISH",
          value: "24,218 / 24,254",
          detail: "Short and medium trend vectors aligned downward",
        },
        {
          name: "AI Agent 03 · Buying Pressure & Velocity",
          status: "BEARISH",
          value: "Score 37.4",
          detail: "Selling pressure dominating below equilibrium threshold",
        },
        {
          name: "AI Agent 04 · Impulse & Wave Convergence",
          status: "BEARISH",
          value: "−18.2 / −11.4",
          detail: "Negative wave spread expanding downward",
        },
        {
          name: "AI Agent 05 · Volatility Regime & Band Guard",
          status: "BEARISH",
          value: "24,258.00 (DOWN)",
          detail: "Index trading below bearish structural volatility band",
        },
      ],
      candles: [
        { time: "09:35", open: 24310, high: 24318, low: 24280, close: 24285 },
        { time: "09:40", open: 24285, high: 24292, low: 24255, close: 24260 },
        { time: "09:45", open: 24260, high: 24274, low: 24248, close: 24268 },
        { time: "09:50", open: 24268, high: 24270, low: 24228, close: 24232 },
        { time: "09:55", open: 24232, high: 24238, low: 24205, close: 24210 },
        { time: "10:00", open: 24210, high: 24216, low: 24188, close: 24195 },
        { time: "10:05", open: 24195, high: 24202, low: 24184, close: 24192, forming: true },
      ],
      aiSummary:
        "Illustrative scenario: Unanimous 5-Agent bearish consensus following a confirmed session support breakdown, signaling when to SELL while capping capital exposure below 2.0%.",
    },
    SIDEWAYS: {
      symbol: "NIFTY50",
      displayName: "NIFTY 50",
      exchange: "NSE Index",
      lotSize: 75,
      scenario: "SIDEWAYS",
      illustrativeSpot: "24,340.15",
      illustrativeDelta: "+12.40 (+0.05%)",
      deltaPositive: null,
      regimeBadge: "SIDEWAYS / CHOP FILTER",
      trendStructure: "RANGE_BOUND (Mixed Agent Verdicts)",
      unanimousSignal: "WAIT / NO TRADE (ILLUSTRATIVE)",
      aiRecommendation: "NO_TRADE",
      alignmentScore: 41,
      volatilityMetric: "24.80 pts (0.10%)",
      volatilityRegime: "LOW (0.78x 20-bar Baseline)",
      momentumMetric: "+0.04% (Flat Mean-Reverting Oscillation)",
      supportS1: "24,310.00",
      supportS2: "24,275.00",
      resistanceR1: "24,370.00",
      resistanceR2: "24,415.00",
      entryZone: "Locked — Awaiting 5/5 AI Agent Consensus",
      stopLoss: "N/A (No Trade Filter Active)",
      target1: "N/A",
      riskReward: "< 1.50x Gate",
      recommendedLots: "0 Lots (Capital Preserved)",
      capitalRiskPct: "0.00% Risk Deployed",
      agents: [
        {
          name: "AI Agent 01 · Dynamic Breakout & Protection",
          status: "NEUTRAL",
          value: "Hold 24,322.10",
          detail: "No fresh bar crossover on confirmed 5m close",
        },
        {
          name: "AI Agent 02 · Multi-Horizon Trend Structure",
          status: "BULLISH",
          value: "24,339 / 24,335",
          detail: "Compressed trend vectors inside narrow 60-pt box",
        },
        {
          name: "AI Agent 03 · Buying Pressure & Velocity",
          status: "NEUTRAL",
          value: "Score 50.4",
          detail: "Midline equilibrium — directional conviction absent",
        },
        {
          name: "AI Agent 04 · Impulse & Wave Convergence",
          status: "BEARISH",
          value: "−1.4 / −0.8",
          detail: "Wave impulse slightly negative — contradicts Agent 02",
        },
        {
          name: "AI Agent 05 · Volatility Regime & Band Guard",
          status: "BULLISH",
          value: "24,308.00 (UP)",
          detail: "Holding band but lacking momentum consensus",
        },
      ],
      candles: [
        { time: "09:35", open: 24335, high: 24352, low: 24328, close: 24344 },
        { time: "09:40", open: 24344, high: 24348, low: 24326, close: 24330 },
        { time: "09:45", open: 24330, high: 24350, low: 24325, close: 24346 },
        { time: "09:50", open: 24346, high: 24355, low: 24332, close: 24336 },
        { time: "09:55", open: 24336, high: 24349, low: 24329, close: 24342 },
        { time: "10:00", open: 24342, high: 24347, low: 24331, close: 24338 },
        { time: "10:05", open: 24338, h: 24346, high: 24346, low: 24334, close: 24340, forming: true },
      ],
      aiSummary:
        "Illustrative scenario: Contradictory AI Agent verdicts detected during sideways chop. Because 5/5 unanimous consensus is not met, the coordinator enforces NO_TRADE to protect capital.",
    },
  },
  BANKNIFTY: {
    BULLISH: {
      symbol: "BANKNIFTY",
      displayName: "BANK NIFTY",
      exchange: "NSE Banking Index",
      lotSize: 30,
      scenario: "BULLISH",
      illustrativeSpot: "51,840.25",
      illustrativeDelta: "+345.80 (+0.67%)",
      deltaPositive: true,
      regimeBadge: "BULLISH REGIME",
      trendStructure: "UPTREND (Multi-Horizon Demand Alignment)",
      unanimousSignal: "BUY SIGNAL (ILLUSTRATIVE)",
      aiRecommendation: "LONG_SETUP",
      alignmentScore: 90,
      volatilityMetric: "92.50 pts (0.18%)",
      volatilityRegime: "NORMAL (1.12x 20-bar Baseline)",
      momentumMetric: "+0.51% (Strong Banking Breadth Impulse)",
      supportS1: "51,710.00",
      supportS2: "51,580.00",
      resistanceR1: "52,020.00",
      resistanceR2: "52,180.00",
      entryZone: "51,825.00 – 51,845.00",
      stopLoss: "51,720.00 (Volatility-Bounded)",
      target1: "52,045.00",
      riskReward: "1.72x R:R",
      recommendedLots: "1 Lot (30 Qty)",
      capitalRiskPct: "1.80% of ₹2,00,000 Cap",
      agents: [
        {
          name: "AI Agent 01 · Dynamic Breakout & Protection",
          status: "BULLISH",
          value: "Floor 51,724.00",
          detail: "Confirmed 5m bullish crossover above trailing protection line",
        },
        {
          name: "AI Agent 02 · Multi-Horizon Trend Structure",
          status: "BULLISH",
          value: "51,796 / 51,732",
          detail: "Bullish horizon alignment across 5m and 15m",
        },
        {
          name: "AI Agent 03 · Buying Pressure & Velocity",
          status: "BULLISH",
          value: "Score 64.1",
          detail: "Sustained buying pressure above 50.0 equilibrium",
        },
        {
          name: "AI Agent 04 · Impulse & Wave Convergence",
          status: "BULLISH",
          value: "+38.4 / +24.1",
          detail: "Positive wave impulse expanding across session bars",
        },
        {
          name: "AI Agent 05 · Volatility Regime & Band Guard",
          status: "BULLISH",
          value: "51,685.00 (UP)",
          detail: "Bullish volatility regime band confirmed",
        },
      ],
      candles: [
        { time: "09:35", open: 51610, high: 51665, low: 51590, close: 51652 },
        { time: "09:40", open: 51652, high: 51710, low: 51640, close: 51698 },
        { time: "09:45", open: 51698, high: 51760, low: 51688, close: 51748 },
        { time: "09:50", open: 51748, high: 51758, low: 51715, close: 51730 },
        { time: "09:55", open: 51730, high: 51802, low: 51724, close: 51790 },
        { time: "10:00", open: 51790, high: 51842, low: 51782, close: 51832 },
        { time: "10:05", open: 51832, high: 51858, low: 51818, close: 51840, forming: true },
      ],
      aiSummary:
        "Illustrative scenario: BANK NIFTY displays unanimous 5-Agent bullish confirmation with lot-size floor rounding (1 Lot = 30 units) keeping capital risk strictly below the 2.0% ceiling.",
    },
    BEARISH: {
      symbol: "BANKNIFTY",
      displayName: "BANK NIFTY",
      exchange: "NSE Banking Index",
      lotSize: 30,
      scenario: "BEARISH",
      illustrativeSpot: "51,120.80",
      illustrativeDelta: "−390.45 (−0.76%)",
      deltaPositive: false,
      regimeBadge: "BEARISH REGIME",
      trendStructure: "DOWNTREND (Multi-Horizon Supply Dominance)",
      unanimousSignal: "SELL SIGNAL (ILLUSTRATIVE)",
      aiRecommendation: "SHORT_SETUP",
      alignmentScore: 88,
      volatilityMetric: "104.20 pts (0.20%)",
      volatilityRegime: "HIGH (1.28x 20-bar Baseline)",
      momentumMetric: "−0.61% (Accelerated Selling Pressure)",
      supportS1: "50,940.00",
      supportS2: "50,780.00",
      resistanceR1: "51,245.00",
      resistanceR2: "51,380.00",
      entryZone: "51,115.00 – 51,130.00",
      stopLoss: "51,245.00 (Volatility-Bounded)",
      target1: "50,910.00",
      riskReward: "1.69x R:R",
      recommendedLots: "1 Lot (30 Qty)",
      capitalRiskPct: "1.86% of ₹2,00,000 Cap",
      agents: [
        {
          name: "AI Agent 01 · Dynamic Breakout & Protection",
          status: "BEARISH",
          value: "Ceiling 51,238.50",
          detail: "Confirmed 5m SELL breakdown below trailing barrier",
        },
        {
          name: "AI Agent 02 · Multi-Horizon Trend Structure",
          status: "BEARISH",
          value: "51,178 / 51,246",
          detail: "Bearish alignment across intraday timeframes",
        },
        {
          name: "AI Agent 03 · Buying Pressure & Velocity",
          status: "BEARISH",
          value: "Score 35.8",
          detail: "Selling pressure dominating below 50.0",
        },
        {
          name: "AI Agent 04 · Impulse & Wave Convergence",
          status: "BEARISH",
          value: "−42.6 / −27.9",
          detail: "Negative wave impulse expanding downward",
        },
        {
          name: "AI Agent 05 · Volatility Regime & Band Guard",
          status: "BEARISH",
          value: "51,264.00 (DOWN)",
          detail: "Bearish volatility band active",
        },
      ],
      candles: [
        { time: "09:35", open: 51380, high: 51395, low: 51310, close: 51320 },
        { time: "09:40", open: 51320, high: 51332, low: 51260, close: 51272 },
        { time: "09:45", open: 51272, high: 51295, low: 51245, close: 51284 },
        { time: "09:50", open: 51284, high: 51288, low: 51205, close: 51215 },
        { time: "09:55", open: 51215, high: 51225, low: 51155, close: 51162 },
        { time: "10:00", open: 51162, high: 51172, low: 51118, close: 51128 },
        { time: "10:05", open: 51128, high: 51140, low: 51105, close: 51120, forming: true },
      ],
      aiSummary:
        "Illustrative scenario: Unanimous 5-Agent bearish signal on BANK NIFTY with 15m/1h trend agreement. Stop-loss is validated within the session volatility safety band.",
    },
    SIDEWAYS: {
      symbol: "BANKNIFTY",
      displayName: "BANK NIFTY",
      exchange: "NSE Banking Index",
      lotSize: 30,
      scenario: "SIDEWAYS",
      illustrativeSpot: "51,480.00",
      illustrativeDelta: "−18.20 (−0.04%)",
      deltaPositive: null,
      regimeBadge: "SIDEWAYS / CHOP FILTER",
      trendStructure: "CHOPPY_CONFLICTING (Signal Lock Active)",
      unanimousSignal: "WAIT / NO TRADE (ILLUSTRATIVE)",
      aiRecommendation: "NO_TRADE",
      alignmentScore: 38,
      volatilityMetric: "68.40 pts (0.13%)",
      volatilityRegime: "LOW (0.81x 20-bar Baseline)",
      momentumMetric: "−0.03% (Range-Bound Consolidation)",
      supportS1: "51,390.00",
      supportS2: "51,290.00",
      resistanceR1: "51,560.00",
      resistanceR2: "51,670.00",
      entryZone: "Locked — Conflicting AI Agent Verdicts",
      stopLoss: "N/A (No Trade Filter Active)",
      target1: "N/A",
      riskReward: "< 1.50x Gate",
      recommendedLots: "0 Lots (Capital Preserved)",
      capitalRiskPct: "0.00% Risk Deployed",
      agents: [
        {
          name: "AI Agent 01 · Dynamic Breakout & Protection",
          status: "NEUTRAL",
          value: "Hold 51,442.00",
          detail: "No fresh bar crossover event",
        },
        {
          name: "AI Agent 02 · Multi-Horizon Trend Structure",
          status: "BEARISH",
          value: "51,476 / 51,484",
          detail: "Compressed horizon entanglement",
        },
        {
          name: "AI Agent 03 · Buying Pressure & Velocity",
          status: "NEUTRAL",
          value: "Score 49.2",
          detail: "Neutral session velocity",
        },
        {
          name: "AI Agent 04 · Impulse & Wave Convergence",
          status: "BULLISH",
          value: "+4.2 / +2.8",
          detail: "Minor positive wave contradicting Agent 02",
        },
        {
          name: "AI Agent 05 · Volatility Regime & Band Guard",
          status: "BEARISH",
          value: "51,545.00 (DOWN)",
          detail: "Overhead band resistance nearby",
        },
      ],
      candles: [
        { time: "09:35", open: 51475, high: 51510, low: 51455, close: 51492 },
        { time: "09:40", open: 51492, high: 51502, low: 51460, close: 51470 },
        { time: "09:45", open: 51470, high: 51498, low: 51458, close: 51488 },
        { time: "09:50", open: 51488, high: 51505, low: 51468, close: 51476 },
        { time: "09:55", open: 51476, high: 51495, low: 51464, close: 51484 },
        { time: "10:00", open: 51484, high: 51492, low: 51466, close: 51478 },
        { time: "10:05", open: 51478, high: 51490, low: 51470, close: 51480, forming: true },
      ],
      aiSummary:
        "Illustrative scenario: BANK NIFTY AI Agents are split inside a narrow consolidation zone. The consensus engine blocks trade entries until all 5 AI Agents align on a confirmed 5-minute bar.",
    },
  },
};

const VERIFIED_CAPABILITIES = [
  {
    capability: "5-Agent Unanimous Buy/Sell Consensus Engine",
    status: "IMPLEMENTED" as const,
    modulePath: "apps/api/app/indicators/decision.py",
    description:
      "Evaluates 5 specialized quantitative AI agents strictly over confirmed 5-minute IST candles before emitting a BUY, SELL, or WAIT decision.",
  },
  {
    capability: "Market Context & Regime Classification Engine",
    status: "IMPLEMENTED" as const,
    modulePath: "apps/api/app/signals/market_context.py",
    description:
      "Classifies BULLISH, BEARISH, and SIDEWAYS regimes, trend direction (UPTREND, DOWNTREND, RANGE_BOUND, CHOPPY_CONFLICTING), volatility expansion, momentum velocity, S1/S2/R1/R2 barriers, and 5m/15m/1h confirmation.",
  },
  {
    capability: "Explainable AI Decision Support & Confidence Scoring",
    status: "IMPLEMENTED" as const,
    modulePath: "apps/api/app/signals/ai_analysis.py",
    description:
      "Generates deterministic LONG_SETUP, SHORT_SETUP, or NO_TRADE recommendations with 0–95 confidence scoring, entry/invalidation zones, and contradiction diagnostics.",
  },
  {
    capability: "Institutional Risk Manager & Lot-Size Calculator",
    status: "IMPLEMENTED" as const,
    modulePath: "apps/api/app/signals/risk_manager.py & apps/web/src/lib/marketData.ts",
    description:
      "Enforces a hard 2.0% maximum capital risk ceiling, minimum 1.5x Risk/Reward gate, volatility-bounded stop distance validation, NIFTY 50 (75) & BANK NIFTY (30) lot rounding, and same-bar SignalDeduplicator.",
  },
  {
    capability: "Groww Read-Only Live Index Stream & 5m Candle Aggregator",
    status: "IMPLEMENTED" as const,
    modulePath: "apps/api/app/providers/groww_*.py & apps/api/app/market_data/live_*.py",
    description:
      "Ingests NIFTY 50 and BANK NIFTY ticks during 09:15–15:30 IST, separates forming candles from confirmed candles, rejects >5s future-skewed ticks, and locks signals when data is >60s stale.",
  },
  {
    capability: "Customer Sign-In, Admin Control Center & Backend IP Policy",
    status: "IMPLEMENTED" as const,
    modulePath: "apps/web/src/app/{login,admin,account} & apps/api/app/{security,auth}",
    description:
      "Authenticated customer sign-in (/login), role-based access control, server-side IP/CIDR allowlist enforcement, sliding-window rate limiting, and session management.",
  },
  {
    capability: "Autonomous Broker Order Placement / Live Trade Execution",
    status: "INTENTIONALLY DISABLED (SAFETY POLICY)" as const,
    modulePath: "apps/api/app/signals/schemas.py (read_only_mode=True, execution_disabled=True)",
    description:
      "Strictly disabled by architectural safety policy. AllSafe AI Trading is a read-only quantitative analysis and decision-support platform and never places orders.",
  },
  {
    capability: "Automated Exchange Holiday Feed Sync & Multi-Broker Routing",
    status: "PLANNED ROADMAP" as const,
    modulePath: "Planned Phase — External Calendar & Broker Adapter Expansion",
    description:
      "Automated remote sync of exchange circular updates and secondary market-data feed failover adapters beyond the bundled 2025–2027 NSE/BSE schedule.",
  },
];

function LegalModal({
  activeDoc,
  onClose,
}: {
  activeDoc: LegalDocKey;
  onClose: () => void;
}) {
  if (!activeDoc) return null;

  const titles: Record<Exclude<LegalDocKey, null>, string> = {
    privacy: "Privacy Policy & Data Handling Architecture",
    terms: "Terms and Conditions of Platform Use",
    risk: "Institutional Risk Disclosure & Read-Only Analysis Notice",
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="legal-modal-title"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4 backdrop-blur-sm"
    >
      <div className="max-h-[85vh] w-full max-w-2xl overflow-y-auto rounded-2xl border border-white/15 bg-[#0b1018] p-6 text-slate-200 shadow-2xl sm:p-8">
        <div className="flex items-start justify-between gap-4 border-b border-white/10 pb-4">
          <h3 id="legal-modal-title" className="text-lg font-bold text-white">
            {titles[activeDoc]}
          </h3>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close legal disclosure dialog"
            className="rounded-lg border border-white/10 bg-white/5 px-3 py-1 text-xs font-semibold text-slate-300 transition hover:bg-white/10 hover:text-white focus:outline-none focus:ring-2 focus:ring-emerald-400"
          >
            Close (Esc)
          </button>
        </div>

        <div className="mt-4 space-y-3 text-xs leading-relaxed text-slate-300 sm:text-sm">
          {activeDoc === "privacy" && (
            <>
              <p>
                <strong>1. Authentication &amp; Session Data:</strong> AllSafe AI
                Trading stores only the minimum account metadata required for
                authenticated access (`id`, `email`, `role`, `status`, and
                server-enforced `allowed_ip` policy). Session tokens are verified
                on the backend API.
              </p>
              <p>
                <strong>2. Secret &amp; Credential Redaction:</strong> Broker API
                credentials and JWT/HMAC signing secrets reside exclusively in
                server environment variables and are automatically redacted
                (`[REDACTED]`) across logs and error payloads.
              </p>
              <p>
                <strong>3. Client IP Verification:</strong> When IP-based access
                restrictions are configured for a customer profile, client IP
                matching is evaluated strictly on the backend API to protect
                institutional terminal sessions.
              </p>
            </>
          )}

          {activeDoc === "terms" && (
            <>
              <p>
                <strong>1. Read-Only Decision Support Scope:</strong> AllSafe AI
                Trading provides multi-agent quantitative calculations and
                explainable market regime analysis for NIFTY 50 and BANK NIFTY.
                The platform does not execute trades, hold client funds, or
                connect to order-execution endpoints.
              </p>
              <p>
                <strong>2. Authorized Access:</strong> Access to the live market
                terminal (`/terminal`) and administrative controls (`/admin`)
                requires valid credentials via `/login` and compliance with
                configured account status and IP allowlist policies.
              </p>
              <p>
                <strong>3. Signal Lock Integrity:</strong> Users must respect
                platform staleness locks (`STALE` / `CLOSED` / `NO_TRADE`).
                Historical or illustrative preview snapshots must never be
                interpreted as live actionable execution instructions.
              </p>
            </>
          )}

          {activeDoc === "risk" && (
            <>
              <p>
                <strong>1. Educational &amp; Quantitative Analysis Only:</strong>{" "}
                All outputs, 5-Agent consensus states, regime classifications, and
                position-sizing calculations are provided strictly for
                informational and educational decision support. Nothing on this
                platform constitutes investment, financial, legal, or tax advice.
              </p>
              <p>
                <strong>2. Market Risk &amp; No Profit Guarantee:</strong> Equity
                and index derivatives trading on NSE/BSE involves substantial
                risk of capital loss. Past performance or unanimous 5-Agent
                consensus never guarantees future profits or risk-free outcomes.
              </p>
              <p>
                <strong>3. Independent Verification:</strong> Market data feeds
                may experience latency, gaps, or provider interruptions. Always
                verify prices and risk parameters independently before making
                any financial decisions.
              </p>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function LandingPage({
  serverTimeUtc = null,
  backendOnline = false,
  backendVersion = "0.1.0",
}: LandingPageProps) {
  const { user } = useAuth();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [previewSymbol, setPreviewSymbol] = useState<PreviewSymbol>("NIFTY50");
  const [previewScenario, setPreviewScenario] = useState<PreviewScenario>("BULLISH");
  const [activeLegalDoc, setActiveLegalDoc] = useState<LegalDocKey>(null);

  const [serverTimeOffsetMs] = useState<number>(() => {
    if (!serverTimeUtc) return 0;
    const parsed = new Date(serverTimeUtc).getTime();
    if (!Number.isFinite(parsed)) return 0;
    return parsed - Date.now();
  });

  const handleCloseMenus = useCallback(() => {
    setMobileMenuOpen(false);
    setActiveLegalDoc(null);
  }, []);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        handleCloseMenus();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [handleCloseMenus]);

  const currentPreview = ILLUSTRATIVE_PREVIEWS[previewSymbol][previewScenario];

  const candlePrices = currentPreview.candles.flatMap((c) => [c.high, c.low]);
  const minCandlePrice = Math.min(...candlePrices);
  const maxCandlePrice = Math.max(...candlePrices);
  const priceSpan = Math.max(1, maxCandlePrice - minCandlePrice);

  return (
    <div className="min-h-screen bg-[#06090f] text-slate-100 selection:bg-emerald-500/30 selection:text-emerald-200">
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:fixed focus:top-3 focus:left-3 focus:z-50 focus:rounded-lg focus:bg-emerald-400 focus:px-4 focus:py-2 focus:text-sm focus:font-bold focus:text-slate-950"
      >
        Skip to main content
      </a>

      {/* ================================================================== */}
      {/* SECTION A — NAVIGATION BAR                                         */}
      {/* ================================================================== */}
      <header className="sticky top-0 z-40 border-b border-white/10 bg-[#06090f]/90 backdrop-blur-xl">
        <nav
          aria-label="Primary navigation"
          className="mx-auto flex max-w-7xl items-center justify-between gap-3 px-4 py-3.5 sm:px-6 lg:px-8"
        >
          <div className="flex items-center gap-3">
            <Link
              href="#home"
              className="group flex items-center gap-3 rounded-lg focus:outline-none focus:ring-2 focus:ring-emerald-400"
            >
              <span className="inline-flex h-9 w-9 items-center justify-center rounded-xl border border-emerald-500/40 bg-emerald-500/15 font-mono text-sm font-bold text-emerald-300 shadow-[0_0_16px_rgba(16,185,129,0.25)] transition group-hover:border-emerald-400">
                AS
              </span>
              <div>
                <span className="block text-base font-bold tracking-tight text-white sm:text-lg">
                  AllSafe <span className="text-emerald-400">AI Trading</span>
                </span>
                <span className="block font-mono text-[10px] uppercase tracking-[0.16em] text-slate-400">
                  NSE Quantitative Intelligence
                </span>
              </div>
            </Link>
          </div>

          {/* Desktop Navigation Links (Includes "What We Done" Page Link) */}
          <div className="hidden items-center gap-1 md:flex lg:gap-2">
            <a
              href="#home"
              className="rounded-lg px-3 py-2 text-xs font-medium text-slate-200 transition hover:bg-white/[0.06] hover:text-white focus:outline-none focus:ring-2 focus:ring-emerald-400 lg:text-sm"
            >
              Home
            </a>
            <Link
              href="/what-we-done"
              data-testid="nav-what-we-done"
              className="rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-3 py-2 text-xs font-semibold text-emerald-300 transition hover:bg-emerald-500/20 focus:outline-none focus:ring-2 focus:ring-emerald-400 lg:text-sm"
            >
              What We Done
            </Link>
            <a
              href="#ai-intelligence"
              className="rounded-lg px-3 py-2 text-xs font-medium text-slate-300 transition hover:bg-white/[0.06] hover:text-white focus:outline-none focus:ring-2 focus:ring-emerald-400 lg:text-sm"
            >
              AI Intelligence
            </a>
            <a
              href="#features"
              className="rounded-lg px-3 py-2 text-xs font-medium text-slate-300 transition hover:bg-white/[0.06] hover:text-white focus:outline-none focus:ring-2 focus:ring-emerald-400 lg:text-sm"
            >
              Features
            </a>
            <a
              href="#about"
              className="rounded-lg px-3 py-2 text-xs font-medium text-slate-300 transition hover:bg-white/[0.06] hover:text-white focus:outline-none focus:ring-2 focus:ring-emerald-400 lg:text-sm"
            >
              About
            </a>
          </div>

          <div className="flex items-center gap-2.5">
            <div className="hidden xl:block">
              <IndianMarketStatusBadge
                variant="compact"
                serverTimeOffsetMs={serverTimeOffsetMs}
                showCountdown={false}
              />
            </div>

            {user && (
              <Link
                href="/terminal"
                className="hidden min-h-[40px] items-center justify-center rounded-xl border border-white/15 bg-white/[0.05] px-3.5 py-2 text-xs font-semibold text-slate-100 transition hover:bg-white/10 focus:outline-none focus:ring-2 focus:ring-emerald-400 sm:inline-flex"
              >
                Open Live Terminal
              </Link>
            )}

            <Link
              href="/login"
              data-testid="nav-customer-signin"
              className="inline-flex min-h-[40px] items-center justify-center gap-2 rounded-xl border border-emerald-400/50 bg-emerald-500 px-4 py-2 text-xs font-bold text-slate-950 shadow-[0_0_20px_rgba(16,185,129,0.3)] transition hover:bg-emerald-400 active:scale-[0.99] focus:outline-none focus:ring-2 focus:ring-emerald-300 sm:text-sm"
            >
              <span>Customer Sign In</span>
              <span aria-hidden="true" className="font-mono text-xs">
                &rarr;
              </span>
            </Link>

            <button
              type="button"
              onClick={() => setMobileMenuOpen((prev) => !prev)}
              aria-expanded={mobileMenuOpen}
              aria-controls="mobile-navigation-drawer"
              aria-label={mobileMenuOpen ? "Close navigation menu" : "Open navigation menu"}
              className="inline-flex min-h-[40px] min-w-[40px] items-center justify-center rounded-xl border border-white/15 bg-white/[0.04] p-2 text-slate-200 transition hover:bg-white/10 focus:outline-none focus:ring-2 focus:ring-emerald-400 md:hidden"
            >
              <svg
                className="h-5 w-5"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                aria-hidden="true"
              >
                {mobileMenuOpen ? (
                  <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                ) : (
                  <path strokeLinecap="round" strokeLinejoin="round" d="M4 6h16M4 12h16M4 18h16" />
                )}
              </svg>
            </button>
          </div>
        </nav>

        {mobileMenuOpen && (
          <div
            id="mobile-navigation-drawer"
            className="border-t border-white/10 bg-[#080d16] px-4 py-4 md:hidden"
          >
            <div className="flex flex-col gap-1.5">
              <a
                href="#home"
                onClick={() => setMobileMenuOpen(false)}
                className="flex min-h-[44px] items-center rounded-lg px-3 py-2 text-sm font-medium text-white hover:bg-white/5"
              >
                Home
              </a>
              <Link
                href="/what-we-done"
                onClick={() => setMobileMenuOpen(false)}
                className="flex min-h-[44px] items-center rounded-lg bg-emerald-500/15 px-3 py-2 text-sm font-bold text-emerald-300"
              >
                What We Done (5 AI Agents)
              </Link>
              <a
                href="#ai-intelligence"
                onClick={() => setMobileMenuOpen(false)}
                className="flex min-h-[44px] items-center rounded-lg px-3 py-2 text-sm font-medium text-slate-200 hover:bg-white/5"
              >
                AI Intelligence
              </a>
              <a
                href="#features"
                onClick={() => setMobileMenuOpen(false)}
                className="flex min-h-[44px] items-center rounded-lg px-3 py-2 text-sm font-medium text-slate-200 hover:bg-white/5"
              >
                Features
              </a>
              <a
                href="#about"
                onClick={() => setMobileMenuOpen(false)}
                className="flex min-h-[44px] items-center rounded-lg px-3 py-2 text-sm font-medium text-slate-200 hover:bg-white/5"
              >
                About
              </a>

              <div className="mt-2 flex flex-col gap-2 border-t border-white/10 pt-3">
                {user && (
                  <Link
                    href="/terminal"
                    onClick={() => setMobileMenuOpen(false)}
                    className="flex min-h-[44px] items-center justify-center rounded-xl border border-white/15 bg-white/5 px-4 py-2.5 text-sm font-semibold text-white"
                  >
                    Open Live Market Terminal
                  </Link>
                )}
                <Link
                  href="/login"
                  onClick={() => setMobileMenuOpen(false)}
                  className="flex min-h-[44px] items-center justify-center rounded-xl bg-emerald-500 px-4 py-2.5 text-sm font-bold text-slate-950"
                >
                  Customer Sign In &rarr;
                </Link>
              </div>
            </div>
          </div>
        )}
      </header>

      <main id="main-content">
        {/* ================================================================== */}
        {/* SECTION B — ANIMATED HERO (CLOCK + MARKET STATUS + BULL VS BEAR)   */}
        {/* ================================================================== */}
        <section
          id="home"
          className="relative overflow-hidden border-b border-white/10 pt-6 pb-16 sm:pt-10 sm:pb-20"
        >
          <div
            aria-hidden="true"
            className="pointer-events-none absolute top-0 left-1/2 -z-10 h-[520px] w-full max-w-6xl -translate-x-1/2 bg-[radial-gradient(ellipse_at_top,rgba(16,185,129,0.12),rgba(244,63,94,0.05),transparent_70%)]"
          />

          <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
            <div className="mb-8 grid grid-cols-1 gap-3.5 md:grid-cols-2">
              <LiveIstClock serverTimeOffsetMs={serverTimeOffsetMs} variant="hero" />
              <IndianMarketStatusBadge
                serverTimeOffsetMs={serverTimeOffsetMs}
                variant="hero"
                showCountdown
              />
            </div>

            <div className="mx-auto max-w-4xl text-center">
              <div className="inline-flex flex-wrap items-center justify-center gap-2 rounded-full border border-emerald-500/30 bg-emerald-500/10 px-3.5 py-1 text-xs font-semibold text-emerald-300">
                <span>INSTITUTIONAL NSE INDEX TERMINAL</span>
                <span aria-hidden="true">&middot;</span>
                <span className="font-mono text-[11px] text-slate-200">
                  NIFTY 50 &amp; BANK NIFTY &middot; 5 AI AGENTS CONSENSUS
                </span>
              </div>

              <h1 className="mt-5 text-3xl font-extrabold tracking-tight text-white sm:text-5xl lg:text-6xl lg:leading-[1.08]">
                Quantitative AI Market Intelligence for{" "}
                <span className="bg-gradient-to-r from-emerald-300 via-emerald-400 to-teal-200 bg-clip-text text-transparent">
                  NIFTY 50
                </span>{" "}
                &amp;{" "}
                <span className="bg-gradient-to-r from-slate-100 via-slate-200 to-rose-300 bg-clip-text text-transparent">
                  BANK NIFTY
                </span>
              </h1>

              <p className="mx-auto mt-5 max-w-3xl text-sm leading-relaxed text-slate-300 sm:text-base lg:text-lg">
                Engineered for disciplined institutional analysis. AllSafe AI Trading
                deploys five specialized AI agents that inspect real-time 5-minute IST
                market structure, multi-timeframe regimes, and volatility-bounded risk
                limits—reaching unanimous consensus to tell you when to buy, when to
                sell, and when to wait.
              </p>

              <div className="mt-7 flex flex-col items-center justify-center gap-3.5 sm:flex-row">
                <a
                  href="#ai-intelligence"
                  data-testid="hero-explore-cta"
                  className="inline-flex min-h-[46px] w-full items-center justify-center gap-2 rounded-xl bg-emerald-500 px-6 py-3 text-sm font-bold text-slate-950 shadow-[0_0_28px_rgba(16,185,129,0.35)] transition hover:bg-emerald-400 focus:outline-none focus:ring-2 focus:ring-emerald-300 sm:w-auto"
                >
                  <span>Explore AI Intelligence</span>
                  <span aria-hidden="true" className="font-mono">
                    &darr;
                  </span>
                </a>

                <Link
                  href="/what-we-done"
                  data-testid="hero-what-we-done-cta"
                  className="inline-flex min-h-[46px] w-full items-center justify-center gap-2 rounded-xl border border-emerald-500/35 bg-emerald-500/10 px-6 py-3 text-sm font-bold text-emerald-300 transition hover:bg-emerald-500/20 focus:outline-none focus:ring-2 focus:ring-emerald-400 sm:w-auto"
                >
                  <span>What We Done (5 AI Agents)</span>
                  <span aria-hidden="true" className="font-mono">
                    &rarr;
                  </span>
                </Link>

                <Link
                  href="/login"
                  data-testid="hero-signin-cta"
                  className="inline-flex min-h-[46px] w-full items-center justify-center gap-2 rounded-xl border border-white/15 bg-white/[0.05] px-6 py-3 text-sm font-semibold text-white transition hover:border-emerald-400/40 hover:bg-white/[0.09] focus:outline-none focus:ring-2 focus:ring-emerald-400 sm:w-auto"
                >
                  <span>Customer Sign In</span>
                  <span aria-hidden="true" className="font-mono text-emerald-300">
                    &rarr;
                  </span>
                </Link>
              </div>
            </div>

            <div className="mt-10">
              <BullBearHeroArena />
            </div>

            <ScrollReveal className="mt-8 grid grid-cols-2 gap-3 sm:grid-cols-4">
              <div className="rounded-xl border border-white/10 bg-[#0b1018]/90 p-4">
                <div className="font-mono text-xs font-semibold uppercase tracking-wider text-slate-400">
                  Consensus Gate
                </div>
                <div className="mt-1 font-mono text-xl font-bold text-emerald-400 tabular-nums sm:text-2xl">
                  5 / 5 AI Agents
                </div>
                <div className="mt-0.5 text-xs text-slate-400">
                  Unanimous Buy / Sell verification
                </div>
              </div>

              <div className="rounded-xl border border-white/10 bg-[#0b1018]/90 p-4">
                <div className="font-mono text-xs font-semibold uppercase tracking-wider text-slate-400">
                  Timeframe Hierarchy
                </div>
                <div className="mt-1 font-mono text-xl font-bold text-white tabular-nums sm:text-2xl">
                  5m &middot; 15m &middot; 1h
                </div>
                <div className="mt-0.5 text-xs text-slate-400">
                  Confirmed vs. forming bar isolation
                </div>
              </div>

              <div className="rounded-xl border border-white/10 bg-[#0b1018]/90 p-4">
                <div className="font-mono text-xs font-semibold uppercase tracking-wider text-slate-400">
                  Hard Capital Risk Cap
                </div>
                <div className="mt-1 font-mono text-xl font-bold text-emerald-300 tabular-nums sm:text-2xl">
                  &le; 2.0% Max Risk
                </div>
                <div className="mt-0.5 text-xs text-slate-400">
                  &ge; 1.5x R:R &amp; dynamic volatility stop gate
                </div>
              </div>

              <div className="rounded-xl border border-white/10 bg-[#0b1018]/90 p-4">
                <div className="font-mono text-xs font-semibold uppercase tracking-wider text-slate-400">
                  Execution Safety
                </div>
                <div className="mt-1 font-mono text-xl font-bold text-amber-300 tabular-nums sm:text-2xl">
                  100% Read-Only
                </div>
                <div className="mt-0.5 text-xs text-slate-400">
                  Autonomous order execution disabled
                </div>
              </div>
            </ScrollReveal>
          </div>
        </section>

        {/* ================================================================== */}
        {/* SECTION C — AI MARKET INTELLIGENCE (ZERO INDICATOR NAMES DISCLOSED)*/}
        {/* ================================================================== */}
        <section
          id="ai-intelligence"
          className="border-b border-white/10 py-16 sm:py-20"
        >
          <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
            <ScrollReveal className="max-w-3xl">
              <p className="font-mono text-xs font-semibold uppercase tracking-[0.2em] text-emerald-400">
                Proprietary 5-Agent Quantitative Architecture
              </p>
              <h2 className="mt-2 text-2xl font-bold tracking-tight text-white sm:text-4xl">
                AI Market Intelligence Powered by Five Specialized Market Agents
              </h2>
              <p className="mt-3 text-sm leading-relaxed text-slate-300 sm:text-base">
                Every market insight in AllSafe AI Trading is computed by five
                specialized AI agents inspecting confirmed 5-minute IST candles on
                NIFTY 50 and BANK NIFTY—protecting proprietary signal parameters while
                delivering clear, auditable Buy, Sell, or Wait guidance.
              </p>
            </ScrollReveal>

            <div className="mt-10 grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
              <ScrollReveal
                delayMs={0}
                className="flex flex-col justify-between rounded-2xl border border-white/10 bg-[#0b1018] p-5 transition hover:border-emerald-500/35"
              >
                <div>
                  <div className="flex items-center justify-between gap-2">
                    <span className="rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-2.5 py-1 font-mono text-[11px] font-semibold text-emerald-300">
                      01 &middot; TREND ANALYSIS
                    </span>
                    <span className="font-mono text-[11px] text-slate-400">
                      Multi-Horizon
                    </span>
                  </div>
                  <h3 className="mt-4 text-lg font-bold text-white">
                    Market Trend &amp; Directional Structure
                  </h3>
                  <p className="mt-2 text-xs leading-relaxed text-slate-300 sm:text-sm">
                    Evaluates short-, medium-, and long-horizon price structure to
                    classify directional state into{" "}
                    <code className="text-emerald-300">UPTREND</code>,{" "}
                    <code className="text-rose-300">DOWNTREND</code>,{" "}
                    <code className="text-slate-200">RANGE_BOUND</code>, or{" "}
                    <code className="text-amber-300">CHOPPY_CONFLICTING</code>.
                  </p>
                </div>
                <div className="mt-4 border-t border-white/10 pt-3 font-mono text-[11px] text-emerald-300">
                  Verified: apps/api/app/signals/market_context.py
                </div>
              </ScrollReveal>

              <ScrollReveal
                delayMs={60}
                className="flex flex-col justify-between rounded-2xl border border-white/10 bg-[#0b1018] p-5 transition hover:border-emerald-500/35"
              >
                <div>
                  <div className="flex items-center justify-between gap-2">
                    <span className="rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-2.5 py-1 font-mono text-[11px] font-semibold text-emerald-300">
                      02 &middot; REGIME DETECTION
                    </span>
                    <span className="font-mono text-[11px] text-slate-400">
                      5m &middot; 15m &middot; 1h
                    </span>
                  </div>
                  <h3 className="mt-4 text-lg font-bold text-white">
                    Bullish / Bearish / Sideways Regime Engine
                  </h3>
                  <p className="mt-2 text-xs leading-relaxed text-slate-300 sm:text-sm">
                    Synthesizes 5-minute primary agent checks with resampled 15-minute
                    and 1-hour confirmation bars to detect{" "}
                    <code className="text-emerald-300">BULLISH</code>,{" "}
                    <code className="text-rose-300">BEARISH</code>, or{" "}
                    <code className="text-amber-300">SIDEWAYS</code> market regimes and
                    filter out counter-trend whipsaws.
                  </p>
                </div>
                <div className="mt-4 border-t border-white/10 pt-3 font-mono text-[11px] text-emerald-300">
                  Verified: compute_multi_timeframe_confirmation()
                </div>
              </ScrollReveal>

              <ScrollReveal
                delayMs={120}
                className="flex flex-col justify-between rounded-2xl border border-white/10 bg-[#0b1018] p-5 transition hover:border-emerald-500/35"
              >
                <div>
                  <div className="flex items-center justify-between gap-2">
                    <span className="rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-2.5 py-1 font-mono text-[11px] font-semibold text-emerald-300">
                      03 &middot; VOLATILITY &amp; MOMENTUM
                    </span>
                    <span className="font-mono text-[11px] text-slate-400">
                      Range &amp; Velocity
                    </span>
                  </div>
                  <h3 className="mt-4 text-lg font-bold text-white">
                    Volatility Expansion &amp; Momentum Telemetry
                  </h3>
                  <p className="mt-2 text-xs leading-relaxed text-slate-300 sm:text-sm">
                    Tracks 10-bar volatility range, 20-bar expansion ratios (
                    <code className="text-slate-200">LOW</code>,{" "}
                    <code className="text-emerald-300">NORMAL</code>,{" "}
                    <code className="text-amber-300">HIGH</code>,{" "}
                    <code className="text-rose-300">EXTREME</code>), and 10-bar
                    directional velocity across Indian index sessions.
                  </p>
                </div>
                <div className="mt-4 border-t border-white/10 pt-3 font-mono text-[11px] text-emerald-300">
                  Verified: compute_volatility_and_momentum()
                </div>
              </ScrollReveal>

              <ScrollReveal
                delayMs={180}
                className="flex flex-col justify-between rounded-2xl border border-white/10 bg-[#0b1018] p-5 transition hover:border-emerald-500/35"
              >
                <div>
                  <div className="flex items-center justify-between gap-2">
                    <span className="rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-2.5 py-1 font-mono text-[11px] font-semibold text-emerald-300">
                      04 &middot; 5 AI AGENTS CONSENSUS
                    </span>
                    <span className="font-mono text-[11px] text-slate-400">
                      5 Specialized Agents
                    </span>
                  </div>
                  <h3 className="mt-4 text-lg font-bold text-white">
                    Unanimous 5-Agent Buy / Sell Framework
                  </h3>
                  <p className="mt-2 text-xs leading-relaxed text-slate-300 sm:text-sm">
                    Requires unanimous 5/5 agreement across our Breakout, Trend
                    Structure, Buying Pressure, Wave Impulse, and Volatility Band AI
                    agents before emitting a{" "}
                    <code className="text-emerald-300">BUY</code> or{" "}
                    <code className="text-rose-300">SELL</code> decision.
                  </p>
                </div>
                <div className="mt-4 border-t border-white/10 pt-3 font-mono text-[11px] text-emerald-300">
                  <Link href="/what-we-done" className="underline hover:text-white">
                    Read full 5-Agent breakdown on What We Done &rarr;
                  </Link>
                </div>
              </ScrollReveal>

              <ScrollReveal
                delayMs={240}
                className="flex flex-col justify-between rounded-2xl border border-white/10 bg-[#0b1018] p-5 transition hover:border-emerald-500/35 md:col-span-2 lg:col-span-2"
              >
                <div>
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <span className="rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-2.5 py-1 font-mono text-[11px] font-semibold text-emerald-300">
                      05 &middot; EXPLAINABLE AI INSIGHTS &amp; BARRIER PROXIMITY
                    </span>
                    <span className="font-mono text-[11px] text-slate-400">
                      0–95 Confidence &middot; S1/S2 &amp; R1/R2
                    </span>
                  </div>
                  <h3 className="mt-4 text-lg font-bold text-white">
                    Explainable AI Decision Support with Support/Resistance Guardrails
                  </h3>
                  <p className="mt-2 text-xs leading-relaxed text-slate-300 sm:text-sm">
                    Produces human-auditable reasoning for{" "}
                    <code className="text-emerald-300">LONG_SETUP</code>,{" "}
                    <code className="text-rose-300">SHORT_SETUP</code>, or{" "}
                    <code className="text-amber-300">NO_TRADE</code> states, complete
                    with swing-pivot support (`S1`, `S2`) and resistance (`R1`, `R2`)
                    distances, contradiction warnings, and automatic staleness locks.
                  </p>
                </div>
                <div className="mt-4 border-t border-white/10 pt-3 font-mono text-[11px] text-emerald-300">
                  Verified: apps/api/app/signals/ai_analysis.py &amp; GET /api/v1/live/intelligence
                </div>
              </ScrollReveal>
            </div>

            {/* Verified Implemented vs Planned Capabilities Table */}
            <ScrollReveal className="mt-10 overflow-hidden rounded-2xl border border-white/10 bg-[#0b1018]">
              <div className="border-b border-white/10 px-5 py-4">
                <h3 className="text-base font-bold text-white sm:text-lg">
                  Repository Capability Verification Matrix (Implemented vs. Planned)
                </h3>
                <p className="mt-1 text-xs text-slate-400">
                  Transparent engineering inventory distinguishing verified codebase
                  modules from safety-disabled or planned roadmap items.
                </p>
              </div>

              <div className="overflow-x-auto">
                <table className="w-full border-collapse text-left text-xs">
                  <thead>
                    <tr className="border-b border-white/10 bg-white/[0.02] font-mono text-[11px] uppercase tracking-wider text-slate-400">
                      <th className="py-3 px-4">Capability</th>
                      <th className="py-3 px-4">Verification Status</th>
                      <th className="py-3 px-4">Repository Module / Path</th>
                      <th className="py-3 px-4">Verified Technical Scope</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-white/10">
                    {VERIFIED_CAPABILITIES.map((item) => (
                      <tr key={item.capability} className="hover:bg-white/[0.02]">
                        <td className="py-3 px-4 font-semibold text-white">
                          {item.capability}
                        </td>
                        <td className="py-3 px-4">
                          <span
                            className={`inline-flex rounded-full border px-2.5 py-0.5 font-mono text-[10px] font-bold ${
                              item.status === "IMPLEMENTED"
                                ? "border-emerald-500/30 bg-emerald-500/15 text-emerald-300"
                                : item.status.startsWith("INTENTIONALLY")
                                  ? "border-amber-500/30 bg-amber-500/15 text-amber-300"
                                  : "border-sky-500/30 bg-sky-500/15 text-sky-300"
                            }`}
                          >
                            {item.status}
                          </span>
                        </td>
                        <td className="py-3 px-4 font-mono text-[11px] text-slate-300">
                          {item.modulePath}
                        </td>
                        <td className="py-3 px-4 text-slate-300">
                          {item.description}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </ScrollReveal>
          </div>
        </section>

        {/* ================================================================== */}
        {/* SECTION D — MARKET DASHBOARD PREVIEW (ZERO INDICATOR NAMES)        */}
        {/* ================================================================== */}
        <section
          id="dashboard-preview"
          className="border-b border-white/10 bg-[#080c14] py-16 sm:py-20"
        >
          <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
            <ScrollReveal className="flex flex-col justify-between gap-4 lg:flex-row lg:items-end">
              <div className="max-w-3xl">
                <div className="inline-flex items-center gap-2 rounded-full border border-amber-500/35 bg-amber-500/10 px-3 py-1 font-mono text-[11px] font-semibold text-amber-200">
                  <span>ILLUSTRATIVE TERMINAL SIMULATION</span>
                  <span aria-hidden="true">&middot;</span>
                  <span>NOT LIVE MARKET PRICES</span>
                </div>
                <h2 className="mt-3 text-2xl font-bold tracking-tight text-white sm:text-4xl">
                  Interactive Market Dashboard Preview
                </h2>
                <p className="mt-2 text-sm text-slate-300 sm:text-base">
                  Explore how our 5 AI Agents inspect{" "}
                  <strong className="text-white">NIFTY 50</strong> and{" "}
                  <strong className="text-white">BANK NIFTY</strong> 5-minute
                  candlesticks and risk sizing across bullish, bearish, and sideways
                  regimes.
                </p>
              </div>

              <div className="flex flex-wrap items-center gap-2">
                <div
                  role="group"
                  aria-label="Select preview index instrument"
                  className="inline-flex rounded-xl border border-white/10 bg-[#0b1018] p-1"
                >
                  {(["NIFTY50", "BANKNIFTY"] as const).map((sym) => (
                    <button
                      key={sym}
                      type="button"
                      onClick={() => setPreviewSymbol(sym)}
                      aria-pressed={previewSymbol === sym}
                      className={`min-h-[36px] rounded-lg px-3.5 py-1.5 font-mono text-xs font-bold transition ${
                        previewSymbol === sym
                          ? "bg-emerald-500 text-slate-950"
                          : "text-slate-300 hover:text-white"
                      }`}
                    >
                      {sym === "NIFTY50" ? "NIFTY 50" : "BANK NIFTY"}
                    </button>
                  ))}
                </div>

                <div
                  role="group"
                  aria-label="Select illustrative market regime scenario"
                  className="inline-flex rounded-xl border border-white/10 bg-[#0b1018] p-1"
                >
                  {(["BULLISH", "BEARISH", "SIDEWAYS"] as const).map((scen) => (
                    <button
                      key={scen}
                      type="button"
                      onClick={() => setPreviewScenario(scen)}
                      aria-pressed={previewScenario === scen}
                      className={`min-h-[36px] rounded-lg px-3 py-1.5 font-mono text-xs font-semibold transition ${
                        previewScenario === scen
                          ? scen === "BULLISH"
                            ? "bg-emerald-500/25 text-emerald-200 border border-emerald-500/40"
                            : scen === "BEARISH"
                              ? "bg-rose-500/25 text-rose-200 border border-rose-500/40"
                              : "bg-amber-500/25 text-amber-200 border border-amber-500/40"
                          : "text-slate-400 hover:text-slate-200"
                      }`}
                    >
                      {scen}
                    </button>
                  ))}
                </div>
              </div>
            </ScrollReveal>

            <ScrollReveal className="mt-8 overflow-hidden rounded-2xl border border-white/15 bg-[#0b1018] shadow-2xl">
              <div className="flex flex-wrap items-center justify-between gap-2 border-b border-white/10 bg-amber-500/[0.08] px-4 py-2.5 text-xs text-amber-200 sm:px-6">
                <div className="flex items-center gap-2 font-medium">
                  <span className="inline-flex h-2 w-2 rounded-full bg-amber-400" />
                  <span>
                    <strong>ILLUSTRATIVE SAMPLE DATA:</strong> Prices, candles, and
                    signals shown below are static educational examples demonstrating
                    terminal UI behavior—never fabricated as live exchange quotes.
                  </span>
                </div>
                <Link
                  href="/login"
                  className="font-mono text-xs font-bold text-emerald-300 underline-offset-2 hover:underline"
                >
                  Sign In for Live Terminal &rarr;
                </Link>
              </div>

              <div className="flex flex-wrap items-center justify-between gap-4 border-b border-white/10 px-4 py-4 sm:px-6">
                <div>
                  <div className="flex items-center gap-2.5">
                    <span className="text-xl font-extrabold tracking-tight text-white sm:text-2xl">
                      {currentPreview.displayName}
                    </span>
                    <span className="rounded border border-white/10 bg-white/[0.04] px-2 py-0.5 font-mono text-[11px] text-slate-300">
                      {currentPreview.exchange} &middot; Lot Size: {currentPreview.lotSize}
                    </span>
                    <span className="rounded border border-amber-500/30 bg-amber-500/10 px-2 py-0.5 font-mono text-[10px] font-semibold text-amber-300">
                      SAMPLE SNAPSHOT
                    </span>
                  </div>
                  <p className="mt-1 font-mono text-xs text-slate-400">
                    Structure: {currentPreview.trendStructure}
                  </p>
                </div>

                <div className="flex flex-wrap items-center gap-4 tabular-nums">
                  <div className="text-right">
                    <div className="font-mono text-2xl font-bold text-white">
                      {currentPreview.illustrativeSpot}
                    </div>
                    <div
                      className={`font-mono text-xs font-semibold ${
                        currentPreview.deltaPositive === true
                          ? "text-emerald-400"
                          : currentPreview.deltaPositive === false
                            ? "text-rose-400"
                            : "text-slate-300"
                      }`}
                    >
                      {currentPreview.illustrativeDelta} (Illustrative)
                    </div>
                  </div>

                  <div
                    className={`rounded-xl border px-3.5 py-2 font-mono text-xs font-bold ${
                      currentPreview.scenario === "BULLISH"
                        ? "border-emerald-500/40 bg-emerald-500/15 text-emerald-300"
                        : currentPreview.scenario === "BEARISH"
                          ? "border-rose-500/40 bg-rose-500/15 text-rose-300"
                          : "border-amber-500/40 bg-amber-500/15 text-amber-300"
                    }`}
                  >
                    <div>{currentPreview.regimeBadge}</div>
                    <div className="mt-0.5 text-[11px] text-white">
                      {currentPreview.unanimousSignal}
                    </div>
                  </div>
                </div>
              </div>

              <div className="grid grid-cols-1 gap-6 p-4 sm:p-6 lg:grid-cols-12">
                <div className="space-y-4 lg:col-span-7">
                  <div className="rounded-xl border border-white/10 bg-[#070b11] p-4">
                    <div className="mb-3 flex flex-wrap items-center justify-between gap-2 text-xs">
                      <span className="font-mono font-semibold text-slate-200">
                        5-Minute IST Candlestick Series (Confirmed vs. Forming Bar)
                      </span>
                      <div className="flex items-center gap-3 text-[11px] text-slate-400">
                        <span className="inline-flex items-center gap-1">
                          <span className="h-2 w-2 rounded-sm bg-emerald-400" />
                          Confirmed Bull
                        </span>
                        <span className="inline-flex items-center gap-1">
                          <span className="h-2 w-2 rounded-sm bg-rose-400" />
                          Confirmed Bear
                        </span>
                        <span className="inline-flex items-center gap-1">
                          <span className="h-2 w-2 rounded-sm border border-amber-400 bg-amber-400/30" />
                          Forming Bar (Isolated)
                        </span>
                      </div>
                    </div>

                    <div className="h-52 w-full">
                      <svg
                        viewBox="0 0 560 200"
                        className="h-full w-full"
                        role="img"
                        aria-label={`Illustrative 5-minute candlestick preview for ${currentPreview.displayName}`}
                      >
                        <line x1="20" y1="35" x2="540" y2="35" stroke="rgba(255,255,255,0.06)" />
                        <line x1="20" y1="95" x2="540" y2="95" stroke="rgba(255,255,255,0.06)" />
                        <line x1="20" y1="155" x2="540" y2="155" stroke="rgba(255,255,255,0.06)" />

                        {currentPreview.candles.map((candle, index) => {
                          const xCenter = 60 + index * 72;
                          const yHigh =
                            20 +
                            ((maxCandlePrice - candle.high) / priceSpan) * 140;
                          const yLow =
                            20 +
                            ((maxCandlePrice - candle.low) / priceSpan) * 140;
                          const yOpen =
                            20 +
                            ((maxCandlePrice - candle.open) / priceSpan) * 140;
                          const yClose =
                            20 +
                            ((maxCandlePrice - candle.close) / priceSpan) * 140;
                          const isBull = candle.close >= candle.open;
                          const bodyTop = Math.min(yOpen, yClose);
                          const bodyHeight = Math.max(4, Math.abs(yClose - yOpen));
                          const strokeColor = candle.forming
                            ? "#fbbf24"
                            : isBull
                              ? "#34d399"
                              : "#fb7185";
                          const fillColor = candle.forming
                            ? "rgba(251,191,36,0.28)"
                            : isBull
                              ? "#10b981"
                              : "#f43f5e";

                          return (
                            <g key={candle.time}>
                              <line
                                x1={xCenter}
                                y1={yHigh}
                                x2={xCenter}
                                y2={yLow}
                                stroke={strokeColor}
                                strokeWidth="2"
                              />
                              <rect
                                x={xCenter - 13}
                                y={bodyTop}
                                width="26"
                                height={bodyHeight}
                                fill={fillColor}
                                stroke={strokeColor}
                                strokeWidth="1.5"
                                strokeDasharray={candle.forming ? "3 2" : undefined}
                                rx="2"
                              />
                              <text
                                x={xCenter}
                                y="186"
                                textAnchor="middle"
                                fill="#94a3b8"
                                fontSize="10"
                                fontFamily="monospace"
                              >
                                {candle.time}
                              </text>
                            </g>
                          );
                        })}
                      </svg>
                    </div>
                  </div>

                  <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                    <div className="rounded-xl border border-white/10 bg-[#070b11] p-3">
                      <div className="text-[10px] font-semibold uppercase tracking-wider text-slate-400">
                        Session Volatility
                      </div>
                      <div className="mt-1 font-mono text-xs font-bold text-white tabular-nums">
                        {currentPreview.volatilityMetric}
                      </div>
                      <div className="mt-0.5 text-[10px] text-slate-400">
                        {currentPreview.volatilityRegime}
                      </div>
                    </div>

                    <div className="rounded-xl border border-white/10 bg-[#070b11] p-3">
                      <div className="text-[10px] font-semibold uppercase tracking-wider text-slate-400">
                        Momentum Velocity
                      </div>
                      <div className="mt-1 font-mono text-xs font-bold text-white tabular-nums">
                        {currentPreview.momentumMetric}
                      </div>
                      <div className="mt-0.5 text-[10px] text-slate-400">
                        10-bar confirmed rate
                      </div>
                    </div>

                    <div className="rounded-xl border border-white/10 bg-[#070b11] p-3">
                      <div className="text-[10px] font-semibold uppercase tracking-wider text-slate-400">
                        Support (S1 / S2)
                      </div>
                      <div className="mt-1 font-mono text-xs font-bold text-emerald-300 tabular-nums">
                        {currentPreview.supportS1}
                      </div>
                      <div className="mt-0.5 font-mono text-[10px] text-slate-400 tabular-nums">
                        S2: {currentPreview.supportS2}
                      </div>
                    </div>

                    <div className="rounded-xl border border-white/10 bg-[#070b11] p-3">
                      <div className="text-[10px] font-semibold uppercase tracking-wider text-slate-400">
                        Resistance (R1 / R2)
                      </div>
                      <div className="mt-1 font-mono text-xs font-bold text-rose-300 tabular-nums">
                        {currentPreview.resistanceR1}
                      </div>
                      <div className="mt-0.5 font-mono text-[10px] text-slate-400 tabular-nums">
                        R2: {currentPreview.resistanceR2}
                      </div>
                    </div>
                  </div>

                  <div className="rounded-xl border border-white/10 bg-[#070b11] p-4">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <span className="font-mono text-xs font-bold uppercase tracking-wider text-emerald-300">
                        AI Decision Support Summary &middot; Recommendation:{" "}
                        {currentPreview.aiRecommendation}
                      </span>
                      <span className="rounded border border-white/10 bg-white/5 px-2 py-0.5 font-mono text-xs font-semibold text-white tabular-nums">
                        Alignment Score: {currentPreview.alignmentScore} / 95
                      </span>
                    </div>
                    <p className="mt-2 text-xs leading-relaxed text-slate-300">
                      {currentPreview.aiSummary}
                    </p>
                  </div>
                </div>

                {/* Right 5 Columns: 5 AI Agents Consensus Panel + Risk Sizing Preview */}
                <div className="space-y-4 lg:col-span-5">
                  <div className="rounded-xl border border-white/10 bg-[#070b11] p-4">
                    <div className="mb-3 flex items-center justify-between">
                      <h3 className="font-mono text-xs font-bold uppercase tracking-wider text-white">
                        5 AI Agents Consensus Panel
                      </h3>
                      <span className="font-mono text-[11px] text-slate-400">
                        Unanimous Buy / Sell Gate
                      </span>
                    </div>

                    <div className="space-y-2.5">
                      {currentPreview.agents.map((ag) => (
                        <div
                          key={ag.name}
                          className="rounded-lg border border-white/10 bg-[#0b1018] px-3 py-2.5"
                        >
                          <div className="flex items-center justify-between gap-2">
                            <span className="text-xs font-semibold text-white">
                              {ag.name}
                            </span>
                            <span
                              className={`rounded px-2 py-0.5 font-mono text-[10px] font-bold ${
                                ag.status === "BULLISH"
                                  ? "bg-emerald-500/20 text-emerald-300"
                                  : ag.status === "BEARISH"
                                    ? "bg-rose-500/20 text-rose-300"
                                    : "bg-amber-500/20 text-amber-300"
                              }`}
                            >
                              {ag.status} &middot; {ag.value}
                            </span>
                          </div>
                          <div className="mt-1 text-[11px] text-slate-400">
                            {ag.detail}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>

                  <div className="rounded-xl border border-white/10 bg-[#070b11] p-4 tabular-nums">
                    <div className="flex items-center justify-between border-b border-white/10 pb-2.5">
                      <span className="font-mono text-xs font-bold uppercase tracking-wider text-white">
                        Risk Manager &amp; Lot Sizing (Illustrative)
                      </span>
                      <span className="rounded bg-emerald-500/15 px-2 py-0.5 font-mono text-[10px] font-semibold text-emerald-300">
                        Max Risk Cap: 2.0%
                      </span>
                    </div>

                    <div className="mt-3 grid grid-cols-2 gap-2.5 text-xs">
                      <div className="rounded-lg border border-white/5 bg-[#0b1018] p-2.5">
                        <div className="text-[10px] text-slate-400">Entry Zone</div>
                        <div className="mt-0.5 font-mono font-semibold text-white">
                          {currentPreview.entryZone}
                        </div>
                      </div>
                      <div className="rounded-lg border border-white/5 bg-[#0b1018] p-2.5">
                        <div className="text-[10px] text-slate-400">Dynamic Stop-Loss</div>
                        <div className="mt-0.5 font-mono font-semibold text-rose-300">
                          {currentPreview.stopLoss}
                        </div>
                      </div>
                      <div className="rounded-lg border border-white/5 bg-[#0b1018] p-2.5">
                        <div className="text-[10px] text-slate-400">
                          Target 1 &amp; R:R Gate
                        </div>
                        <div className="mt-0.5 font-mono font-semibold text-emerald-300">
                          {currentPreview.target1} ({currentPreview.riskReward})
                        </div>
                      </div>
                      <div className="rounded-lg border border-white/5 bg-[#0b1018] p-2.5">
                        <div className="text-[10px] text-slate-400">
                          Position Size ({currentPreview.lotSize}/Lot)
                        </div>
                        <div className="mt-0.5 font-mono font-semibold text-white">
                          {currentPreview.recommendedLots} ({currentPreview.capitalRiskPct})
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </ScrollReveal>
          </div>
        </section>

        {/* ================================================================== */}
        {/* SECTION E — INTELLIGENT TRADING FEATURES                           */}
        {/* ================================================================== */}
        <section id="features" className="border-b border-white/10 py-16 sm:py-20">
          <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
            <ScrollReveal className="max-w-3xl">
              <p className="font-mono text-xs font-semibold uppercase tracking-[0.2em] text-emerald-400">
                Verified Platform Capabilities
              </p>
              <h2 className="mt-2 text-2xl font-bold tracking-tight text-white sm:text-4xl">
                Intelligent Trading Decision-Support Features
              </h2>
              <p className="mt-3 text-sm leading-relaxed text-slate-300 sm:text-base">
                Built on five specialized AI market agents with zero hype, zero
                autonomous order execution, and strict risk preservation rules.
              </p>
            </ScrollReveal>

            <div className="mt-10 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
              <ScrollReveal
                delayMs={0}
                className="rounded-2xl border border-white/10 bg-[#0b1018] p-6"
              >
                <div className="font-mono text-xs font-bold uppercase tracking-wider text-emerald-400">
                  Breakout &amp; Protection Agent
                </div>
                <h3 className="mt-2 text-lg font-bold text-white">
                  Adaptive Trailing Stop &amp; Crossover Detection
                </h3>
                <p className="mt-2 text-xs leading-relaxed text-slate-300 sm:text-sm">
                  Monitors confirmed 5-minute IST closes with directional trailing
                  stop ratcheting and structural crossover detection to pinpoint fresh
                  market shifts.
                </p>
              </ScrollReveal>

              <ScrollReveal
                delayMs={60}
                className="rounded-2xl border border-white/10 bg-[#0b1018] p-6"
              >
                <div className="font-mono text-xs font-bold uppercase tracking-wider text-emerald-400">
                  5-Agent Unanimity
                </div>
                <h3 className="mt-2 text-lg font-bold text-white">
                  Multi-Agent Buy &amp; Sell Consensus
                </h3>
                <p className="mt-2 text-xs leading-relaxed text-slate-300 sm:text-sm">
                  Combines our Trend Structure, Buying Pressure, Wave Impulse,
                  Breakout, and Volatility Band AI agents into a single unanimous
                  decision gate.
                </p>
              </ScrollReveal>

              <ScrollReveal
                delayMs={120}
                className="rounded-2xl border border-white/10 bg-[#0b1018] p-6"
              >
                <div className="font-mono text-xs font-bold uppercase tracking-wider text-emerald-400">
                  Capital Preservation
                </div>
                <h3 className="mt-2 text-lg font-bold text-white">
                  Volatility-Bounded Risk Management
                </h3>
                <p className="mt-2 text-xs leading-relaxed text-slate-300 sm:text-sm">
                  Caps per-trade capital risk at `2.0%`, requires a minimum `1.5x`
                  reward-to-risk ratio, validates stop distance against live session
                  volatility, and rounds down to exact NSE lot multiples (`75` / `30`).
                </p>
              </ScrollReveal>

              <ScrollReveal
                delayMs={180}
                className="rounded-2xl border border-white/10 bg-[#0b1018] p-6"
              >
                <div className="font-mono text-xs font-bold uppercase tracking-wider text-emerald-400">
                  Candle Grid Integrity
                </div>
                <h3 className="mt-2 text-lg font-bold text-white">
                  Confirmed vs. Forming Bar Separation
                </h3>
                <p className="mt-2 text-xs leading-relaxed text-slate-300 sm:text-sm">
                  Aligns intraday ticks to the official 09:15–15:30 IST 5-minute grid,
                  isolates the in-progress forming candle from confirmed history, and
                  suppresses duplicate intra-bar signal alerts.
                </p>
              </ScrollReveal>

              <ScrollReveal
                delayMs={240}
                className="rounded-2xl border border-white/10 bg-[#0b1018] p-6"
              >
                <div className="font-mono text-xs font-bold uppercase tracking-wider text-emerald-400">
                  Performance Engineered
                </div>
                <h3 className="mt-2 text-lg font-bold text-white">
                  Context Caching &amp; Adaptive Polling
                </h3>
                <p className="mt-2 text-xs leading-relaxed text-slate-300 sm:text-sm">
                  Uses single-pass series sharing, bounded context caching,
                  subscriber-isolated GET deduplication, and adaptive `15s` (open) /
                  `60s` (closed) polling backoff.
                </p>
              </ScrollReveal>

              <ScrollReveal
                delayMs={300}
                className="rounded-2xl border border-white/10 bg-[#0b1018] p-6"
              >
                <div className="font-mono text-xs font-bold uppercase tracking-wider text-amber-300">
                  Discipline First
                </div>
                <h3 className="mt-2 text-lg font-bold text-white">
                  No Guaranteed Profits or Hype
                </h3>
                <p className="mt-2 text-xs leading-relaxed text-slate-300 sm:text-sm">
                  Markets are probabilistic. When our 5 AI agents conflict, volatility
                  is compressed, or the feed is stale, AllSafe AI Trading explicitly
                  outputs `NO_TRADE` / `WAIT` rather than forcing low-quality setups.
                </p>
              </ScrollReveal>
            </div>
          </div>
        </section>

        {/* ================================================================== */}
        {/* SECTION F — SECURITY AND TRUST                                     */}
        {/* ================================================================== */}
        <section
          id="about"
          className="border-b border-white/10 bg-[#080c14] py-16 sm:py-20"
        >
          <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
            <ScrollReveal className="max-w-3xl">
              <p className="font-mono text-xs font-semibold uppercase tracking-[0.2em] text-emerald-400">
                Security, Access Control &amp; Operational Transparency
              </p>
              <h2 className="mt-2 text-2xl font-bold tracking-tight text-white sm:text-4xl">
                Defense-in-Depth Security &amp; Read-Only Safety Architecture
              </h2>
              <p className="mt-3 text-sm leading-relaxed text-slate-300 sm:text-base">
                Security boundaries are enforced on the FastAPI backend and database
                layer—never trusted to client-side code.
              </p>
            </ScrollReveal>

            <div className="mt-10 grid grid-cols-1 gap-4 md:grid-cols-2">
              <ScrollReveal className="rounded-2xl border border-white/10 bg-[#0b1018] p-6">
                <div className="flex items-center justify-between">
                  <span className="font-mono text-xs font-bold uppercase tracking-wider text-emerald-300">
                    01 &middot; Customer Authentication &amp; Role Guards
                  </span>
                  <span className="rounded border border-white/10 bg-white/5 px-2 py-0.5 font-mono text-[10px] text-slate-300">
                    /login &middot; /api/v1/auth/*
                  </span>
                </div>
                <h3 className="mt-3 text-base font-bold text-white sm:text-lg">
                  Verified Token Authentication &amp; Account Lifecycle
                </h3>
                <p className="mt-2 text-xs leading-relaxed text-slate-300 sm:text-sm">
                  The top-right <strong>Customer Sign In</strong> button connects
                  directly to the existing `/login` authentication route. Every
                  protected API request requires a valid `Bearer` token verified
                  against active account status (`active` vs. `paused`) and role
                  permissions (`user` vs. `admin`).
                </p>
              </ScrollReveal>

              <ScrollReveal
                delayMs={80}
                className="rounded-2xl border border-white/10 bg-[#0b1018] p-6"
              >
                <div className="flex items-center justify-between">
                  <span className="font-mono text-xs font-bold uppercase tracking-wider text-emerald-300">
                    02 &middot; Server-Enforced IP Allowlist Policy
                  </span>
                  <span className="rounded border border-white/10 bg-white/5 px-2 py-0.5 font-mono text-[10px] text-slate-300">
                    apps/api/app/security.py
                  </span>
                </div>
                <h3 className="mt-3 text-base font-bold text-white sm:text-lg">
                  Backend IP &amp; CIDR Verification Boundary
                </h3>
                <p className="mt-2 text-xs leading-relaxed text-slate-300 sm:text-sm">
                  IP-based access restrictions (`allowed_ip` in `public.profiles` /
                  `AuthStore`) are evaluated strictly on the backend server using
                  `ipaddress` exact and CIDR subnet matching (`verify_ip_match` /
                  `is_client_ip_allowed`). Private IP allowlists and secrets are never
                  exposed in frontend bundles.
                </p>
              </ScrollReveal>

              <ScrollReveal
                delayMs={140}
                className="rounded-2xl border border-white/10 bg-[#0b1018] p-6"
              >
                <div className="flex items-center justify-between">
                  <span className="font-mono text-xs font-bold uppercase tracking-wider text-emerald-300">
                    03 &middot; Execution Lock &amp; Secret Redaction
                  </span>
                  <span className="rounded border border-white/10 bg-white/5 px-2 py-0.5 font-mono text-[10px] text-slate-300">
                    execution_disabled = True
                  </span>
                </div>
                <h3 className="mt-3 text-base font-bold text-white sm:text-lg">
                  Zero Order Execution &amp; Automatic Credential Redaction
                </h3>
                <p className="mt-2 text-xs leading-relaxed text-slate-300 sm:text-sm">
                  Groww integration operates strictly in read-only market-data mode.
                  `Settings.__repr__` and `redact_groww_secrets()` automatically scrub
                  tokens, API keys, and TOTP secrets from all logs and exception
                  traces.
                </p>
              </ScrollReveal>

              <ScrollReveal
                delayMs={200}
                className="rounded-2xl border border-white/10 bg-[#0b1018] p-6"
              >
                <div className="flex items-center justify-between">
                  <span className="font-mono text-xs font-bold uppercase tracking-wider text-amber-300">
                    04 &middot; Honest Institutional Disclosure
                  </span>
                  <span className="rounded border border-amber-500/30 bg-amber-500/10 px-2 py-0.5 font-mono text-[10px] text-amber-300">
                    Transparent Scope
                  </span>
                </div>
                <h3 className="mt-3 text-base font-bold text-white sm:text-lg">
                  No Unsupported Regulatory or Profit Claims
                </h3>
                <p className="mt-2 text-xs leading-relaxed text-slate-300 sm:text-sm">
                  AllSafe AI Trading is an independent software engineering and
                  quantitative market-analysis platform. It does not claim SEBI
                  investment adviser registration, brokerage licensing, or guaranteed
                  financial returns.
                </p>
              </ScrollReveal>
            </div>
          </div>
        </section>

        {/* ================================================================== */}
        {/* SECTION G — FINAL CTA                                              */}
        {/* ================================================================== */}
        <section className="relative overflow-hidden py-16 sm:py-20">
          <div className="mx-auto max-w-5xl px-4 sm:px-6 lg:px-8">
            <ScrollReveal className="relative overflow-hidden rounded-3xl border border-emerald-500/30 bg-gradient-to-br from-[#0b1520] via-[#091019] to-[#120b16] p-8 text-center shadow-2xl sm:p-12">
              <p className="font-mono text-xs font-semibold uppercase tracking-[0.2em] text-emerald-300">
                Ready for Disciplined Market Analysis
              </p>
              <h2 className="mt-3 text-2xl font-extrabold tracking-tight text-white sm:text-4xl">
                Access the AllSafe AI Trading Terminal
              </h2>
              <p className="mx-auto mt-3 max-w-2xl text-sm leading-relaxed text-slate-300 sm:text-base">
                Sign in with your authorized customer or administrator credentials to
                access live 5-minute NIFTY 50 and BANK NIFTY charts, 5-Agent
                consensus telemetry, and volatility-bounded risk calculations.
              </p>

              <div className="mt-7 flex flex-col items-center justify-center gap-3.5 sm:flex-row">
                <Link
                  href="/login"
                  data-testid="final-cta-signin"
                  className="inline-flex min-h-[46px] w-full items-center justify-center gap-2 rounded-xl bg-emerald-500 px-7 py-3 text-sm font-bold text-slate-950 shadow-[0_0_25px_rgba(16,185,129,0.35)] transition hover:bg-emerald-400 focus:outline-none focus:ring-2 focus:ring-emerald-300 sm:w-auto"
                >
                  <span>Customer Sign In</span>
                  <span aria-hidden="true" className="font-mono">
                    &rarr;
                  </span>
                </Link>

                <Link
                  href="/what-we-done"
                  className="inline-flex min-h-[46px] w-full items-center justify-center rounded-xl border border-white/15 bg-white/[0.05] px-6 py-3 text-sm font-semibold text-white transition hover:bg-white/10 focus:outline-none focus:ring-2 focus:ring-emerald-400 sm:w-auto"
                >
                  Explore What We Done (5 AI Agents)
                </Link>
              </div>
            </ScrollReveal>
          </div>
        </section>
      </main>

      {/* ================================================================== */}
      {/* SECTION H — FOOTER                                                 */}
      {/* ================================================================== */}
      <footer className="border-t border-white/10 bg-[#05080d] py-12 text-xs text-slate-400">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          <div className="grid grid-cols-1 gap-8 md:grid-cols-4">
            <div className="space-y-3 md:col-span-2">
              <div className="flex items-center gap-2.5">
                <span className="inline-flex h-7 w-7 items-center justify-center rounded-lg border border-emerald-500/40 bg-emerald-500/15 font-mono text-xs font-bold text-emerald-300">
                  AS
                </span>
                <span className="text-base font-bold text-white">
                  AllSafe <span className="text-emerald-400">AI Trading</span>
                </span>
              </div>
              <p className="max-w-md leading-relaxed text-slate-400">
                Quantitative NSE index analysis platform for NIFTY 50 and BANK NIFTY.
                Powered by 5 autonomous AI market agents, multi-timeframe regime
                classification, and read-only risk management.
              </p>
              <div className="flex flex-wrap items-center gap-2 font-mono text-[11px] text-slate-400">
                <span className="rounded border border-white/10 bg-white/[0.03] px-2 py-0.5">
                  API Status: {backendOnline ? `Online (v${backendVersion})` : "Standby / Read-Only"}
                </span>
                <span className="rounded border border-white/10 bg-white/[0.03] px-2 py-0.5">
                  Session: 09:15–15:30 IST
                </span>
              </div>
            </div>

            <div className="space-y-2">
              <div className="font-mono text-[11px] font-bold uppercase tracking-wider text-slate-200">
                Navigation
              </div>
              <ul className="space-y-1.5">
                <li>
                  <a href="#home" className="hover:text-white">
                    Home &amp; Live IST Clock
                  </a>
                </li>
                <li>
                  <Link href="/what-we-done" className="text-emerald-300 hover:underline">
                    What We Done (5 AI Agents)
                  </Link>
                </li>
                <li>
                  <a href="#ai-intelligence" className="hover:text-white">
                    AI Market Intelligence
                  </a>
                </li>
                <li>
                  <a href="#dashboard-preview" className="hover:text-white">
                    Market Dashboard Preview
                  </a>
                </li>
                <li>
                  <a href="#features" className="hover:text-white">
                    Trading Features
                  </a>
                </li>
                <li>
                  <a href="#about" className="hover:text-white">
                    Security &amp; Architecture
                  </a>
                </li>
                <li>
                  <Link href="/login" className="text-emerald-300 hover:underline">
                    Customer Sign In (/login)
                  </Link>
                </li>
              </ul>
            </div>

            <div className="space-y-2">
              <div className="font-mono text-[11px] font-bold uppercase tracking-wider text-slate-200">
                Governance &amp; Disclosures
              </div>
              <ul className="space-y-1.5">
                <li>
                  <button
                    type="button"
                    onClick={() => setActiveLegalDoc("privacy")}
                    className="text-left hover:text-white focus:outline-none focus:underline"
                  >
                    Privacy Policy
                  </button>
                </li>
                <li>
                  <button
                    type="button"
                    onClick={() => setActiveLegalDoc("terms")}
                    className="text-left hover:text-white focus:outline-none focus:underline"
                  >
                    Terms and Conditions
                  </button>
                </li>
                <li>
                  <button
                    type="button"
                    onClick={() => setActiveLegalDoc("risk")}
                    className="text-left text-amber-300 hover:text-amber-200 focus:outline-none focus:underline"
                  >
                    Risk Disclosure
                  </button>
                </li>
                <li className="pt-1">
                  <a
                    href="https://github.com/sanju245/allsafe-ai-trading"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="font-mono text-[11px] text-slate-300 hover:text-emerald-300"
                  >
                    GitHub: sanju245/allsafe-ai-trading
                  </a>
                </li>
              </ul>
            </div>
          </div>

          <div className="mt-8 border-t border-white/10 pt-6 leading-relaxed text-slate-400">
            <p>
              <strong className="text-slate-200">Risk Disclosure:</strong> AllSafe AI
              Trading provides educational and rule-based quantitative market analysis
              only and does not provide personalized investment advice or broker order
              execution. Equity and index derivatives trading on NSE/BSE involves
              substantial risk of loss, and no AI model or strategy guarantees
              profits.
            </p>
            <p className="mt-3 font-mono text-[11px] text-slate-500">
              &copy; {new Date().getUTCFullYear()} AllSafe AI Trading. All rights
              reserved. Read-Only Quantitative Analysis Platform.
            </p>
          </div>
        </div>
      </footer>

      <LegalModal activeDoc={activeLegalDoc} onClose={() => setActiveLegalDoc(null)} />
    </div>
  );
}

export default memo(LandingPage);
