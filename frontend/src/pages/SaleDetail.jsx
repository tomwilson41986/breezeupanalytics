import { useParams, Link } from "react-router-dom";
import { useSaleData } from "../hooks/useSaleData";
import { SALE_CATALOG } from "../lib/api";
import StatCard from "../components/StatCard";
import HipTable from "../components/HipTable";
import LoadingSpinner from "../components/LoadingSpinner";
import ErrorBanner from "../components/ErrorBanner";
import PriceDistributionChart from "../components/charts/PriceDistributionChart";
import SireLeaderboard from "../components/charts/SireLeaderboard";
import {
  formatCompact,
  formatNumber,
  formatPercent,
  formatCurrency,
} from "../lib/format";

export default function SaleDetail() {
  const { saleId } = useParams();
  const { sale, stats, assetIndex, loading, error } = useSaleData(saleId);

  const meta = Object.values(SALE_CATALOG).find(
    (m) => String(m.id) === String(saleId)
  );

  if (loading) return <LoadingSpinner message="Loading sale catalog..." />;
  if (error) return <ErrorBanner message={error} />;
  if (!sale) return <ErrorBanner message="Sale not found" />;

  return (
    <div className="space-y-6">
      {/* Breadcrumb */}
      <div className="flex items-center gap-2 text-sm">
        <Link
          to="/"
          className="text-gray-400 hover:text-brand-600 transition-colors"
        >
          Dashboard
        </Link>
        <span className="text-gray-300">/</span>
        <span className="text-gray-700">{sale.saleName}</span>
      </div>

      {/* Header */}
      <div>
        <h1 className="text-2xl font-semibold text-gray-900 tracking-tight">
          {sale.saleName}
        </h1>
        <p className="text-sm text-gray-500 mt-1">
          {meta?.company || "OBS"} &middot; {meta?.location || "Ocala, FL"}{" "}
          &middot; Sale ID {saleId}
        </p>
      </div>

      {/* Key metrics */}
      <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-6 gap-3">
        <StatCard
          label="Cataloged"
          value={formatNumber(stats.totalHips)}
        />
        <StatCard
          label="Sold"
          value={formatNumber(stats.soldCount)}
          sub={`${formatPercent(
            (stats.soldCount / stats.totalHips) * 100
          )} of catalog`}
        />
        <StatCard
          label="RNA"
          value={formatNumber(stats.rnaCount)}
          sub={`${formatPercent(stats.buybackRate)} buyback`}
        />
        <StatCard
          label="Average"
          value={formatCompact(stats.avgPrice)}
          accent
        />
        <StatCard label="Median" value={formatCompact(stats.medianPrice)} />
        <StatCard
          label="Top Price"
          value={formatCurrency(stats.maxPrice)}
          accent
        />
      </div>

      {/* Quick charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <PriceDistributionChart data={stats.priceDistribution} />
        <SireLeaderboard sires={stats.topSires} limit={10} />
      </div>

      {/* Hip table */}
      <div>
        <h2 className="text-lg font-semibold text-gray-900 mb-4">
          Full Catalog
        </h2>
        <HipTable hips={sale.hips} saleId={saleId} assetIndex={assetIndex} />
      </div>
    </div>
  );
}
