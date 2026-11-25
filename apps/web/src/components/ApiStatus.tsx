import { getApiHealth } from "@/lib/api";

// Async Server Component: checks the backend /health endpoint on each request.
export default async function ApiStatus() {
  const health = await getApiHealth();

  if (!health.ok) {
    return (
      <p className="as-pill as-pill--amber">Account service unavailable</p>
    );
  }

  return (
    <p className="as-pill as-pill--green"><span className="as-led" aria-hidden="true" /> Account service online</p>
  );
}
