import { useHistoricSalesSummary } from "../hooks/useHistoricData";
import LoadingSpinner from "../components/LoadingSpinner";
import ErrorBanner from "../components/ErrorBanner";
import StatCard from "../components/StatCard";
import { formatNumber, formatPercent } from "../lib/format";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  RadarChart,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  Radar,
  Legend,
} from "recharts";

const SHORT_NAMES = {
  "OBS March Sale": "March",
  "OBS Spring Sale": "Spring",
  "OBS June Sale": "June",
  "Fasig Tipton Midlantic Sale": "FT Midlantic",
};

function shortSale(name) {
  return SHORT_NAMES[name] || name;
}

export default function SalesAnalysis() {
  const { sales, loading, error } = useHistoricSalesSummary();

  const totals = sales.reduce(
    (acc, s) => ({
      runners: acc.runners + s.runners,
      winners: acc.winners + s.winners,
      stakesWinners: acc.stakesWinners + s.stakesWinners,
      gradedStakesWinners: acc.gradedStakesWinners + s.gradedStakesWinners,
      g1Winners: acc.g1Winners + s.g1Winners,
    }),
    { runners: 0, winners: 0, stakesWinners: 0, gradedStakesWinners: 0, g1Winners: 0 }
  );

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-gray-900 tracking-tight">
          Sales Analysis
        </h1>
        <p className="text-sm text-gray-500 mt-1">
          Historic performance across all 2YO breeze-up sales
        </p>
      </div>

      {loading && <LoadingSpinner message="Loading sales data..." />}
      {error && <ErrorBanner message={String(error)} />}

      {sales.length > 0 && (
        <>
          {/* Totals */}
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
            <StatCard label="Total Runners" value={formatNumber(totals.runners)} />
            <StatCard
              label="Winners"
              value={formatNumber(totals.winners)}
              sub={formatPercent((totals.winners / totals.runners) * 100)}
            />
            <StatCard
              label="Stakes Winners"
              value={formatNumber(totals.stakesWinners)}
              sub={formatPercent((totals.stakesWinners / totals.runners) * 100)}
              accent
            />
            <StatCard
              label="Graded SW"
              value={formatNumber(totals.gradedStakesWinners)}
              sub={formatPercent((totals.gradedStakesWinners / totals.runners) * 100)}
            />
            <StatCard
              label="G1 Winners"
              value={formatNumber(totals.g1Winners)}
              sub={formatPercent((totals.g1Winners / totals.runners) * 100)}
              accent
            />
          </div>

          {/* Comparison charts */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <WinnersBysale sales={sales} />
            <RateComparison sales={sales} />
          </div>

          {/* Radar chart */}
          <SaleRadar sales={sales} />

          {/* Full table */}
          <SaleTable sales={sales} />
        </>
      )}
    </div>
  );
}

/* ── Charts ────────────────────────────────────────────────── */

