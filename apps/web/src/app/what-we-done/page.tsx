import type { Metadata } from "next";
import WhatWeDonePage from "@/components/landing/WhatWeDonePage";
import { getApiHealth } from "@/lib/api";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "What We Done — AllSafe AI Trading",
  description:
    "Discover how our five autonomous AI agents inspect the Indian stock market (NIFTY 50 and BANK NIFTY) to determine when to buy, when to sell, and when to wait.",
};

export default async function WhatWeDoneRoute() {
  const health = await getApiHealth();

  return (
    <WhatWeDonePage
      serverTimeUtc={health.ok ? health.timeUtc : null}
      backendOnline={health.ok}
      backendVersion={health.ok ? health.version : "0.1.0"}
    />
  );
}
