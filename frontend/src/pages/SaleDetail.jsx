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
  const { saleKey } = useParams();
  const { sale, stats, assetIndex, dataSource, loading, error } = useSaleData(saleKey);

  const meta = SALE_CATALOG[saleKey];

  if (loading) return <LoadingSpinner message="Loading sale catalog..." />;
  if (error) return <ErrorBanner message={error} />;

  // Asset-only mode for historical sales
  if (dataSource === "assets-only") {
    return (
      <AssetOnlySaleView
        saleKey={saleKey}
        meta={meta}
        assetIndex={assetIndex}
      />
    );
  }

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
          {meta?.company || "OBS"} &middot; {meta?.location || "Ocala, FL"}
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
        <HipTable hips={sale.hips} saleKey={saleKey} assetIndex={assetIndex} />
      </div>
    </div>
  );
}

/**
 * View for historical sales that only have S3 assets (no JSON sale data).
 * Displays a hip grid derived from the S3 asset index.
 */
function AssetOnlySaleView({ saleKey, meta, assetIndex }) {
  const hipNumbers = Object.keys(assetIndex || {})
    .map(Number)
    .sort((a, b) => a - b);

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
        <span className="text-gray-700">{meta?.name || saleKey}</span>
      </div>

      {/* Header */}
      <div>
        <h1 className="text-2xl font-semibold text-gray-900 tracking-tight">
          {meta?.name || saleKey}
        </h1>
        <p className="text-sm text-gray-500 mt-1">
          {meta?.company || "OBS"} &middot; {meta?.location || "Ocala, FL"} &middot;{" "}
          <span className="text-amber-600">Asset-only view</span>
        </p>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <StatCard label="Hips with Assets" value={formatNumber(hipNumbers.length)} accent />
        <StatCard
          label="Videos"
          value={formatNumber(
            Object.values(assetIndex || {}).filter((a) => a.video).length
          )}
        />
        <StatCard
          label="Photos"
          value={formatNumber(
            Object.values(assetIndex || {}).filter((a) => a.photo).length
          )}
        />
        <StatCard
          label="Pedigree PDFs"
          value={formatNumber(
            Object.values(assetIndex || {}).filter((a) => a.pedigree).length
          )}
        />
      </div>

      {/* Hip grid */}
      <div>
        <h2 className="text-lg font-semibold text-gray-900 mb-4">
          Browse by Hip Number
        </h2>
        {hipNumbers.length === 0 ? (
          <div className="rounded-xl border border-gray-100 bg-white p-8 text-center shadow-[0_1px_3px_rgba(0,0,0,0.04)]">
            <p className="text-gray-400">No assets found for this sale</p>
          </div>
        ) : (
          <div className="grid grid-cols-4 sm:grid-cols-6 md:grid-cols-8 lg:grid-cols-10 gap-2">
            {hipNumbers.map((hip) => {
              const assets = assetIndex[String(hip)] || {};
              return (
                <Link
                  key={hip}
                  to={`/sale/${saleKey}/hip/${hip}`}
                  className="flex flex-col items-center rounded-lg border border-gray-100 bg-white p-3 hover:border-brand-300 hover:shadow-sm transition-all group"
                >
                  <span className="text-lg font-mono font-bold text-brand-600 group-hover:text-brand-700">
                    #{hip}
                  </span>
                  <div className="flex gap-1 mt-1.5">
                    {assets.video && (
                      <span className="w-4 h-4 rounded text-[8px] font-bold flex items-center justify-center bg-emerald-50 text-emerald-600 border border-emerald-200">
                        V
                      </span>
                    )}
                    {assets.walkVideo && (
                      <span className="w-4 h-4 rounded text-[8px] font-bold flex items-center justify-center bg-sky-50 text-sky-600 border border-sky-200">
                        W
                      </span>
                    )}
                    {assets.photo && (
                      <span className="w-4 h-4 rounded text-[8px] font-bold flex items-center justify-center bg-violet-50 text-violet-600 border border-violet-200">
                        P
                      </span>
                    )}
                    {assets.pedigree && (
                      <span className="w-4 h-4 rounded text-[8px] font-bold flex items-center justify-center bg-amber-50 text-amber-600 border border-amber-200">
                        D
                      </span>
                    )}
                  </div>
                </Link>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
