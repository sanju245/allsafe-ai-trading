import type { Metadata } from "next";
import WhatWeDonePage from "@/components/landing/WhatWeDonePage";
import { getApiHealth } from "@/lib/api";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "How It Works — AllSafe AI Trading",
  description:
    "See how the deterministic five-check signal engine evaluates confirmed NIFTY 50 and BANK NIFTY candles for read-only market analysis.",
};

export default async function WhatWeDoneRoute() {
  const health = await getApiHealth();

  return (
    <WhatWeDonePage
      serverTimeUtc={health.ok ? health.timeUtc : null}
      backendOnline={health.ok}
      marketCalendar={health.ok ? health.marketCalendar : undefined}
      backendVersion={health.ok ? health.version : "0.1.0"}
    />
  );
}
