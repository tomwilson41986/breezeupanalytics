import { Link } from "react-router-dom";
import { formatCompact, formatNumber, formatPercent } from "../lib/format";

export default function SaleCard({ saleKey, meta, stats, loading }) {
  if (loading) {
    return (
      <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-5 animate-pulse-brand">
        <div className="h-5 bg-slate-800 rounded w-3/4 mb-3" />
        <div className="h-4 bg-slate-800 rounded w-1/2 mb-6" />
        <div className="grid grid-cols-3 gap-3">
          <div className="h-12 bg-slate-800 rounded" />
          <div className="h-12 bg-slate-800 rounded" />
          <div className="h-12 bg-slate-800 rounded" />
        </div>
      </div>
    );
  }

  return (
    <Link
      to={`/sale/${meta.id}`}
      className="block rounded-xl border border-slate-800 bg-slate-900/50 p-5 hover:border-brand-500/40 hover:bg-slate-900/80 transition-all group"
    >
      {/* Header */}
      <div className="flex items-start justify-between mb-1">
        <div>
          <h3 className="font-semibold text-white group-hover:text-brand-400 transition-colors">
            {meta.name}
          </h3>
          <p className="text-xs text-slate-500 mt-0.5">
            {meta.company} &middot; {meta.location}
          </p>
        </div>
        <span className="text-xs font-mono text-slate-500 bg-slate-800/60 px-2 py-0.5 rounded">
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
      <p className="text-[10px] uppercase tracking-wider text-slate-500 mb-0.5">
        {label}
      </p>
      <p
        className={`text-sm font-semibold ${
          accent ? "text-brand-400" : "text-slate-200"
        }`}
      >
        {value}
      </p>
    </div>
  );
}
