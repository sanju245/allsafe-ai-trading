import type { Metadata } from "next";
import Link from "next/link";
import StrategyResearchReport, { type StrategyResearchData } from "@/components/StrategyResearchReport";
import researchData from "@/data/strategy-research.json";

export const metadata: Metadata = {
  title: "Strategy Research — AllSafe AI Trading",
  description: "Exploratory strategy methods, chronological historical checks, and limitations for NIFTY 50 and BANK NIFTY analysis.",
};

export default function ResearchPage() {
  return (
    <main className="mx-auto min-h-screen max-w-6xl px-4 py-8 sm:px-6">
      <nav aria-label="Research navigation" className="flex flex-wrap gap-5 text-sm text-emerald-300"><Link href="/">AllSafe home</Link><Link href="/terminal">Return to market dashboard</Link></nav>
      <header className="py-10"><p className="text-xs uppercase tracking-widest text-emerald-400">Methods and measured observations</p><h1 className="mt-3 text-3xl font-semibold sm:text-4xl">Strategy research</h1><p className="mt-4 max-w-3xl leading-7 text-slate-400">Compare the original decision rules with research candidates, see the size of each test, and understand what the available evidence can establish.</p></header>
      <StrategyResearchReport data={researchData as StrategyResearchData} />
    </main>
  );
}
