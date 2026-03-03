import { SALE_CATALOG } from "../lib/api";
import { useSaleData } from "../hooks/useSaleData";
import SaleCard from "../components/SaleCard";
import { formatNumber } from "../lib/format";

// Group historic sales by year, newest first
const historicByYear = Object.entries(SALE_CATALOG)
  .filter(([, m]) => !m.isLive)
  .sort(([, a], [, b]) => b.year - a.year || a.month - b.month)
  .reduce((acc, [key, meta]) => {
    if (!acc[meta.year]) acc[meta.year] = [];
    acc[meta.year].push({ key, meta });
    return acc;
  }, {});

const years = Object.keys(historicByYear).sort((a, b) => b - a);

export default function HistoricSales() {
  return (
    <div className="space-y-8">
      {/* Page header */}
      <div>
        <h1 className="text-2xl font-semibold text-gray-900 tracking-tight">
          Historic Sales
        </h1>
        <p className="text-sm text-gray-500 mt-1">
          Browse all OBS 2YO training sales from 2018 to 2025 — including
          videos, photos, pedigree PDFs, and sale data
        </p>
      </div>

      {/* Summary */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <SummaryCard label="Years Covered" value={years.length} />
        <SummaryCard
          label="Total Sales"
          value={Object.values(historicByYear).reduce(
            (sum, arr) => sum + arr.length,
            0
          )}
        />
        <SummaryCard label="Sales with Data" value="2025" accent />
        <SummaryCard label="Asset Archive" value="2018–2025" />
      </div>

      {/* Sale cards by year */}
      {years.map((year) => (
        <div key={year}>
          <h2 className="text-lg font-semibold text-gray-900 mb-4">
            {year} Sales Season
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {historicByYear[year].map((s) =>
              s.meta.hasData ? (
                <DataSaleCard key={s.key} saleKey={s.key} meta={s.meta} />
              ) : (
                <AssetSaleCard key={s.key} saleKey={s.key} meta={s.meta} />
              )
            )}
          </div>
        </div>
      ))}
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

function AssetSaleCard({ saleKey, meta }) {
  const { assetIndex, dataSource, loading } = useSaleData(saleKey);
  const assetCount = assetIndex ? Object.keys(assetIndex).length : 0;

  return (
    <SaleCard
      saleKey={saleKey}
      meta={meta}
      stats={null}
      assetCount={assetCount}
      dataSource={dataSource}
      loading={loading}
    />
  );
}

function SummaryCard({ label, value, accent }) {
  return (
    <div className="rounded-xl border border-gray-100 bg-white p-4 shadow-[0_1px_3px_rgba(0,0,0,0.04)]">
      <p className="text-[10px] uppercase tracking-wider text-gray-400 mb-1">
        {label}
      </p>
      <p
        className={`text-lg font-semibold ${
          accent ? "text-brand-600" : "text-gray-800"
        }`}
      >
        {value}
      </p>
    </div>
  );
}
