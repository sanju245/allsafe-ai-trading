import DashboardAccessGate from "@/components/auth/DashboardAccessGate";
import IndexChartPage from "@/components/IndexChartPage";

export const dynamic = "force-dynamic";

export default async function ChartPage({
  params,
}: {
  params: Promise<{ symbol: string }>;
}) {
  const { symbol } = await params;

  return (
    <DashboardAccessGate>
      <IndexChartPage symbol={symbol} />
    </DashboardAccessGate>
  );
}
