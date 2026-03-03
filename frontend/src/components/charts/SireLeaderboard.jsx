import { formatCompact, formatNumber } from "../../lib/format";

export default function SireLeaderboard({ sires, limit = 15 }) {
  if (!sires || sires.length === 0) return null;

  const top = sires.slice(0, limit);
  const maxAvg = Math.max(...top.map((s) => s.avgPrice));

  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-5">
      <h3 className="text-sm font-semibold text-white mb-4">
        Sire Leaderboard{" "}
        <span className="text-slate-500 font-normal">(by Avg Price)</span>
      </h3>
      <div className="space-y-2">
        {top.map((sire, i) => (
          <div key={sire.name} className="group">
            <div className="flex items-center justify-between text-xs mb-1">
              <span className="flex items-center gap-2">
                <span className="w-5 text-right font-mono text-slate-500">
                  {i + 1}
                </span>
                <span className="font-medium text-slate-200 group-hover:text-brand-400 transition-colors">
                  {sire.name}
                </span>
              </span>
              <span className="flex items-center gap-3 text-slate-400">
                <span>{formatNumber(sire.count)} sold</span>
                <span className="font-semibold text-brand-400 font-mono">
                  {formatCompact(sire.avgPrice)}
                </span>
              </span>
            </div>
            <div className="ml-7 h-1.5 rounded-full bg-slate-800 overflow-hidden">
              <div
                className="h-full rounded-full bg-gradient-to-r from-brand-600 to-brand-400 transition-all"
                style={{ width: `${(sire.avgPrice / maxAvg) * 100}%` }}
              />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
