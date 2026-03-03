import { formatCompact, formatNumber } from "../../lib/format";

export default function ConsignorTable({ consignors, limit = 20 }) {
  if (!consignors || consignors.length === 0) return null;

  const top = consignors.slice(0, limit);

  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-5">
      <h3 className="text-sm font-semibold text-white mb-4">
        Top Consignors{" "}
        <span className="text-slate-500 font-normal">(by Revenue)</span>
      </h3>
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-slate-800">
              <th className="text-left py-2 px-2 text-slate-400 font-semibold uppercase tracking-wider">
                #
              </th>
              <th className="text-left py-2 px-2 text-slate-400 font-semibold uppercase tracking-wider">
                Consignor
              </th>
              <th className="text-right py-2 px-2 text-slate-400 font-semibold uppercase tracking-wider">
                Sold
              </th>
              <th className="text-right py-2 px-2 text-slate-400 font-semibold uppercase tracking-wider">
                Avg Price
              </th>
              <th className="text-right py-2 px-2 text-slate-400 font-semibold uppercase tracking-wider">
                Revenue
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800/50">
            {top.map((c, i) => (
              <tr key={c.name} className="table-row-hover">
                <td className="py-2 px-2 text-slate-500 font-mono">
                  {i + 1}
                </td>
                <td className="py-2 px-2 text-slate-200 font-medium">
                  {c.name}
                </td>
                <td className="py-2 px-2 text-right text-slate-400 font-mono">
                  {formatNumber(c.count)}
                </td>
                <td className="py-2 px-2 text-right text-slate-300 font-mono">
                  {formatCompact(c.avgPrice)}
                </td>
                <td className="py-2 px-2 text-right text-brand-400 font-mono font-semibold">
                  {formatCompact(c.totalRevenue)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
