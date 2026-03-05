import { useState, useEffect, useMemo } from "react";
import { Link, useNavigate } from "react-router-dom";
import { SALE_CATALOG, fetchRatingsFromS3 } from "../lib/api";
import { useSaleData } from "../hooks/useSaleData";
import LoadingSpinner from "../components/LoadingSpinner";
import ErrorBanner from "../components/ErrorBanner";
import { formatBreezeTime } from "../lib/format";
import {
  ScatterChart,
  Scatter,
  XAxis,
  YAxis,
  ZAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
} from "recharts";

const AXIS_OPTIONS = [
  { key: "timeUT", label: "UT Time", unit: "s" },
  { key: "strideLengthUT", label: "Stride Length UT", unit: "ft" },
  { key: "rating", label: "Breeze Rating", unit: "" },
  { key: "strideLengthGO", label: "Stride Length GO", unit: "ft" },
];

const DISTANCE_OPTIONS = [
  { value: "1/8", label: "1/8 Mile" },
  { value: "1/4", label: "1/4 Mile" },
  { value: "all", label: "All Distances" },
];

/* Color horses by rating band */
function ratingColor(rating) {
  if (rating == null) return "#9ca3af";
  if (rating >= 80) return "#059669";
  if (rating >= 60) return "#0284c7";
  if (rating >= 40) return "#d97706";
  return "#dc2626";
}

/* Get all live sale keys */
const liveSaleKeys = Object.entries(SALE_CATALOG)
  .filter(([, m]) => m.isLive && m.month === 3)
  .map(([key]) => key);

