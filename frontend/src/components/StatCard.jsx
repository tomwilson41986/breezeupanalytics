export default function StatCard({ label, value, sub, accent = false }) {
  return (
    <div
      className={`rounded-xl border p-4 ${
        accent
          ? "border-brand-500/30 bg-brand-950/40 stat-glow"
          : "border-slate-800 bg-slate-900/50"
      }`}
    >
      <p className="text-xs font-medium uppercase tracking-wider text-slate-400 mb-1">
        {label}
      </p>
      <p
        className={`text-2xl font-bold tracking-tight ${
          accent ? "text-brand-400" : "text-white"
        }`}
      >
        {value}
      </p>
      {sub && <p className="text-xs text-slate-500 mt-0.5">{sub}</p>}
    </div>
  );
}
