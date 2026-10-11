import { getApiHealth } from "@/lib/api";

// Async Server Component: checks the backend /health endpoint on each request.
export default async function ApiStatus() {
  const health = await getApiHealth();

  if (!health.ok) {
    return (
      <div className="flex items-center gap-2 text-sm text-amber-300">
        <span className="h-2 w-2 rounded-full bg-amber-400" aria-hidden />
        <span>Backend offline: {health.reason}</span>
      </div>
    );
  }

  return (
    <div className="flex items-center gap-2 text-sm text-emerald-300">
      <span className="h-2 w-2 rounded-full bg-emerald-400" aria-hidden />
      <span>
        Backend online &middot; v{health.version} &middot; {health.environment}
      </span>
    </div>
  );
}
