import { SALE_CATALOG } from "../lib/api";
import { useSaleData } from "../hooks/useSaleData";
import SaleCard from "../components/SaleCard";

const liveSales = Object.entries(SALE_CATALOG)
  .filter(([, m]) => m.isLive && m.month === 3)
  .sort(([, a], [, b]) => a.month - b.month);

export default function LiveSales() {
  return (
    <div className="space-y-8">
      {/* Page header */}
      <div>
        <div className="flex items-center gap-3 mb-1">
          <h1 className="text-2xl font-semibold text-gray-900 tracking-tight">
            Live Sales
          </h1>
          <span className="relative flex h-2.5 w-2.5">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
            <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-emerald-500" />
          </span>
        </div>
        <p className="text-sm text-gray-500 mt-1">
          2026 OBS 2YO training sales — live data with BreezeVision ratings
        </p>
      </div>

      {/* Ratings notice */}
      <div className="rounded-xl border border-brand-100 bg-brand-50/50 p-4">
        <div className="flex items-start gap-3">
          <div className="w-8 h-8 rounded-lg bg-brand-100 flex items-center justify-center shrink-0 mt-0.5">
            <svg
              className="w-4 h-4 text-brand-600"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" />
            </svg>
          </div>
          <div>
            <p className="text-sm font-medium text-brand-900">
              BreezeVision Ratings
            </p>
            <p className="text-xs text-brand-700 mt-0.5">
              Live sales include our proprietary ratings based on under-tack
              performance analysis, pedigree evaluation, and conformation
              assessment.
            </p>
          </div>
        </div>
      </div>

      {/* Sale cards */}
      <div>
        <h2 className="text-lg font-semibold text-gray-900 mb-4">
          2026 Sales Season
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {liveSales.map(([key, meta]) => (
            <DataSaleCard key={key} saleKey={key} meta={meta} />
          ))}
        </div>
      </div>
    </div>
  );
}

function DataSaleCard({ saleKey, meta }) {
  const { stats, assetIndex, dataSource, loading } = useSaleData(saleKey);
  const assetCount = assetIndex ? Object.keys(assetIndex).length : 0;

  return (
    <SaleCard
      saleKey={saleKey}
      meta={meta}
      stats={stats}
      assetCount={assetCount}
      dataSource={dataSource}
      loading={loading}
    />
  );
}
