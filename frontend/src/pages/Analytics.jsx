import { useState } from "react";
import { SALE_CATALOG } from "../lib/api";
import { useSaleData } from "../hooks/useSaleData";
import LoadingSpinner from "../components/LoadingSpinner";
import ErrorBanner from "../components/ErrorBanner";
import StatCard from "../components/StatCard";
import PriceDistributionChart from "../components/charts/PriceDistributionChart";
import SireLeaderboard from "../components/charts/SireLeaderboard";
import BreezeScatter from "../components/charts/BreezeScatter";
import ConsignorTable from "../components/charts/ConsignorTable";
import {
  formatCompact,
  formatNumber,
  formatPercent,
  formatCurrency,
} from "../lib/format";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  Legend,
} from "recharts";

const saleEntries = Object.entries(SALE_CATALOG);

export default function Analytics() {
  const [selectedSaleId, setSelectedSaleId] = useState(
    String(saleEntries[0][1].id)
  );

  const { sale, stats, loading, error } = useSaleData(selectedSaleId);

  return (
    <div className="space-y-6">
      {/* Header + selector */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-gray-900 tracking-tight">
            Analytics
          </h1>
          <p className="text-sm text-gray-500 mt-1">
            Deep-dive analysis tools and visualizations
          </p>
        </div>
        <select
          value={selectedSaleId}
          onChange={(e) => setSelectedSaleId(e.target.value)}
          className="bg-white border border-gray-200 rounded-lg px-3 py-2 text-sm text-gray-700 focus:outline-none focus:border-brand-400 focus:ring-2 focus:ring-brand-100"
        >
          {saleEntries.map(([key, meta]) => (
            <option key={key} value={String(meta.id)}>
              {meta.name}
            </option>
          ))}
        </select>
      </div>

      {loading && <LoadingSpinner message="Crunching the numbers..." />}
      {error && <ErrorBanner message={error} />}

      {stats && sale && (
        <>
          {/* Overview metrics */}
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
            <StatCard
              label="Total Hips"
              value={formatNumber(stats.totalHips)}
            />
            <StatCard
              label="Sold"
              value={formatNumber(stats.soldCount)}
              sub={`${formatPercent(
                (stats.soldCount / stats.totalHips) * 100
              )} clearance`}
            />
            <StatCard
              label="Revenue"
              value={formatCompact(stats.totalRevenue)}
              accent
            />
            <StatCard
              label="Average"
              value={formatCompact(stats.avgPrice)}
            />
            <StatCard
              label="Median"
              value={formatCompact(stats.medianPrice)}
            />
            <StatCard
              label="Top Price"
              value={formatCurrency(stats.maxPrice)}
              accent
            />
          </div>

          {/* Row 1: Price distribution + Sale status pie */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
            <div className="lg:col-span-2">
              <PriceDistributionChart data={stats.priceDistribution} />
            </div>
            <SaleStatusPie stats={stats} />
          </div>

          {/* Row 2: Breeze scatter + Sire leaderboard */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <BreezeScatter breezeByDistance={stats.breezeByDistance} />
            <SireLeaderboard sires={stats.topSires} limit={20} />
          </div>

          {/* Row 3: Sex breakdown + Consignor table */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
            <SexBreakdown hips={sale.hips} />
            <div className="lg:col-span-2">
              <ConsignorTable consignors={stats.topConsignors} limit={25} />
            </div>
          </div>

          {/* Row 4: Top sellers */}
          <TopSellers hips={sale.hips} />
        </>
      )}
    </div>
  );
}

/* ── Sub-charts ────────────────────────────────────────────── */

function SaleStatusPie({ stats }) {
  const data = [
    { name: "Sold", value: stats.soldCount, color: "#16a34a" },
    { name: "RNA", value: stats.rnaCount, color: "#f97316" },
    { name: "Out", value: stats.outCount, color: "#ef4444" },
    {
      name: "Pending",
      value:
        stats.totalHips - stats.soldCount - stats.rnaCount - stats.outCount,
      color: "#d1d5db",
    },
  ].filter((d) => d.value > 0);

  return (
    <div className="rounded-xl border border-gray-100 bg-white p-5 shadow-[0_1px_3px_rgba(0,0,0,0.04)]">
      <h3 className="text-sm font-semibold text-gray-900 mb-4">
        Sale Status Breakdown
      </h3>
      <ResponsiveContainer width="100%" height={220}>
        <PieChart>
          <Pie
            data={data}
            cx="50%"
            cy="50%"
            innerRadius={50}
            outerRadius={80}
            paddingAngle={3}
            dataKey="value"
          >
            {data.map((entry, i) => (
              <Cell key={i} fill={entry.color} />
            ))}
          </Pie>
          <Tooltip
            contentStyle={{
              backgroundColor: "#ffffff",
              border: "1px solid #e5e7eb",
              borderRadius: 8,
              fontSize: 12,
              boxShadow: "0 4px 12px rgba(0,0,0,0.08)",
            }}
          />
          <Legend
            iconSize={8}
            wrapperStyle={{ fontSize: 11, color: "#6b7280" }}
          />
        </PieChart>
      </ResponsiveContainer>
    </div>
  );
}

function SexBreakdown({ hips }) {
  const sexMap = {};
  for (const h of hips) {
    const label =
      h.sex === "C"
        ? "Colts"
        : h.sex === "F"
          ? "Fillies"
          : h.sex === "G"
            ? "Geldings"
            : "Other";
    if (!sexMap[label]) sexMap[label] = { count: 0, totalPrice: 0, sold: 0 };
    sexMap[label].count++;
    if (h.price) {
      sexMap[label].totalPrice += h.price;
      sexMap[label].sold++;
    }
  }

  const data = Object.entries(sexMap)
    .map(([name, d]) => ({
      name,
      count: d.count,
      avgPrice: d.sold > 0 ? d.totalPrice / d.sold : 0,
    }))
    .sort((a, b) => b.count - a.count);

  const colors = ["#3b82f6", "#8b5cf6", "#16a34a", "#f97316"];

  return (
    <div className="rounded-xl border border-gray-100 bg-white p-5 shadow-[0_1px_3px_rgba(0,0,0,0.04)]">
      <h3 className="text-sm font-semibold text-gray-900 mb-4">
        By Sex
      </h3>
      <ResponsiveContainer width="100%" height={220}>
        <BarChart data={data} margin={{ top: 5, right: 10, left: 10, bottom: 5 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#f3f4f6" />
          <XAxis
            dataKey="name"
            tick={{ fill: "#6b7280", fontSize: 11 }}
            axisLine={{ stroke: "#e5e7eb" }}
            tickLine={false}
          />
          <YAxis
            tick={{ fill: "#6b7280", fontSize: 11 }}
            axisLine={{ stroke: "#e5e7eb" }}
            tickLine={false}
          />
          <Tooltip
            contentStyle={{
              backgroundColor: "#ffffff",
              border: "1px solid #e5e7eb",
              borderRadius: 8,
              fontSize: 12,
              boxShadow: "0 4px 12px rgba(0,0,0,0.08)",
            }}
          />
          <Bar dataKey="count" name="Count" radius={[4, 4, 0, 0]}>
            {data.map((_, i) => (
              <Cell key={i} fill={colors[i % colors.length]} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

function TopSellers({ hips }) {
  const sold = hips
    .filter((h) => h.status === "sold" && h.price)
    .sort((a, b) => b.price - a.price)
    .slice(0, 10);

  if (sold.length === 0) return null;

  return (
    <div className="rounded-xl border border-gray-100 bg-white p-5 shadow-[0_1px_3px_rgba(0,0,0,0.04)]">
      <h3 className="text-sm font-semibold text-gray-900 mb-4">
        Top 10 Highest Prices
      </h3>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-100">
              <th className="text-left py-2 px-3 text-[11px] font-medium uppercase tracking-wider text-gray-400">
                Rank
              </th>
              <th className="text-left py-2 px-3 text-[11px] font-medium uppercase tracking-wider text-gray-400">
                Hip
              </th>
              <th className="text-left py-2 px-3 text-[11px] font-medium uppercase tracking-wider text-gray-400">
                Sire
              </th>
              <th className="text-left py-2 px-3 text-[11px] font-medium uppercase tracking-wider text-gray-400">
                Dam
              </th>
              <th className="text-left py-2 px-3 text-[11px] font-medium uppercase tracking-wider text-gray-400">
                Consignor
              </th>
              <th className="text-left py-2 px-3 text-[11px] font-medium uppercase tracking-wider text-gray-400">
                Buyer
              </th>
              <th className="text-right py-2 px-3 text-[11px] font-medium uppercase tracking-wider text-gray-400">
                Price
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-50">
            {sold.map((h, i) => (
              <tr key={h.hipNumber} className="table-row-hover">
                <td className="py-2 px-3 font-mono text-gray-400">
                  {i + 1}
                </td>
                <td className="py-2 px-3 font-mono font-semibold text-brand-600">
                  #{h.hipNumber}
                </td>
                <td className="py-2 px-3 text-gray-700">{h.sire}</td>
                <td className="py-2 px-3 text-gray-500">{h.dam}</td>
                <td className="py-2 px-3 text-gray-500 text-xs max-w-[180px] truncate">
                  {h.consignor}
                </td>
                <td className="py-2 px-3 text-gray-600 text-xs max-w-[180px] truncate">
                  {h.buyer || "—"}
                </td>
                <td className="py-2 px-3 text-right font-mono font-bold text-gray-900">
                  {formatCurrency(h.price)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
