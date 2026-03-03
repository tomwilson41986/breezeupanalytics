import { useState, useMemo, useEffect } from "react";
import { Link } from "react-router-dom";
import { useHistoricRecords } from "../hooks/useHistoricData";
import LoadingSpinner from "../components/LoadingSpinner";
import ErrorBanner from "../components/ErrorBanner";
import StatCard from "../components/StatCard";
import { formatNumber, formatCurrency, formatPercent } from "../lib/format";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
  PieChart,
  Pie,
  Cell,
} from "recharts";

/** Map a vendor-data record's sale name to an s3Key for linking */
function recordToSaleKey(record) {
  const saleMap = {
    "OBS March Sale": "march",
    "OBS Spring Sale": "spring",
    "OBS June Sale": "june",
  };
  const season = saleMap[record.sale];
  if (!season) return null;
  return `obs_${season}_${record.year}`;
}

/** Determine highest performance level for a record */
function performanceLevel(r) {
  if (r.g1Winner) return "g1";
  if (r.gradedStakesWinner) return "gsw";
  if (r.stakesWinner) return "sw";
  if (r.winner) return "winner";
  if (r.runner) return "non-winner";
  return "unraced";
}

function performanceLabel(level) {
  const labels = {
    g1: "G1 Winner",
    gsw: "Graded Stakes Winner",
    sw: "Stakes Winner",
    winner: "Winner",
    "non-winner": "Non-Winner",
    unraced: "Unraced",
  };
  return labels[level] || level;
}

const PERFORMANCE_COLORS = {
  g1: { bg: "bg-red-100", text: "text-red-700", dot: "#ef4444", border: "border-red-200" },
  gsw: { bg: "bg-purple-100", text: "text-purple-700", dot: "#8b5cf6", border: "border-purple-200" },
  sw: { bg: "bg-blue-100", text: "text-blue-700", dot: "#3b82f6", border: "border-blue-200" },
  winner: { bg: "bg-emerald-100", text: "text-emerald-700", dot: "#22c55e", border: "border-emerald-200" },
  "non-winner": { bg: "bg-amber-100", text: "text-amber-700", dot: "#f59e0b", border: "border-amber-200" },
  unraced: { bg: "bg-gray-100", text: "text-gray-500", dot: "#9ca3af", border: "border-gray-200" },
};

