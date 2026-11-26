import type { Metadata } from "next";
import WhatWeDonePage from "@/components/landing/WhatWeDonePage";

export const metadata: Metadata = {
  title: "How It Works — AllSafe AI Trading",
  description:
    "See how the deterministic five-check signal engine evaluates confirmed NIFTY 50 and BANK NIFTY candles for read-only market analysis.",
};

export default function WhatWeDoneRoute() {
  return <WhatWeDonePage />;
}
