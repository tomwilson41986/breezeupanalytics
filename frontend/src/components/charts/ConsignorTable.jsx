import { Link } from "react-router-dom";
import { formatCompact, formatNumber } from "../../lib/format";

export default function ConsignorTable({ consignors, limit = 20 }) {
  if (!consignors || consignors.length === 0) return null;

  const top = consignors.slice(0, limit);

  return (
    <div className="rounded-xl border border-gray-100 bg-white p-5 shadow-[0_1px_3px_rgba(0,0,0,0.04)]">
      <h3 className="text-sm font-semibold text-gray-900 mb-4">
        Top Consignors{" "}
        <span className="text-gray-400 font-normal">(by Revenue)</span>
      </h3>
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-gray-100">
              <th className="text-left py-2 px-2 text-[11px] font-medium uppercase tracking-wider text-gray-400">
                #
              </th>
              <th className="text-left py-2 px-2 text-[11px] font-medium uppercase tracking-wider text-gray-400">
                Consignor
              </th>
              <th className="text-right py-2 px-2 text-[11px] font-medium uppercase tracking-wider text-gray-400">
                Sold
              </th>
              <th className="text-right py-2 px-2 text-[11px] font-medium uppercase tracking-wider text-gray-400">
                Avg Price
              </th>
              <th className="text-right py-2 px-2 text-[11px] font-medium uppercase tracking-wider text-gray-400">
                Revenue
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-50">
            {top.map((c, i) => (
              <tr key={c.name} className="table-row-hover">
                <td className="py-2 px-2 text-gray-400 font-mono">
                  {i + 1}
                </td>
                <td className="py-2 px-2 text-gray-700 font-medium">
                  <Link to={`/vendor/${encodeURIComponent(c.name)}`} className="text-brand-600 hover:text-brand-800 hover:underline">
                    {c.name}
                  </Link>
                </td>
                <td className="py-2 px-2 text-right text-gray-500 font-mono">
                  {formatNumber(c.count)}
                </td>
                <td className="py-2 px-2 text-right text-gray-600 font-mono">
                  {formatCompact(c.avgPrice)}
                </td>
                <td className="py-2 px-2 text-right text-brand-600 font-mono font-semibold">
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