function PerformanceBadge({ level }) {
  const c = PERFORMANCE_COLORS[level] || PERFORMANCE_COLORS.unraced;
  return (
    <span
      className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[11px] font-medium border ${c.bg} ${c.text} ${c.border}`}
    >
      <span
        className="w-2 h-2 rounded-full"
        style={{ backgroundColor: c.dot }}
      />
      {performanceLabel(level)}
    </span>
  );
}

const FILTER_OPTIONS = [
  { value: "all-performers", label: "All Performers (Winners+)" },
  { value: "g1", label: "G1 Winners" },
  { value: "gsw", label: "Graded Stakes Winners" },
  { value: "sw", label: "Stakes Winners" },
  { value: "winner", label: "Winners" },
  { value: "all", label: "All Records" },
];

export default function PerformanceTracker() {
  const { records, loading, error, load } = useHistoricRecords();
  const [performanceFilter, setPerformanceFilter] = useState("all-performers");
  const [saleFilter, setSaleFilter] = useState("all");
  const [yearFilter, setYearFilter] = useState("all");
  const [search, setSearch] = useState("");
  const [sortKey, setSortKey] = useState("g1Winner");
  const [sortDir, setSortDir] = useState("desc");
  const [page, setPage] = useState(0);
  const PER_PAGE = 25;

  useEffect(() => {
    load();
  }, []);

  // Unique sales and years for filters
  const { uniqueSales, uniqueYears } = useMemo(() => {
    if (!records) return { uniqueSales: [], uniqueYears: [] };
    const sales = [...new Set(records.map((r) => r.sale))].sort();
    const years = [...new Set(records.map((r) => r.year))].sort((a, b) => b - a);
    return { uniqueSales: sales, uniqueYears: years };
  }, [records]);

  // Filter records
  const filtered = useMemo(() => {
    if (!records) return [];
    let result = records;

    // Performance filter
    if (performanceFilter === "g1") {
      result = result.filter((r) => r.g1Winner);
    } else if (performanceFilter === "gsw") {
      result = result.filter((r) => r.gradedStakesWinner);
    } else if (performanceFilter === "sw") {
      result = result.filter((r) => r.stakesWinner);
    } else if (performanceFilter === "winner") {
      result = result.filter((r) => r.winner);
    } else if (performanceFilter === "all-performers") {
      result = result.filter((r) => r.winner);
    }

    // Sale filter
    if (saleFilter !== "all") {
      result = result.filter((r) => r.sale === saleFilter);
    }

    // Year filter
    if (yearFilter !== "all") {
      result = result.filter((r) => r.year === parseInt(yearFilter));
    }

    // Search
    if (search.trim()) {
      const q = search.toLowerCase().trim();
      result = result.filter(
        (r) =>
          (r.name && r.name.toLowerCase().includes(q)) ||
          (r.sire && r.sire.toLowerCase().includes(q)) ||
          (r.dam && r.dam.toLowerCase().includes(q)) ||
          (r.vendor && r.vendor.toLowerCase().includes(q)) ||
          String(r.hip).includes(q)
      );
    }

    return result;
  }, [records, performanceFilter, saleFilter, yearFilter, search]);

  // Sort
  const sorted = useMemo(() => {
    return [...filtered].sort((a, b) => {
      let va = a[sortKey];
      let vb = b[sortKey];
      if (typeof va === "string") va = va?.toLowerCase() || "";
      if (typeof vb === "string") vb = vb?.toLowerCase() || "";
      if (va == null) va = sortDir === "asc" ? Infinity : -Infinity;
      if (vb == null) vb = sortDir === "asc" ? Infinity : -Infinity;
      if (va < vb) return sortDir === "asc" ? -1 : 1;
      if (va > vb) return sortDir === "asc" ? 1 : -1;
      return 0;
    });
  }, [filtered, sortKey, sortDir]);

  const pageRecords = sorted.slice(page * PER_PAGE, (page + 1) * PER_PAGE);
  const totalPages = Math.ceil(sorted.length / PER_PAGE);

  function handleSort(key) {
    if (sortKey === key) setSortDir(sortDir === "asc" ? "desc" : "asc");
    else {
      setSortKey(key);
      setSortDir(key === "price" || key === "g1Winner" || key === "gradedStakesWinner" || key === "stakesWinner" ? "desc" : "asc");
    }
    setPage(0);
  }

  // Summary stats
  const stats = useMemo(() => {
    if (!records) return null;
    return {
      total: records.length,
      runners: records.filter((r) => r.runner).length,
      winners: records.filter((r) => r.winner).length,
      stakesWinners: records.filter((r) => r.stakesWinner).length,
      gsw: records.filter((r) => r.gradedStakesWinner).length,
      g1: records.filter((r) => r.g1Winner).length,
    };
  }, [records]);

  // Reset page when filters change
  useEffect(() => {
    setPage(0);
  }, [performanceFilter, saleFilter, yearFilter, search]);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-semibold text-gray-900 tracking-tight">
          Performance Tracker
        </h1>
        <p className="text-sm text-gray-500 mt-1">
          Track winners, stakes winners, graded stakes winners, and G1 winners
          across all historic 2YO breeze-up sales
        </p>
      </div>

      {loading && <LoadingSpinner message="Loading performance data..." />}
      {error && <ErrorBanner message={String(error)} />}

      {stats && (
        <>
          {/* Summary stat cards */}
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
            <StatCard
              label="Total Records"
              value={formatNumber(stats.total)}
            />
            <StatCard
              label="Runners"
              value={formatNumber(stats.runners)}
              sub={formatPercent((stats.runners / stats.total) * 100)}
            />
            <StatCard
              label="Winners"
              value={formatNumber(stats.winners)}
              sub={formatPercent((stats.winners / stats.runners) * 100)}
            />
            <StatCard
              label="Stakes Winners"
              value={formatNumber(stats.stakesWinners)}
              sub={formatPercent((stats.stakesWinners / stats.runners) * 100)}
              accent
            />
            <StatCard
              label="Graded SW"
              value={formatNumber(stats.gsw)}
              sub={formatPercent((stats.gsw / stats.runners) * 100)}
            />
            <StatCard
              label="G1 Winners"
              value={formatNumber(stats.g1)}
              sub={formatPercent((stats.g1 / stats.runners) * 100)}
              accent
            />
          </div>

          {/* Performance distribution charts */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <PerformanceBySale records={records} />
            <PerformancePie stats={stats} />
          </div>

          {/* Filters */}
          <div className="rounded-xl border border-gray-100 bg-white p-4 shadow-[0_1px_3px_rgba(0,0,0,0.04)]">
            <div className="flex flex-wrap items-center gap-3">
              <select
                value={performanceFilter}
                onChange={(e) => setPerformanceFilter(e.target.value)}
                className="bg-white border border-gray-200 rounded-lg px-3 py-2 text-sm text-gray-700 focus:outline-none focus:border-brand-400 focus:ring-2 focus:ring-brand-100"
              >
                {FILTER_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
              <select
                value={saleFilter}
                onChange={(e) => setSaleFilter(e.target.value)}
                className="bg-white border border-gray-200 rounded-lg px-3 py-2 text-sm text-gray-700 focus:outline-none focus:border-brand-400 focus:ring-2 focus:ring-brand-100"
              >
                <option value="all">All Sales</option>
                {uniqueSales.map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </select>
              <select
                value={yearFilter}
                onChange={(e) => setYearFilter(e.target.value)}
                className="bg-white border border-gray-200 rounded-lg px-3 py-2 text-sm text-gray-700 focus:outline-none focus:border-brand-400 focus:ring-2 focus:ring-brand-100"
              >
                <option value="all">All Years</option>
                {uniqueYears.map((y) => (
                  <option key={y} value={y}>
                    {y}
                  </option>
                ))}
              </select>
              <div className="flex-1 min-w-[200px]">
                <input
                  type="text"
                  placeholder="Search horse, sire, dam, or vendor..."
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  className="w-full bg-white border border-gray-200 rounded-lg px-3 py-2 text-sm text-gray-700 placeholder-gray-400 focus:outline-none focus:border-brand-400 focus:ring-2 focus:ring-brand-100"
                />
              </div>
              <span className="text-xs text-gray-400">
                {formatNumber(sorted.length)} results
              </span>
            </div>
          </div>

          {/* Table */}
          <PerformanceTable
            records={pageRecords}
            sortKey={sortKey}
            sortDir={sortDir}
            onSort={handleSort}
            page={page}
            totalPages={totalPages}
            totalRecords={sorted.length}
            onPageChange={setPage}
          />
        </>
      )}
    </div>
  );
}

/* ── Performance Table ─────────────────────────────────────── */

function PerformanceTable({
  records,
  sortKey,
  sortDir,
  onSort,
  page,
  totalPages,
  totalRecords,
  onPageChange,
}) {
  const cols = [
    { key: "hip", label: "Hip", align: "left" },
    { key: "name", label: "Horse", align: "left" },
    { key: "year", label: "Year", align: "center" },
    { key: "sale", label: "Sale", align: "left" },
    { key: "sire", label: "Sire", align: "left" },
    { key: "dam", label: "Dam", align: "left" },
    { key: "vendor", label: "Vendor", align: "left" },
    { key: "price", label: "Price", align: "right" },
    { key: "g1Winner", label: "Status", align: "center" },
  ];

  return (
    <div className="rounded-xl border border-gray-100 bg-white p-5 shadow-[0_1px_3px_rgba(0,0,0,0.04)]">
      <h3 className="text-sm font-semibold text-gray-900 mb-4">
        Performance Records
      </h3>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-100">
              {cols.map((c) => (
                <th
                  key={c.key}
                  onClick={() => onSort(c.key)}
                  className={`py-2 px-3 text-[11px] font-medium uppercase tracking-wider text-gray-400 cursor-pointer hover:text-gray-600 whitespace-nowrap ${
                    c.align === "left"
                      ? "text-left"
                      : c.align === "center"
                        ? "text-center"
                        : "text-right"
                  }`}
                >
                  {c.label}
                  {sortKey === c.key && (
                    <span className="ml-1">
                      {sortDir === "asc" ? "\u25B2" : "\u25BC"}
                    </span>
                  )}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-50">
            {records.map((r, i) => {
              const saleKey = recordToSaleKey(r);
              const level = performanceLevel(r);
              return (
                <tr key={`${r.sale}-${r.year}-${r.hip}-${i}`} className="table-row-hover">
                  <td className="py-2 px-3 font-mono font-semibold text-brand-600">
                    {saleKey ? (
                      <Link
                        to={`/sale/${saleKey}/hip/${r.hip}`}
                        className="hover:underline"
                      >
                        #{r.hip}
                      </Link>
                    ) : (
                      `#${r.hip}`
                    )}
                  </td>
                  <td className="py-2 px-3 text-gray-900 font-medium max-w-[160px] truncate">
                    {r.name ? (
                      saleKey ? (
                        <Link
                          to={`/sale/${saleKey}/hip/${r.hip}`}
                          className="hover:underline hover:text-brand-600"
                        >
                          {r.name}
                        </Link>
                      ) : (
                        r.name
                      )
                    ) : (
                      <span className="text-gray-400 italic">Unnamed</span>
                    )}
                  </td>
                  <td className="py-2 px-3 text-center text-gray-500 font-mono text-xs">
                    {r.year}
                  </td>
                  <td className="py-2 px-3 text-gray-600 text-xs max-w-[140px] truncate">
                    {r.sale}
                  </td>
                  <td className="py-2 px-3 text-gray-700 text-xs max-w-[120px] truncate">
                    {r.sire}
                  </td>
                  <td className="py-2 px-3 text-gray-500 text-xs max-w-[120px] truncate">
                    {r.dam}
                  </td>
                  <td className="py-2 px-3 text-gray-500 text-xs max-w-[120px] truncate">
                    {r.vendor}
                  </td>
                  <td className="py-2 px-3 text-right font-mono text-gray-700">
                    {r.price ? formatCurrency(r.price) : "\u2014"}
                  </td>
                  <td className="py-2 px-3 text-center">
                    <PerformanceBadge level={level} />
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {totalPages > 1 && (
        <div className="flex items-center justify-between mt-4 pt-3 border-t border-gray-100">
          <p className="text-xs text-gray-400">
            {formatNumber(totalRecords)} records \u2014 Page {page + 1} of{" "}
            {totalPages}
          </p>
          <div className="flex gap-1">
            <button
              onClick={() => onPageChange(0)}
              disabled={page === 0}
              className="px-2 py-1 text-xs rounded-md border border-gray-200 text-gray-600 hover:bg-gray-50 disabled:opacity-40"
            >
              First
            </button>
            <button
              onClick={() => onPageChange(Math.max(0, page - 1))}
              disabled={page === 0}
              className="px-3 py-1 text-xs rounded-md border border-gray-200 text-gray-600 hover:bg-gray-50 disabled:opacity-40"
            >
              Prev
            </button>
            <button
              onClick={() => onPageChange(Math.min(totalPages - 1, page + 1))}
              disabled={page >= totalPages - 1}
              className="px-3 py-1 text-xs rounded-md border border-gray-200 text-gray-600 hover:bg-gray-50 disabled:opacity-40"
            >
              Next
            </button>
            <button
              onClick={() => onPageChange(totalPages - 1)}
              disabled={page >= totalPages - 1}
              className="px-2 py-1 text-xs rounded-md border border-gray-200 text-gray-600 hover:bg-gray-50 disabled:opacity-40"
            >
              Last
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

/* ── Charts ────────────────────────────────────────────────── */

function PerformanceBySale({ records }) {
  const saleMap = {};
  for (const r of records) {
    if (!saleMap[r.sale]) {
      saleMap[r.sale] = { runners: 0, winners: 0, sw: 0, gsw: 0, g1: 0 };
    }
    if (r.runner) saleMap[r.sale].runners++;
    if (r.winner) saleMap[r.sale].winners++;
    if (r.stakesWinner) saleMap[r.sale].sw++;
    if (r.gradedStakesWinner) saleMap[r.sale].gsw++;
    if (r.g1Winner) saleMap[r.sale].g1++;
  }

  const SHORT = {
    "OBS March Sale": "March",
    "OBS Spring Sale": "Spring",
    "OBS June Sale": "June",
    "Fasig Tipton Midlantic Sale": "FT Mid",
    "Gulfstream Sale": "Gulf",
    "July 2yo Sale": "July",
    "Santa Anita 2yo Sale": "Santa Anita",
    "Texas 2yo Sale": "Texas",
  };

  const data = Object.entries(saleMap)
    .map(([sale, s]) => ({
      sale: SHORT[sale] || sale,
      Winners: s.winners,
      "Stakes W": s.sw,
      GSW: s.gsw,
      "G1 W": s.g1,
    }))
    .sort((a, b) => b.Winners - a.Winners);

  return (
    <div className="rounded-xl border border-gray-100 bg-white p-5 shadow-[0_1px_3px_rgba(0,0,0,0.04)]">
      <h3 className="text-sm font-semibold text-gray-900 mb-4">
        Performance by Sale
      </h3>
      <ResponsiveContainer width="100%" height={280}>
        <BarChart data={data} margin={{ top: 5, right: 10, left: 10, bottom: 5 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#f3f4f6" />
          <XAxis
            dataKey="sale"
            tick={{ fill: "#6b7280", fontSize: 10 }}
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
          <Bar dataKey="Winners" fill="#22c55e" radius={[4, 4, 0, 0]} />
          <Bar dataKey="Stakes W" fill="#3b82f6" radius={[4, 4, 0, 0]} />
          <Bar dataKey="GSW" fill="#8b5cf6" radius={[4, 4, 0, 0]} />
          <Bar dataKey="G1 W" fill="#ef4444" radius={[4, 4, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

function PerformancePie({ stats }) {
  const data = [
    { name: "G1 Winners", value: stats.g1, color: "#ef4444" },
    { name: "GSW (excl G1)", value: stats.gsw - stats.g1, color: "#8b5cf6" },
    { name: "SW (excl GSW)", value: stats.stakesWinners - stats.gsw, color: "#3b82f6" },
    { name: "Winners (excl SW)", value: stats.winners - stats.stakesWinners, color: "#22c55e" },
    { name: "Non-Winners", value: stats.runners - stats.winners, color: "#f59e0b" },
  ].filter((d) => d.value > 0);

  return (
    <div className="rounded-xl border border-gray-100 bg-white p-5 shadow-[0_1px_3px_rgba(0,0,0,0.04)]">
      <h3 className="text-sm font-semibold text-gray-900 mb-4">
        Runner Outcome Distribution
      </h3>
      <ResponsiveContainer width="100%" height={280}>
        <PieChart>
          <Pie
            data={data}
            cx="50%"
            cy="50%"
            innerRadius={55}
            outerRadius={90}
            paddingAngle={2}
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
            formatter={(val) => formatNumber(val)}
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
