import LandingPage from "@/components/landing/LandingPage";
import { getApiHealth } from "@/lib/api";

// Backend status and server UTC timestamp are checked per request.
export const dynamic = "force-dynamic";

export default async function Home() {
  const health = await getApiHealth();

  return (
    <LandingPage
      serverTimeUtc={health.ok ? health.timeUtc : null}
      backendOnline={health.ok}
      backendVersion={health.ok ? health.version : "0.1.0"}
    />
  );
}
