const CUSTOMER_DESTINATIONS = new Set(["/account", "/terminal"]);

/** Accept only the two customer routes; never pass an arbitrary URL to the router. */
export function customerDestination(search: string): string {
  const requested = new URLSearchParams(search).get("next");
  return requested && CUSTOMER_DESTINATIONS.has(requested) ? requested : "/terminal";
}