function WinnersBysale({ sales }) {
  const data = sales.map((s) => ({
    sale: shortSale(s.sale),
    Runners: s.runners,
    Winners: s.winners,
    "Stakes Winners": s.stakesWinners,
  }));

  return (
    <div className="rounded-xl border border-gray-100 bg-white p-5 shadow-[0_1px_3px_rgba(0,0,0,0.04)]">
      <h3 className="text-sm font-semibold text-gray-900 mb-4">
        Runners &amp; Winners by Sale
      </h3>
      <ResponsiveContainer width="100%" height={280}>
        <BarChart data={data} margin={{ top: 5, right: 10, left: 10, bottom: 5 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#f3f4f6" />
          <XAxis
            dataKey="sale"
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
          <Legend iconSize={8} wrapperStyle={{ fontSize: 11, color: "#6b7280" }} />
          <Bar dataKey="Runners" fill="#93c5fd" radius={[4, 4, 0, 0]} />
          <Bar dataKey="Winners" fill="#3b82f6" radius={[4, 4, 0, 0]} />
          <Bar dataKey="Stakes Winners" fill="#1d4ed8" radius={[4, 4, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

function RateComparison({ sales }) {
  const data = sales.map((s) => ({
    sale: shortSale(s.sale),
    "Win %": s.winPct,
    "Stakes Win %": s.stakesWinPct,
    "GSW %": s.gradedStakesPct,
    "G1 %": s.g1Pct,
  }));

  return (
    <div className="rounded-xl border border-gray-100 bg-white p-5 shadow-[0_1px_3px_rgba(0,0,0,0.04)]">
      <h3 className="text-sm font-semibold text-gray-900 mb-4">
        Win Rates by Sale (%)
      </h3>
      <ResponsiveContainer width="100%" height={280}>
        <BarChart data={data} margin={{ top: 5, right: 10, left: 10, bottom: 5 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#f3f4f6" />
          <XAxis
            dataKey="sale"
            tick={{ fill: "#6b7280", fontSize: 11 }}
            axisLine={{ stroke: "#e5e7eb" }}
            tickLine={false}
          />
          <YAxis
            tick={{ fill: "#6b7280", fontSize: 11 }}
            axisLine={{ stroke: "#e5e7eb" }}
            tickLine={false}
            unit="%"
          />
          <Tooltip
            contentStyle={{
              backgroundColor: "#ffffff",
              border: "1px solid #e5e7eb",
              borderRadius: 8,
              fontSize: 12,
              boxShadow: "0 4px 12px rgba(0,0,0,0.08)",
            }}
            formatter={(val) => `${val.toFixed(1)}%`}
          />
          <Legend iconSize={8} wrapperStyle={{ fontSize: 11, color: "#6b7280" }} />
          <Bar dataKey="Win %" fill="#16a34a" radius={[4, 4, 0, 0]} />
          <Bar dataKey="Stakes Win %" fill="#f97316" radius={[4, 4, 0, 0]} />
          <Bar dataKey="GSW %" fill="#8b5cf6" radius={[4, 4, 0, 0]} />
          <Bar dataKey="G1 %" fill="#ef4444" radius={[4, 4, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

function SaleRadar({ sales }) {
  const maxWin = Math.max(...sales.map((s) => s.winPct));
  const maxSW = Math.max(...sales.map((s) => s.stakesWinPct));
  const maxGSW = Math.max(...sales.map((s) => s.gradedStakesPct));
  const maxG1 = Math.max(...sales.map((s) => s.g1Pct));
  const maxRunners = Math.max(...sales.map((s) => s.runners));

  const data = [
    { metric: "Win %", ...Object.fromEntries(sales.map((s) => [shortSale(s.sale), (s.winPct / maxWin) * 100])) },
    { metric: "SW %", ...Object.fromEntries(sales.map((s) => [shortSale(s.sale), (s.stakesWinPct / maxSW) * 100])) },
    { metric: "GSW %", ...Object.fromEntries(sales.map((s) => [shortSale(s.sale), (s.gradedStakesPct / maxGSW) * 100])) },
    { metric: "G1 %", ...Object.fromEntries(sales.map((s) => [shortSale(s.sale), (s.g1Pct / maxG1) * 100])) },
    { metric: "Volume", ...Object.fromEntries(sales.map((s) => [shortSale(s.sale), (s.runners / maxRunners) * 100])) },
  ];

  const colors = ["#3b82f6", "#16a34a", "#f97316", "#8b5cf6"];

  return (
    <div className="rounded-xl border border-gray-100 bg-white p-5 shadow-[0_1px_3px_rgba(0,0,0,0.04)]">
      <h3 className="text-sm font-semibold text-gray-900 mb-4">
        Sale Profile Comparison
      </h3>
      <ResponsiveContainer width="100%" height={340}>
        <RadarChart data={data}>
          <PolarGrid stroke="#e5e7eb" />
          <PolarAngleAxis
            dataKey="metric"
            tick={{ fill: "#6b7280", fontSize: 11 }}
          />
          <PolarRadiusAxis tick={false} axisLine={false} />
          {sales.map((s, i) => (
            <Radar
              key={s.sale}
              name={shortSale(s.sale)}
              dataKey={shortSale(s.sale)}
              stroke={colors[i % colors.length]}
              fill={colors[i % colors.length]}
              fillOpacity={0.1}
            />
          ))}
          <Legend iconSize={8} wrapperStyle={{ fontSize: 11, color: "#6b7280" }} />
          <Tooltip
            contentStyle={{
              backgroundColor: "#ffffff",
              border: "1px solid #e5e7eb",
              borderRadius: 8,
              fontSize: 12,
              boxShadow: "0 4px 12px rgba(0,0,0,0.08)",
            }}
            formatter={(val) => `${val.toFixed(0)}%`}
          />
        </RadarChart>
      </ResponsiveContainer>
    </div>
  );
}

function SaleTable({ sales }) {
  return (
    <div className="rounded-xl border border-gray-100 bg-white p-5 shadow-[0_1px_3px_rgba(0,0,0,0.04)]">
      <h3 className="text-sm font-semibold text-gray-900 mb-4">
        Full Breakdown
      </h3>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-100">
              {[
                "Sale",
                "Runners",
                "Winners",
                "Win %",
                "SW",
                "SW %",
                "GSW",
                "GSW %",
                "G1",
                "G1 %",
              ].map((h) => (
                <th
                  key={h}
                  className={`py-2 px-3 text-[11px] font-medium uppercase tracking-wider text-gray-400 ${
                    h === "Sale" ? "text-left" : "text-right"
                  }`}
                >
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-50">
            {sales.map((s) => (
              <tr key={s.sale} className="table-row-hover">
                <td className="py-2.5 px-3 font-medium text-gray-900 whitespace-nowrap">
                  {s.sale}
                </td>
                <td className="py-2.5 px-3 text-right font-mono text-gray-700">
                  {formatNumber(s.runners)}
                </td>
                <td className="py-2.5 px-3 text-right font-mono text-gray-700">
                  {formatNumber(s.winners)}
                </td>
                <td className="py-2.5 px-3 text-right font-mono text-brand-600 font-semibold">
                  {formatPercent(s.winPct)}
                </td>
                <td className="py-2.5 px-3 text-right font-mono text-gray-700">
                  {formatNumber(s.stakesWinners)}
                </td>
                <td className="py-2.5 px-3 text-right font-mono text-amber-600 font-semibold">
                  {formatPercent(s.stakesWinPct)}
                </td>
                <td className="py-2.5 px-3 text-right font-mono text-gray-700">
                  {formatNumber(s.gradedStakesWinners)}
                </td>
                <td className="py-2.5 px-3 text-right font-mono text-purple-600 font-semibold">
                  {formatPercent(s.gradedStakesPct)}
                </td>
                <td className="py-2.5 px-3 text-right font-mono text-gray-700">
                  {formatNumber(s.g1Winners)}
                </td>
                <td className="py-2.5 px-3 text-right font-mono text-red-500 font-semibold">
                  {formatPercent(s.g1Pct)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
