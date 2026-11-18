import { notFound } from "next/navigation";
import DashboardAccessGate from "@/components/auth/DashboardAccessGate";
import IndexChartPage from "@/components/IndexChartPage";
import { chartDestination } from "@/lib/customerNavigation";

export const dynamic = "force-dynamic";

export default async function ChartPage({
  params,
  searchParams,
}: {
  params: Promise<{ symbol: string }>;
  searchParams: Promise<{ provider?: string | string[]; days?: string | string[] }>;
}) {
  const [route, query] = await Promise.all([params, searchParams]);
  const symbol = route.symbol.toUpperCase();
  if (symbol !== "NIFTY50" && symbol !== "BANKNIFTY") notFound();

  const returnPath = chartDestination(
    `/chart/${symbol}`,
    typeof query.provider === "string" ? query.provider : undefined,
    typeof query.days === "string" ? query.days : undefined,
  );

  return (
    <DashboardAccessGate signInDestination={returnPath}>
      <IndexChartPage symbol={symbol} />
    </DashboardAccessGate>
  );
}
