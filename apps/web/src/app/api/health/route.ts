import { getApiHealth } from "@/lib/api";

export async function GET() {
  const health = await getApiHealth();
  const headers = { "Cache-Control": "no-store" };
  if (!health.ok) return Response.json({ ok: false }, { status: 503, headers });
  return Response.json({ timeUtc: health.timeUtc, marketCalendar: health.marketCalendar }, { headers });
}
