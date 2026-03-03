import { Link } from "react-router-dom";
import { formatCompact, formatNumber, formatPercent } from "../lib/format";

export default function SaleCard({ saleKey, meta, stats, loading }) {
  if (loading) {
    return (
      <div className="rounded-xl border border-gray-100 bg-white p-5 shadow-[0_1px_3px_rgba(0,0,0,0.04)] animate-pulse-brand">
        <div className="h-5 bg-gray-100 rounded w-3/4 mb-3" />
        <div className="h-4 bg-gray-100 rounded w-1/2 mb-6" />
        <div className="grid grid-cols-3 gap-3">
          <div className="h-12 bg-gray-100 rounded" />
          <div className="h-12 bg-gray-100 rounded" />
          <div className="h-12 bg-gray-100 rounded" />
        </div>
      </div>
    );
  }

  return (
    <Link
      to={`/sale/${meta.id}`}
      className="block rounded-xl border border-gray-100 bg-white p-5 shadow-[0_1px_3px_rgba(0,0,0,0.04)] hover:shadow-[0_4px_12px_rgba(0,0,0,0.08)] hover:border-gray-200 transition-all group"
    >
      {/* Header */}
      <div className="flex items-start justify-between mb-1">
        <div>
          <h3 className="font-semibold text-gray-900 group-hover:text-brand-600 transition-colors">
            {meta.name}
          </h3>
          <p className="text-xs text-gray-400 mt-0.5">
            {meta.company} &middot; {meta.location}
          </p>
        </div>
        <span className="text-[11px] font-mono text-gray-400 bg-gray-50 px-2 py-0.5 rounded">
          ID {meta.id}
        </span>
      </div>

      {/* Stats grid */}
      {stats && (
        <div className="grid grid-cols-3 gap-3 mt-4">
          <MiniStat label="Hips" value={formatNumber(stats.totalHips)} />
          <MiniStat label="Sold" value={formatNumber(stats.soldCount)} />
          <MiniStat
            label="Revenue"
            value={formatCompact(stats.totalRevenue)}
            accent
          />
          <MiniStat label="Avg Price" value={formatCompact(stats.avgPrice)} />
          <MiniStat
            label="Median"
            value={formatCompact(stats.medianPrice)}
          />
          <MiniStat
            label="Buyback"
            value={formatPercent(stats.buybackRate)}
          />
        </div>
      )}
    </Link>
  );
}

function MiniStat({ label, value, accent }) {
  return (
    <div>
      <p className="text-[10px] uppercase tracking-wider text-gray-400 mb-0.5">
        {label}
      </p>
      <p
        className={`text-sm font-semibold ${
          accent ? "text-brand-600" : "text-gray-800"
        }`}
      >
        {value}
      </p>
    </div>
  );
}