export default function BreezeScatter() {
  const [xAxis, setXAxis] = useState("timeUT");
  const [yAxis, setYAxis] = useState("strideLengthUT");
  const [distanceFilter, setDistanceFilter] = useState("1/8");
  const [saleKey, setSaleKey] = useState(liveSaleKeys[0] || "");
  const [search, setSearch] = useState("");

  const { sale, loading, error } = useSaleData(saleKey);
  const navigate = useNavigate();

  // Also fetch UT latest for breeze distance
  const [utLatest, setUtLatest] = useState(null);
  useEffect(() => {
    if (!saleKey) return;
    let cancelled = false;
    async function loadUt() {
      try {
        const res = await fetch(
          `/.netlify/functions/sale-data?sale=${encodeURIComponent(saleKey)}&type=under-tack/latest`
        );
        if (res.ok) {
          const data = await res.json();
          if (!cancelled) setUtLatest(data);
          return;
        }
      } catch {}
      try {
        const res = await fetch(`/data/under-tack/${saleKey}/latest.json`);
        if (res.ok) {
          const data = await res.json();
          if (!cancelled) setUtLatest(data);
        }
      } catch {}
    }
    loadUt();
    return () => { cancelled = true; };
  }, [saleKey]);

  // Build scatter data from sale hips with ratings
  const scatterData = useMemo(() => {
    if (!sale?.hips) return [];

    // Build UT lookup for breeze distance
    const utMap = {};
    if (utLatest?.hips) {
      for (const uh of utLatest.hips) {
        utMap[uh.hip_number] = uh;
      }
    }

    return sale.hips
      .filter((h) => h.ratings)
      .map((h) => {
        const ut = utMap[h.hipNumber];
        const breezeDistance = h.breezeDistance ?? ut?.ut_distance ?? null;
        return {
          hipNumber: h.hipNumber,
          horseName: h.horseName,
          sire: h.sire,
          dam: h.dam,
          consignor: h.consignor,
          breezeDistance,
          timeUT: h.ratings.timeUT,
          strideLengthUT: h.ratings.strideLengthUT,
          strideLengthGO: h.ratings.strideLengthGO,
          rating: h.ratings.rating,
          distanceUT: h.ratings.distanceUT,
          meanRank: h.ratings.meanRank,
          diff: h.ratings.diff,
          saleKey,
        };
      });
  }, [sale, utLatest, saleKey]);

  // Apply filters
  const filtered = useMemo(() => {
    let result = scatterData;

    if (distanceFilter !== "all") {
      result = result.filter((h) => {
        if (h.breezeDistance) return h.breezeDistance === distanceFilter;
        // Fallback: infer from distanceUT (feet)
        if (h.distanceUT) {
          const d = parseFloat(h.distanceUT);
          if (distanceFilter === "1/8") return d < 300;
          if (distanceFilter === "1/4") return d >= 300;
        }
        return true;
      });
    }

    if (search.trim()) {
      const q = search.toLowerCase().trim();
      result = result.filter(
        (h) =>
          String(h.hipNumber).includes(q) ||
          (h.horseName && h.horseName.toLowerCase().includes(q)) ||
          (h.sire && h.sire.toLowerCase().includes(q)) ||
          (h.dam && h.dam.toLowerCase().includes(q)) ||
          (h.consignor && h.consignor.toLowerCase().includes(q))
      );
    }

    return result;
  }, [scatterData, distanceFilter, search]);

  // Compute stats
  const stats = useMemo(() => {
    if (filtered.length === 0) return null;
    const xVals = filtered.map((h) => h[xAxis]).filter((v) => v != null);
    const yVals = filtered.map((h) => h[yAxis]).filter((v) => v != null);
    return {
      count: filtered.length,
      xMean: xVals.length ? xVals.reduce((a, b) => a + b, 0) / xVals.length : 0,
      yMean: yVals.length ? yVals.reduce((a, b) => a + b, 0) / yVals.length : 0,
    };
  }, [filtered, xAxis, yAxis]);

  const xConfig = AXIS_OPTIONS.find((o) => o.key === xAxis);
  const yConfig = AXIS_OPTIONS.find((o) => o.key === yAxis);
  const saleMeta = SALE_CATALOG[saleKey];

  return (
    <div className="space-y-6">
      {/* Breadcrumb */}
      <div className="flex items-center gap-2 text-sm">
        <Link
          to="/live"
          className="text-gray-400 hover:text-brand-600 transition-colors"
        >
          Live Sales
        </Link>
        <span className="text-gray-300">/</span>
        <span className="text-gray-700">Breeze Scatter Analysis</span>
      </div>

      {/* Header */}
      <div>
        <h1 className="text-xl sm:text-2xl font-semibold text-gray-900 tracking-tight">
          Breeze Scatter Analysis
        </h1>
        <p className="text-sm text-gray-500 mt-1">
          Scatter plot of breeze metrics — compare UT Time, Stride Lengths, and Breeze Ratings
        </p>
      </div>

      {/* Controls */}
      <div className="rounded-xl border border-gray-100 bg-white p-4 shadow-[0_1px_3px_rgba(0,0,0,0.04)]">
        <div className="flex flex-col sm:flex-row flex-wrap items-stretch sm:items-end gap-3">
          {/* Sale picker */}
          <div>
            <label className="block text-[11px] font-medium uppercase tracking-wider text-gray-400 mb-1">
              Sale
            </label>
            <select
              value={saleKey}
              onChange={(e) => setSaleKey(e.target.value)}
              className="bg-white border border-gray-200 rounded-lg px-3 py-2 text-sm text-gray-700 focus:outline-none focus:border-brand-400 focus:ring-2 focus:ring-brand-100"
            >
              {liveSaleKeys.map((key) => (
                <option key={key} value={key}>
                  {SALE_CATALOG[key]?.name || key}
                </option>
              ))}
            </select>
          </div>

          {/* Distance filter */}
          <div>
            <label className="block text-[11px] font-medium uppercase tracking-wider text-gray-400 mb-1">
              Distance
            </label>
            <select
              value={distanceFilter}
              onChange={(e) => setDistanceFilter(e.target.value)}
              className="bg-white border border-gray-200 rounded-lg px-3 py-2 text-sm text-gray-700 focus:outline-none focus:border-brand-400 focus:ring-2 focus:ring-brand-100"
            >
              {DISTANCE_OPTIONS.map((d) => (
                <option key={d.value} value={d.value}>
                  {d.label}
                </option>
              ))}
            </select>
          </div>

          {/* X Axis */}
          <div>
            <label className="block text-[11px] font-medium uppercase tracking-wider text-gray-400 mb-1">
              X Axis
            </label>
            <select
              value={xAxis}
              onChange={(e) => setXAxis(e.target.value)}
              className="bg-white border border-gray-200 rounded-lg px-3 py-2 text-sm text-gray-700 focus:outline-none focus:border-brand-400 focus:ring-2 focus:ring-brand-100"
            >
              {AXIS_OPTIONS.map((o) => (
                <option key={o.key} value={o.key}>
                  {o.label}
                </option>
              ))}
            </select>
          </div>

          {/* Y Axis */}
          <div>
            <label className="block text-[11px] font-medium uppercase tracking-wider text-gray-400 mb-1">
              Y Axis
            </label>
            <select
              value={yAxis}
              onChange={(e) => setYAxis(e.target.value)}
              className="bg-white border border-gray-200 rounded-lg px-3 py-2 text-sm text-gray-700 focus:outline-none focus:border-brand-400 focus:ring-2 focus:ring-brand-100"
            >
              {AXIS_OPTIONS.map((o) => (
                <option key={o.key} value={o.key}>
                  {o.label}
                </option>
              ))}
            </select>
          </div>

          {/* Search */}
          <div className="flex-1 min-w-0 sm:min-w-[180px]">
            <label className="block text-[11px] font-medium uppercase tracking-wider text-gray-400 mb-1">
              Search
            </label>
            <input
              type="text"
              placeholder="Hip, sire, dam, consignor..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full bg-white border border-gray-200 rounded-lg px-3 py-2 text-sm text-gray-700 placeholder-gray-400 focus:outline-none focus:border-brand-400 focus:ring-2 focus:ring-brand-100"
            />
          </div>
        </div>
      </div>

      {loading && <LoadingSpinner message="Loading breeze data..." />}
      {error && <ErrorBanner message={error} />}

      {!loading && !error && filtered.length === 0 && scatterData.length > 0 && (
        <div className="rounded-xl border border-gray-100 bg-white p-8 text-center shadow-[0_1px_3px_rgba(0,0,0,0.04)]">
          <p className="text-gray-400">No horses match the current filters</p>
        </div>
      )}

      {!loading && !error && scatterData.length === 0 && (
        <div className="rounded-xl border border-gray-100 bg-white p-8 text-center shadow-[0_1px_3px_rgba(0,0,0,0.04)]">
          <p className="text-gray-400">No rated horses available for this sale yet</p>
        </div>
      )}

      {!loading && filtered.length > 0 && (
        <>
          {/* Summary */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <div className="rounded-xl border border-gray-100 bg-white p-4 shadow-[0_1px_3px_rgba(0,0,0,0.04)]">
              <p className="text-[11px] uppercase tracking-wider text-gray-400">Horses</p>
              <p className="text-2xl font-semibold text-gray-900 mt-1">{stats?.count || 0}</p>
            </div>
            <div className="rounded-xl border border-gray-100 bg-white p-4 shadow-[0_1px_3px_rgba(0,0,0,0.04)]">
              <p className="text-[11px] uppercase tracking-wider text-gray-400">Avg {xConfig?.label}</p>
              <p className="text-2xl font-semibold font-mono text-gray-900 mt-1">
                {stats?.xMean?.toFixed(2)}{xConfig?.unit}
              </p>
            </div>
            <div className="rounded-xl border border-gray-100 bg-white p-4 shadow-[0_1px_3px_rgba(0,0,0,0.04)]">
              <p className="text-[11px] uppercase tracking-wider text-gray-400">Avg {yConfig?.label}</p>
              <p className="text-2xl font-semibold font-mono text-gray-900 mt-1">
                {stats?.yMean?.toFixed(2)}{yConfig?.unit}
              </p>
            </div>
            <div className="rounded-xl border border-gray-100 bg-white p-4 shadow-[0_1px_3px_rgba(0,0,0,0.04)]">
              <p className="text-[11px] uppercase tracking-wider text-gray-400">Distance</p>
              <p className="text-2xl font-semibold text-gray-900 mt-1">
                {distanceFilter === "all" ? "All" : `${distanceFilter} mi`}
              </p>
            </div>
          </div>

          {/* Scatter chart */}
          <div className="rounded-xl border border-gray-100 bg-white p-4 sm:p-5 shadow-[0_1px_3px_rgba(0,0,0,0.04)]">
            <h3 className="text-sm font-semibold text-gray-900 mb-4">
              {xConfig?.label} vs {yConfig?.label}
              <span className="text-xs font-normal text-gray-400 ml-2">
                {filtered.length} horses
              </span>
            </h3>
            <ResponsiveContainer width="100%" height={420}>
              <ScatterChart margin={{ top: 10, right: 20, left: 10, bottom: 20 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f3f4f6" />
                <XAxis
                  dataKey={xAxis}
                  name={xConfig?.label}
                  type="number"
                  domain={["auto", "auto"]}
                  tick={{ fill: "#6b7280", fontSize: 11 }}
                  axisLine={{ stroke: "#e5e7eb" }}
                  tickLine={false}
                  label={{
                    value: `${xConfig?.label}${xConfig?.unit ? ` (${xConfig.unit})` : ""}`,
                    position: "insideBottom",
                    offset: -10,
                    style: { fill: "#9ca3af", fontSize: 11 },
                  }}
                />
                <YAxis
                  dataKey={yAxis}
                  name={yConfig?.label}
                  type="number"
                  domain={["auto", "auto"]}
                  tick={{ fill: "#6b7280", fontSize: 11 }}
                  axisLine={{ stroke: "#e5e7eb" }}
                  tickLine={false}
                  label={{
                    value: `${yConfig?.label}${yConfig?.unit ? ` (${yConfig.unit})` : ""}`,
                    angle: -90,
                    position: "insideLeft",
                    offset: 0,
                    style: { fill: "#9ca3af", fontSize: 11 },
                  }}
                />
                <ZAxis range={[48, 48]} />
                {stats?.xMean && (
                  <ReferenceLine
                    x={stats.xMean}
                    stroke="#e5e7eb"
                    strokeDasharray="4 4"
                    label={{ value: "avg", position: "top", fill: "#9ca3af", fontSize: 10 }}
                  />
                )}
                {stats?.yMean && (
                  <ReferenceLine
                    y={stats.yMean}
                    stroke="#e5e7eb"
                    strokeDasharray="4 4"
                    label={{ value: "avg", position: "right", fill: "#9ca3af", fontSize: 10 }}
                  />
                )}
                <Tooltip content={<ScatterTooltip xConfig={xConfig} yConfig={yConfig} />} />
                <Scatter
                  data={filtered}
                  fill="#6366f1"
                  fillOpacity={0.7}
                  shape={(props) => {
                    const { cx, cy, payload } = props;
                    return (
                      <circle
                        cx={cx}
                        cy={cy}
                        r={5}
                        fill={ratingColor(payload.rating)}
                        fillOpacity={0.75}
                        stroke="#fff"
                        strokeWidth={1}
                        style={{ cursor: "pointer" }}
                        onClick={() => navigate(`/sale/${payload.saleKey}/hip/${payload.hipNumber}`)}
                      />
                    );
                  }}
                />
              </ScatterChart>
            </ResponsiveContainer>

            {/* Color legend */}
            <div className="flex flex-wrap items-center gap-4 mt-3 pt-3 border-t border-gray-50">
              <span className="text-[11px] font-medium text-gray-400 uppercase tracking-wider">
                Breeze Rating:
              </span>
              {[
                { label: "80+", color: "#059669" },
                { label: "60-79", color: "#0284c7" },
                { label: "40-59", color: "#d97706" },
                { label: "< 40", color: "#dc2626" },
                { label: "N/A", color: "#9ca3af" },
              ].map((item) => (
                <span key={item.label} className="flex items-center gap-1.5 text-xs text-gray-500">
                  <span
                    className="w-3 h-3 rounded-full border border-white shadow-sm"
                    style={{ backgroundColor: item.color }}
                  />
                  {item.label}
                </span>
              ))}
            </div>
          </div>

          {/* Data table */}
          <ScatterTable data={filtered} xAxis={xAxis} yAxis={yAxis} xConfig={xConfig} yConfig={yConfig} saleKey={saleKey} />
        </>
      )}
    </div>
  );
}

/* ── Scatter tooltip ───────────────────────────────── */

function ScatterTooltip({ active, payload, xConfig, yConfig }) {
  if (!active || !payload?.length) return null;
  const d = payload[0]?.payload;
  if (!d) return null;

  return (
    <div className="bg-white border border-gray-200 rounded-lg shadow-lg p-3 text-sm max-w-[280px]">
      <div className="flex items-center gap-2 mb-1">
        <span
          className="w-2.5 h-2.5 rounded-full"
          style={{ backgroundColor: ratingColor(d.rating) }}
        />
        <span className="font-semibold text-gray-900">Hip #{d.hipNumber}</span>
      </div>
      {d.horseName && (
        <p className="text-gray-700 font-medium">{d.horseName}</p>
      )}
      <p className="text-gray-500 text-xs">{d.sire} &middot; {d.dam}</p>
      <div className="grid grid-cols-2 gap-x-4 gap-y-1 mt-2 text-xs">
        <span className="text-gray-500">
          {xConfig?.label}:{" "}
          <span className="font-mono font-semibold text-gray-700">
            {d[xConfig?.key]?.toFixed(2)}{xConfig?.unit}
          </span>
        </span>
        <span className="text-gray-500">
          {yConfig?.label}:{" "}
          <span className="font-mono font-semibold text-gray-700">
            {d[yConfig?.key]?.toFixed(2)}{yConfig?.unit}
          </span>
        </span>
        {d.rating != null && (
          <span className="text-gray-500">
            Breeze Rating:{" "}
            <span className="font-mono font-semibold text-gray-700">
              {d.rating.toFixed(1)}
            </span>
          </span>
        )}
        {d.breezeDistance && (
          <span className="text-gray-500">
            Distance:{" "}
            <span className="font-mono font-semibold text-gray-700">{d.breezeDistance}</span>
          </span>
        )}
      </div>
    </div>
  );
}

/* ── Data table ──────────────────────────────────────── */

function ScatterTable({ data, xAxis, yAxis, xConfig, yConfig, saleKey }) {
  const [sortKey, setSortKey] = useState("rating");
  const [sortDir, setSortDir] = useState("desc");
  const [page, setPage] = useState(0);
  const PER_PAGE = 25;

  const sorted = useMemo(() => {
    return [...data].sort((a, b) => {
      let va = a[sortKey];
      let vb = b[sortKey];
      if (va == null) return 1;
      if (vb == null) return -1;
      if (typeof va === "string") va = va.toLowerCase();
      if (typeof vb === "string") vb = vb.toLowerCase();
      if (va < vb) return sortDir === "asc" ? -1 : 1;
      if (va > vb) return sortDir === "asc" ? 1 : -1;
      return 0;
    });
  }, [data, sortKey, sortDir]);

  const pageData = sorted.slice(page * PER_PAGE, (page + 1) * PER_PAGE);
  const totalPages = Math.ceil(sorted.length / PER_PAGE);

  function handleSort(key) {
    if (sortKey === key) setSortDir(sortDir === "asc" ? "desc" : "asc");
    else {
      setSortKey(key);
      setSortDir(key === "hipNumber" || key === "sire" ? "asc" : "desc");
    }
    setPage(0);
  }

  const cols = [
    { key: "hipNumber", label: "Hip" },
    { key: "horseName", label: "Horse" },
    { key: "sire", label: "Sire" },
    { key: xAxis, label: xConfig?.label },
    { key: yAxis, label: yConfig?.label },
    { key: "rating", label: "Breeze Rating" },
    { key: "breezeDistance", label: "Dist" },
  ];

  return (
    <div className="rounded-xl border border-gray-100 bg-white p-4 sm:p-5 shadow-[0_1px_3px_rgba(0,0,0,0.04)]">
      <h3 className="text-sm font-semibold text-gray-900 mb-3">
        Horse Data ({data.length} horses)
      </h3>
      <div className="overflow-x-auto -mx-4 sm:-mx-5 px-4 sm:px-5">
        <table className="w-full text-sm min-w-[600px]">
          <thead>
            <tr className="border-b border-gray-100">
              {cols.map((c) => (
                <th
                  key={c.key}
                  onClick={() => handleSort(c.key)}
                  className="py-2 px-3 text-left text-[11px] font-medium uppercase tracking-wider text-gray-400 cursor-pointer hover:text-gray-600 whitespace-nowrap"
                >
                  {c.label}
                  {sortKey === c.key && (
                    <span className="ml-1 text-brand-600">
                      {sortDir === "asc" ? "\u2191" : "\u2193"}
                    </span>
                  )}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-50">
            {pageData.map((h) => (
              <tr key={h.hipNumber} className="table-row-hover">
                <td className="py-2 px-3 font-mono font-semibold text-brand-600">
                  <Link
                    to={`/sale/${saleKey}/hip/${h.hipNumber}`}
                    className="hover:underline"
                  >
                    {h.hipNumber}
                  </Link>
                </td>
                <td className="py-2 px-3 text-gray-900 font-medium max-w-[140px] truncate">
                  {h.horseName || <span className="text-gray-400 italic">Unnamed</span>}
                </td>
                <td className="py-2 px-3 text-gray-600 text-xs max-w-[120px] truncate">
                  {h.sire}
                </td>
                <td className="py-2 px-3 font-mono text-gray-700">
                  {h[xAxis] != null ? h[xAxis].toFixed(2) : "\u2014"}
                  <span className="text-[10px] text-gray-400">{xConfig?.unit}</span>
                </td>
                <td className="py-2 px-3 font-mono text-gray-700">
                  {h[yAxis] != null ? h[yAxis].toFixed(2) : "\u2014"}
                  <span className="text-[10px] text-gray-400">{yConfig?.unit}</span>
                </td>
                <td className="py-2 px-3">
                  {h.rating != null ? (
                    <span
                      className="inline-flex items-center px-2 py-0.5 rounded-md text-xs font-semibold font-mono border"
                      style={{
                        color: ratingColor(h.rating),
                        borderColor: ratingColor(h.rating) + "33",
                        backgroundColor: ratingColor(h.rating) + "0d",
                      }}
                    >
                      {h.rating.toFixed(1)}
                    </span>
                  ) : (
                    <span className="text-gray-300">\u2014</span>
                  )}
                </td>
                <td className="py-2 px-3 text-gray-500 text-xs">
                  {h.breezeDistance || h.distanceUT || "\u2014"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {totalPages > 1 && (
        <div className="flex items-center justify-between mt-4 pt-3 border-t border-gray-100">
          <p className="text-xs text-gray-400">
            Page {page + 1} of {totalPages}
          </p>
          <div className="flex gap-1">
            <button
              onClick={() => setPage(Math.max(0, page - 1))}
              disabled={page === 0}
              className="px-3 py-1 text-xs rounded-md border border-gray-200 text-gray-600 hover:bg-gray-50 disabled:opacity-40"
            >
              Prev
            </button>
            <button
              onClick={() => setPage(Math.min(totalPages - 1, page + 1))}
              disabled={page >= totalPages - 1}
              className="px-3 py-1 text-xs rounded-md border border-gray-200 text-gray-600 hover:bg-gray-50 disabled:opacity-40"
            >
              Next
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
