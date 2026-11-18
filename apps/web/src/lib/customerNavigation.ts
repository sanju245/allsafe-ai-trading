const CUSTOMER_DESTINATIONS = new Set(["/account", "/terminal"]);
const CHART_DESTINATIONS = new Set(["/chart/NIFTY50", "/chart/BANKNIFTY"]);

export function chartDestination(path: string, provider?: string | null, days?: string | null): string {
  if (!CHART_DESTINATIONS.has(path)) return "/terminal";
  if (provider !== "groww" && provider !== "upstox") return path;

  const search = new URLSearchParams({ provider });
  if (provider === "upstox" && days && /^(?:[1-9]|[12]\d|30)$/.test(days)) {
    search.set("days", days);
  }
  return `${path}?${search}`;
}

/** Build a return URL from allowed routes and chart settings. */
export function customerDestination(search: string): string {
  const requested = new URLSearchParams(search).get("next");
  if (!requested) return "/terminal";
  if (CUSTOMER_DESTINATIONS.has(requested)) return requested;

  const [path, query = ""] = requested.split("?", 2);
  const chartSearch = new URLSearchParams(query);
  return chartDestination(path, chartSearch.get("provider"), chartSearch.get("days"));
}
