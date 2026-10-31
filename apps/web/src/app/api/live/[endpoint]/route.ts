const allowedEndpoints = new Set(["status", "quote", "candles", "forming-candle"]);
const allowedSymbols = new Set(["NIFTY50", "BANKNIFTY"]);

type RouteContext = {
  params: Promise<{ endpoint: string }>;
};

function jsonError(message: string, status: number): Response {
  return Response.json({ error: message }, {
    status,
    headers: { "Cache-Control": "no-store" },
  });
}

export async function GET(request: Request, context: RouteContext): Promise<Response> {
  const { endpoint } = await context.params;
  if (!allowedEndpoints.has(endpoint)) {
    return jsonError("Unsupported live market-data endpoint.", 404);
  }

  const incoming = new URL(request.url);
  const symbol = incoming.searchParams.get("symbol");
  if (endpoint !== "status" && (!symbol || !allowedSymbols.has(symbol))) {
    return jsonError("Choose NIFTY50 or BANKNIFTY.", 400);
  }

  const base = process.env.API_BASE_URL?.replace(/\/+$/, "");
  if (!base) {
    return jsonError("The market-data API is not configured.", 503);
  }

  const upstream = new URL(`${base}/api/v1/live/${endpoint}`);
  if (symbol) upstream.searchParams.set("symbol", symbol);
  if (endpoint === "candles") {
    upstream.searchParams.set("timeframe", "5m");
    upstream.searchParams.set("limit", "100");
  }

  try {
    const response = await fetch(upstream, {
      cache: "no-store",
      signal: AbortSignal.timeout(8000),
    });
    return new Response(response.body, {
      status: response.status,
      headers: {
        "Content-Type": response.headers.get("Content-Type") ?? "application/json",
        "Cache-Control": "no-store",
      },
    });
  } catch {
    return jsonError("The market-data API could not be reached.", 502);
  }
}
