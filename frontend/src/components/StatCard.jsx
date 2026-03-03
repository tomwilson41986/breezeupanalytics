export default function StatCard({ label, value, sub, accent = false }) {
  return (
    <div className="bg-white rounded-xl border border-gray-100 p-5 shadow-[0_1px_3px_rgba(0,0,0,0.04)]">
      <p className="text-[11px] font-medium uppercase tracking-wider text-gray-400 mb-1.5">
        {label}
      </p>
      <p
        className={`text-2xl font-semibold tracking-tight ${
          accent ? "text-brand-600" : "text-gray-900"
        }`}
      >
        {value}
      </p>
      {sub && <p className="text-[12px] text-gray-400 mt-1">{sub}</p>}
    </div>
  );
}
