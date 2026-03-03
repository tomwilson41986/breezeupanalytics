import { SALE_CATALOG } from "../lib/api";
import { useSaleData } from "../hooks/useSaleData";
import SaleCard from "../components/SaleCard";
import { formatCompact, formatNumber, formatPercent } from "../lib/format";

// Group sales by year, sorted descending
const salesByYear = Object.entries(SALE_CATALOG)
  .sort(([, a], [, b]) => b.year - a.year || b.month - a.month)
  .reduce((acc, [key, meta]) => {
    if (!acc[meta.year]) acc[meta.year] = [];
    acc[meta.year].push({ key, meta });
    return acc;
  }, {});

const years = Object.keys(salesByYear).sort((a, b) => b - a);

export default function Dashboard() {
  return (
    <div className="space-y-8">
      {/* Page header */}
      <div>
        <h1 className="text-2xl font-semibold text-gray-900 tracking-tight">
          Dashboard
        </h1>
        <p className="text-sm text-gray-500 mt-1">
          Breeze-up sale analytics across all OBS 2YO training sales (2018–2025)
        </p>
      </div>

      {/* Sale cards by year */}
      {years.map((year) => (
        <div key={year}>
          <h2 className="text-lg font-semibold text-gray-900 mb-4">
            {year} Sales Season
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {salesByYear[year].map((s) =>
              s.meta.hasData ? (
                <DataSaleCard key={s.key} saleKey={s.key} meta={s.meta} />
              ) : (
                <SaleCard
                  key={s.key}
                  saleKey={s.key}
                  meta={s.meta}
                  stats={null}
                  assetCount={0}
                  dataSource="assets-only"
                  loading={false}
                />
              )
            )}
          </div>
        </div>
      ))}
    </div>
  );
}

/**
 * Only loads data for sales that have pre-processed JSON (2025).
 */
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
