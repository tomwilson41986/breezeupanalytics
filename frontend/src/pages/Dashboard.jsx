import { SALE_CATALOG } from "../lib/api";
import { useSaleData } from "../hooks/useSaleData";
import SaleCard from "../components/SaleCard";
import StatCard from "../components/StatCard";
import { formatCompact, formatNumber, formatPercent } from "../lib/format";

export default function Dashboard() {
  const sales = Object.entries(SALE_CATALOG).map(([key, meta]) => ({
    key,
    meta,
    ...useSaleData(meta.id),
  }));

  // Aggregate stats across all loaded sales
  const allStats = sales.filter((s) => s.stats);
  const totalHips = allStats.reduce((s, x) => s + x.stats.totalHips, 0);
  const totalSold = allStats.reduce((s, x) => s + x.stats.soldCount, 0);
  const totalRevenue = allStats.reduce((s, x) => s + x.stats.totalRevenue, 0);
  const avgBuyback =
    allStats.length > 0
      ? allStats.reduce((s, x) => s + x.stats.buybackRate, 0) /
        allStats.length
      : 0;

  return (
    <div className="space-y-8">
      {/* Page header */}
      <div>
        <h1 className="text-2xl font-bold text-white tracking-tight">
          Dashboard
        </h1>
        <p className="text-sm text-slate-400 mt-1">
          Breeze-up sale analytics across all OBS 2YO training sales
        </p>
      </div>

      {/* Aggregate metrics */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <StatCard
          label="Total Cataloged"
          value={formatNumber(totalHips)}
          sub={`across ${allStats.length} sales`}
        />
        <StatCard
          label="Total Sold"
          value={formatNumber(totalSold)}
          sub={`${formatPercent(
            totalHips ? (totalSold / totalHips) * 100 : 0
          )} clearance`}
        />
        <StatCard
          label="Combined Revenue"
          value={formatCompact(totalRevenue)}
          accent
        />
        <StatCard
          label="Avg Buyback Rate"
          value={formatPercent(avgBuyback)}
          sub="RNA / (Sold + RNA)"
        />
      </div>

      {/* Sale cards */}
      <div>
        <h2 className="text-lg font-semibold text-white mb-4">
          2025 Sales Season
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {sales.map((s) => (
            <SaleCard
              key={s.key}
              saleKey={s.key}
              meta={s.meta}
              stats={s.stats}
              loading={s.loading}
            />
          ))}
        </div>
      </div>
    </div>
  );
}
