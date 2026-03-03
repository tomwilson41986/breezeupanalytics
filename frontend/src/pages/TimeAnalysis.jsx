import { useState, useEffect, useMemo } from "react";
import { Link } from "react-router-dom";
import { SALE_CATALOG } from "../lib/api";
import { useSaleData } from "../hooks/useSaleData";
import LoadingSpinner from "../components/LoadingSpinner";
import ErrorBanner from "../components/ErrorBanner";
import StatCard from "../components/StatCard";
import { formatNumber, formatPercent, formatCurrency, formatCompact, formatBreezeTime } from "../lib/format";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ScatterChart,
  Scatter,
  ZAxis,
  Cell,
  Legend,
} from "recharts";

const analyticsSales = Object.entries(SALE_CATALOG)
  .filter(([, meta]) => meta.hasData)
  .sort(([, a], [, b]) => b.year - a.year || b.month - a.month);

function median(arr) {
  if (!arr.length) return 0;
  const sorted = [...arr].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
}

function saleName(key) {
  const meta = SALE_CATALOG[key];
  if (!meta) return key;
  const month = meta.month === 3 ? "March" : meta.month === 4 ? "Spring" : "June";
  return `${month} ${meta.year}`;
}

export default function TimeAnalysis() {
  const [selectedSaleKey, setSelectedSaleKey] = useState("all");
  const [distanceFilter, setDistanceFilter] = useState("all");

  // Load all sales with data
  const [allSaleData, setAllSaleData] = useState({});
  const [loadingSales, setLoadingSales] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoadingSales(true);

    async function loadAll() {
      const results = {};
      for (const [key] of analyticsSales) {
        try {
          const res = await fetch(
            `/.netlify/functions/sale-data?sale=${encodeURIComponent(key)}`
          );
          if (res.ok) {
            const data = await res.json();
            if (data && data.hips) {
              results[key] = data.hips;
            }
          }
        } catch {
          // Skip failed sales
        }
      }
      if (!cancelled) {
        setAllSaleData(results);
        setLoadingSales(false);
      }
    }

    loadAll();
    return () => { cancelled = true; };
  }, []);

  // Normalize hip data from S3 format
  const allHips = useMemo(() => {
    const hips = [];
    for (const [saleKey, rawHips] of Object.entries(allSaleData)) {
      for (const h of rawHips) {
        const time = h.under_tack_time || null;
        const distance = h.under_tack_distance
          ? h.under_tack_distance.trim()
          : null;
        if (!time || !distance) continue;
        hips.push({
          saleKey,
          hip: h.hip_number,
          time: parseFloat(time),
          distance,
          price: h.sale_price || null,
          status: (h.sale_status || "pending").toLowerCase(),
          sire: h.sire || "Unknown",
          dam: h.dam || "Unknown",
          sex: h.sex || "—",
          consignor: h.consignor || "—",
          name: h.horse_name || null,
        });
      }
    }
    return hips;
  }, [allSaleData]);

  // Filter by sale and distance
  const filtered = useMemo(() => {
    let result = allHips;
    if (selectedSaleKey !== "all") {
      result = result.filter((h) => h.saleKey === selectedSaleKey);
    }
    if (distanceFilter !== "all") {
      result = result.filter((h) => h.distance === distanceFilter);
    }
    return result;
  }, [allHips, selectedSaleKey, distanceFilter]);

  // Split by distance
  const eighthHips = useMemo(
    () => filtered.filter((h) => h.distance === "1/8"),
    [filtered]
  );
  const quarterHips = useMemo(
    () => filtered.filter((h) => h.distance === "1/4"),
    [filtered]
  );

  // Calculate medians per sale
  const saleMedians = useMemo(() => {
    const medians = {};
    for (const [saleKey, rawHips] of Object.entries(allSaleData)) {
      const eightTimes = [];
      const quarterTimes = [];
      for (const h of rawHips) {
        const time = h.under_tack_time ? parseFloat(h.under_tack_time) : null;
        const dist = h.under_tack_distance
          ? h.under_tack_distance.trim()
          : null;
        if (!time || !dist) continue;
        if (dist === "1/8") eightTimes.push(time);
        else if (dist === "1/4") quarterTimes.push(time);
      }
      medians[saleKey] = {
        eighth: median(eightTimes),
        quarter: median(quarterTimes),
        eighthCount: eightTimes.length,
        quarterCount: quarterTimes.length,
      };
    }
    return medians;
  }, [allSaleData]);

  // Enrich hips with median diff
  const enrichedHips = useMemo(() => {
    return filtered.map((h) => {
      const m = saleMedians[h.saleKey];
      const medianTime = h.distance === "1/8" ? m?.eighth : m?.quarter;
      return {
        ...h,
        medianTime,
        diffToMedian: medianTime ? +(h.time - medianTime).toFixed(2) : null,
      };
    });
  }, [filtered, saleMedians]);

  const availableDistances = useMemo(() => {
    const set = new Set(allHips.map((h) => h.distance));
    return [...set].sort();
  }, [allHips]);

  // Overall stats
  const eighthTimes = eighthHips.map((h) => h.time);
  const quarterTimes = quarterHips.map((h) => h.time);
  const allTimes = filtered.map((h) => h.time);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-gray-900 tracking-tight">
            Time Analysis
          </h1>
          <p className="text-sm text-gray-500 mt-1">
            Under-tack breeze times, distributions, and performance correlation
          </p>
        </div>
        <div className="flex gap-2">
          <select
            value={distanceFilter}
            onChange={(e) => setDistanceFilter(e.target.value)}
            className="bg-white border border-gray-200 rounded-lg px-3 py-2 text-sm text-gray-700 focus:outline-none focus:border-brand-400 focus:ring-2 focus:ring-brand-100"
          >
            <option value="all">All Distances</option>
            {availableDistances.map((d) => (
              <option key={d} value={d}>
                {d} Mile
              </option>
            ))}
          </select>
          <select
            value={selectedSaleKey}
            onChange={(e) => setSelectedSaleKey(e.target.value)}
            className="bg-white border border-gray-200 rounded-lg px-3 py-2 text-sm text-gray-700 focus:outline-none focus:border-brand-400 focus:ring-2 focus:ring-brand-100"
          >
            <option value="all">All Sales</option>
            {analyticsSales.map(([key]) => (
              <option key={key} value={key}>
                {saleName(key)}
              </option>
            ))}
          </select>
        </div>
      </div>

      {loadingSales && <LoadingSpinner message="Loading breeze time data..." />}

      {!loadingSales && allHips.length === 0 && (
        <ErrorBanner message="No breeze time data available yet. Times will appear as sales complete their under-tack shows." />
      )}

      {!loadingSales && allHips.length > 0 && (
        <>
          {/* Summary stats */}
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
            <StatCard
              label="Total Timed"
              value={formatNumber(filtered.length)}
            />
            <StatCard
              label="1/8 Mile"
              value={formatNumber(eighthHips.length)}
              sub={eighthTimes.length ? `Med: ${formatBreezeTime(median(eighthTimes))}` : "—"}
            />
            <StatCard
              label="1/4 Mile"
              value={formatNumber(quarterHips.length)}
              sub={quarterTimes.length ? `Med: ${formatBreezeTime(median(quarterTimes))}` : "—"}
            />
            <StatCard
              label="Fastest 1/8"
              value={eighthTimes.length ? formatBreezeTime(Math.min(...eighthTimes)) : "—"}
              accent
            />
            <StatCard
              label="Fastest 1/4"
              value={quarterTimes.length ? formatBreezeTime(Math.min(...quarterTimes)) : "—"}
              accent
            />
            <StatCard
              label="Avg Time"
              value={allTimes.length ? formatBreezeTime(allTimes.reduce((s, t) => s + t, 0) / allTimes.length) : "—"}
            />
          </div>

          {/* Time distribution charts */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {eighthHips.length > 0 && (
              <TimeDistribution
                hips={eighthHips}
                title="1/8 Mile Time Distribution"
                color="#3b82f6"
              />
            )}
            {quarterHips.length > 0 && (
              <TimeDistribution
                hips={quarterHips}
                title="1/4 Mile Time Distribution"
                color="#8b5cf6"
              />
            )}
          </div>

          {/* Time vs Price scatter */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {eighthHips.length > 0 && (
              <TimeVsPrice
                hips={eighthHips}
                title="1/8 Mile: Time vs Sale Price"
                color="#3b82f6"
                minDomain={9}
              />
            )}
            {quarterHips.length > 0 && (
              <TimeVsPrice
                hips={quarterHips}
                title="1/4 Mile: Time vs Sale Price"
                color="#8b5cf6"
                minDomain={19}
              />
            )}
          </div>

          {/* Median comparison by sale */}
          {selectedSaleKey === "all" && Object.keys(saleMedians).length > 1 && (
            <MedianBySale saleMedians={saleMedians} />
          )}

          {/* Difference to median table */}
          <DiffToMedianTable hips={enrichedHips} />

          {/* Outcome analysis by time bucket */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {eighthHips.length > 0 && (
              <TimeBucketOutcomes
                hips={eighthHips}
                title="1/8 Mile: Price by Time Bucket"
                distance="1/8"
              />
            )}
            {quarterHips.length > 0 && (
              <TimeBucketOutcomes
                hips={quarterHips}
                title="1/4 Mile: Price by Time Bucket"
                distance="1/4"
              />
            )}
          </div>
        </>
      )}
    </div>
  );
}

/* ── Sub Components ───────────────────────────────────────── */

function TimeDistribution({ hips, title, color }) {
  const times = hips.map((h) => h.time);
  const min = Math.floor(Math.min(...times) * 5) / 5;
  const max = Math.ceil(Math.max(...times) * 5) / 5;
  const step = 0.2;

  const buckets = [];
  for (let t = min; t < max; t = +(t + step).toFixed(1)) {
    const high = +(t + step).toFixed(1);
    const count = times.filter((v) => v >= t && v < high).length;
    buckets.push({ label: `${t.toFixed(1)}s`, count });
  }

  return (
    <div className="rounded-xl border border-gray-100 bg-white p-5 shadow-[0_1px_3px_rgba(0,0,0,0.04)]">
      <h3 className="text-sm font-semibold text-gray-900 mb-4">{title}</h3>
      <ResponsiveContainer width="100%" height={260}>
        <BarChart
          data={buckets}
          margin={{ top: 5, right: 10, left: 10, bottom: 5 }}
        >
          <CartesianGrid strokeDasharray="3 3" stroke="#f3f4f6" />
          <XAxis
            dataKey="label"
            tick={{ fill: "#6b7280", fontSize: 10 }}
            axisLine={{ stroke: "#e5e7eb" }}
            tickLine={false}
            interval={0}
            angle={-45}
            textAnchor="end"
            height={50}
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
          <Bar dataKey="count" name="Horses" fill={color} radius={[4, 4, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

function TimeVsPrice({ hips, title, color, minDomain }) {
  const data = hips
    .filter((h) => h.price && h.price > 0)
    .map((h) => ({
      time: h.time,
      price: h.price,
      label: `Hip #${h.hip} — ${h.sire}`,
    }));

  if (data.length === 0) return null;

  const xDomain = minDomain != null ? [minDomain, 'auto'] : ['auto', 'auto'];

  return (
    <div className="rounded-xl border border-gray-100 bg-white p-5 shadow-[0_1px_3px_rgba(0,0,0,0.04)]">
      <h3 className="text-sm font-semibold text-gray-900 mb-4">{title}</h3>
      <ResponsiveContainer width="100%" height={280}>
        <ScatterChart margin={{ top: 5, right: 20, left: 10, bottom: 5 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#f3f4f6" />
          <XAxis
            dataKey="time"
            name="Time"
            unit="s"
            type="number"
            domain={xDomain}
            tick={{ fill: "#6b7280", fontSize: 11 }}
            axisLine={{ stroke: "#e5e7eb" }}
            tickLine={false}
          />
          <YAxis
            dataKey="price"
            name="Price"
            type="number"
            tickFormatter={(v) => formatCompact(v)}
            tick={{ fill: "#6b7280", fontSize: 11 }}
            axisLine={{ stroke: "#e5e7eb" }}
            tickLine={false}
          />
          <ZAxis range={[30, 30]} />
          <Tooltip
            contentStyle={{
              backgroundColor: "#ffffff",
              border: "1px solid #e5e7eb",
              borderRadius: 8,
              fontSize: 12,
              boxShadow: "0 4px 12px rgba(0,0,0,0.08)",
            }}
            formatter={(val, name) =>
              name === "Price" ? formatCurrency(val) : `${val}s`
            }
            labelFormatter={() => ""}
          />
          <Scatter data={data} fill={color} fillOpacity={0.6} />
        </ScatterChart>
      </ResponsiveContainer>
    </div>
  );
}

function MedianBySale({ saleMedians }) {
  const data = Object.entries(saleMedians)
    .map(([key, m]) => ({
      sale: saleName(key),
      "1/8 Median": m.eighth || null,
      "1/4 Median": m.quarter || null,
      eighthCount: m.eighthCount,
      quarterCount: m.quarterCount,
    }))
    .filter((d) => d["1/8 Median"] || d["1/4 Median"]);

  if (data.length === 0) return null;

  return (
    <div className="rounded-xl border border-gray-100 bg-white p-5 shadow-[0_1px_3px_rgba(0,0,0,0.04)]">
      <h3 className="text-sm font-semibold text-gray-900 mb-4">
        Median Breeze Times by Sale
      </h3>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-100">
              <th className="text-left py-2 px-3 text-[11px] font-medium uppercase tracking-wider text-gray-400">
                Sale
              </th>
              <th className="text-right py-2 px-3 text-[11px] font-medium uppercase tracking-wider text-gray-400">
                1/8 Median
              </th>
              <th className="text-right py-2 px-3 text-[11px] font-medium uppercase tracking-wider text-gray-400">
                1/8 Count
              </th>
              <th className="text-right py-2 px-3 text-[11px] font-medium uppercase tracking-wider text-gray-400">
                1/4 Median
              </th>
              <th className="text-right py-2 px-3 text-[11px] font-medium uppercase tracking-wider text-gray-400">
                1/4 Count
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-50">
            {data.map((d) => (
              <tr key={d.sale} className="table-row-hover">
                <td className="py-2.5 px-3 font-medium text-gray-900">
                  {d.sale}
                </td>
                <td className="py-2.5 px-3 text-right font-mono text-brand-600 font-semibold">
                  {d["1/8 Median"] ? formatBreezeTime(d["1/8 Median"]) : "—"}
                </td>
                <td className="py-2.5 px-3 text-right font-mono text-gray-500">
                  {formatNumber(d.eighthCount)}
                </td>
                <td className="py-2.5 px-3 text-right font-mono text-purple-600 font-semibold">
                  {d["1/4 Median"] ? formatBreezeTime(d["1/4 Median"]) : "—"}
                </td>
                <td className="py-2.5 px-3 text-right font-mono text-gray-500">
                  {formatNumber(d.quarterCount)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function DiffToMedianTable({ hips }) {
  const [sortKey, setSortKey] = useState("diffToMedian");
  const [sortDir, setSortDir] = useState("asc");
  const [page, setPage] = useState(0);
  const PER_PAGE = 25;

  function handleSort(key) {
    if (sortKey === key) setSortDir(sortDir === "asc" ? "desc" : "asc");
    else {
      setSortKey(key);
      setSortDir("asc");
    }
    setPage(0);
  }

  const sorted = useMemo(() => {
    return [...hips].sort((a, b) => {
      let va = a[sortKey];
      let vb = b[sortKey];
      if (va == null) va = Infinity;
      if (vb == null) vb = Infinity;
      return sortDir === "asc" ? va - vb : vb - va;
    });
  }, [hips, sortKey, sortDir]);

  const pageHips = sorted.slice(page * PER_PAGE, (page + 1) * PER_PAGE);
  const totalPages = Math.ceil(sorted.length / PER_PAGE);

  const cols = [
    { key: "hip", label: "Hip", align: "left" },
    { key: "saleKey", label: "Sale", align: "left" },
    { key: "distance", label: "Dist", align: "center" },
    { key: "time", label: "Time", align: "right" },
    { key: "medianTime", label: "Median", align: "right" },
    { key: "diffToMedian", label: "Diff", align: "right" },
    { key: "price", label: "Price", align: "right" },
    { key: "sire", label: "Sire", align: "left" },
  ];

  return (
    <div className="rounded-xl border border-gray-100 bg-white p-5 shadow-[0_1px_3px_rgba(0,0,0,0.04)]">
      <h3 className="text-sm font-semibold text-gray-900 mb-4">
        Individual Times &amp; Difference to Sale Median
      </h3>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-100">
              {cols.map((c) => (
                <th
                  key={c.key}
                  onClick={() => handleSort(c.key)}
                  className={`py-2 px-3 text-[11px] font-medium uppercase tracking-wider text-gray-400 cursor-pointer hover:text-gray-600 ${
                    c.align === "left"
                      ? "text-left"
                      : c.align === "center"
                        ? "text-center"
                        : "text-right"
                  }`}
                >
                  {c.label}
                  {sortKey === c.key && (
                    <span className="ml-1">{sortDir === "asc" ? "▲" : "▼"}</span>
                  )}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-50">
            {pageHips.map((h, i) => (
              <tr key={`${h.saleKey}-${h.hip}-${i}`} className="table-row-hover">
                <td className="py-2 px-3 font-mono font-semibold text-brand-600">
                  <Link
                    to={`/sale/${h.saleKey}/hip/${h.hip}`}
                    className="hover:underline"
                  >
                    #{h.hip}
                  </Link>
                </td>
                <td className="py-2 px-3 text-gray-600 text-xs">
                  {saleName(h.saleKey)}
                </td>
                <td className="py-2 px-3 text-center text-gray-500">
                  {h.distance}
                </td>
                <td className="py-2 px-3 text-right font-mono text-gray-900 font-semibold">
                  {formatBreezeTime(h.time)}
                </td>
                <td className="py-2 px-3 text-right font-mono text-gray-400">
                  {h.medianTime ? formatBreezeTime(h.medianTime) : "—"}
                </td>
                <td
                  className={`py-2 px-3 text-right font-mono font-semibold ${
                    h.diffToMedian == null
                      ? "text-gray-400"
                      : h.diffToMedian < 0
                        ? "text-emerald-600"
                        : h.diffToMedian > 0
                          ? "text-red-500"
                          : "text-gray-500"
                  }`}
                >
                  {h.diffToMedian != null
                    ? `${h.diffToMedian > 0 ? "+" : ""}${h.diffToMedian.toFixed(2)}s`
                    : "—"}
                </td>
                <td className="py-2 px-3 text-right font-mono text-gray-700">
                  {h.price ? formatCurrency(h.price) : "—"}
                </td>
                <td className="py-2 px-3 text-gray-600 text-xs max-w-[140px] truncate">
                  {h.sire}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {totalPages > 1 && (
        <div className="flex items-center justify-between mt-4 pt-3 border-t border-gray-100">
          <p className="text-xs text-gray-400">
            {formatNumber(sorted.length)} horses — Page {page + 1} of{" "}
            {totalPages}
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

function TimeBucketOutcomes({ hips, title, distance }) {
  // Create time buckets based on distance
  const times = hips.map((h) => h.time);
  const minTime = Math.floor(Math.min(...times) * 5) / 5;
  const maxTime = Math.ceil(Math.max(...times) * 5) / 5;
  const step = 0.2;

  const buckets = [];
  for (let t = minTime; t < maxTime; t = +(t + step).toFixed(1)) {
    const high = +(t + step).toFixed(1);
    const inBucket = hips.filter((h) => h.time >= t && h.time < high);
    const sold = inBucket.filter((h) => h.price && h.price > 0);
    const avgPrice = sold.length
      ? sold.reduce((s, h) => s + h.price, 0) / sold.length
      : 0;
    const medPrice = sold.length
      ? median(sold.map((h) => h.price))
      : 0;

    buckets.push({
      label: `${t.toFixed(1)}-${high.toFixed(1)}s`,
      count: inBucket.length,
      sold: sold.length,
      avgPrice,
      medPrice,
    });
  }

  const filteredBuckets = buckets.filter((b) => b.count > 0);

  return (
    <div className="rounded-xl border border-gray-100 bg-white p-5 shadow-[0_1px_3px_rgba(0,0,0,0.04)]">
      <h3 className="text-sm font-semibold text-gray-900 mb-4">{title}</h3>
      <ResponsiveContainer width="100%" height={280}>
        <BarChart
          data={filteredBuckets}
          margin={{ top: 5, right: 10, left: 10, bottom: 5 }}
        >
          <CartesianGrid strokeDasharray="3 3" stroke="#f3f4f6" />
          <XAxis
            dataKey="label"
            tick={{ fill: "#6b7280", fontSize: 10 }}
            axisLine={{ stroke: "#e5e7eb" }}
            tickLine={false}
          />
          <YAxis
            yAxisId="left"
            tick={{ fill: "#6b7280", fontSize: 11 }}
            axisLine={{ stroke: "#e5e7eb" }}
            tickLine={false}
          />
          <YAxis
            yAxisId="right"
            orientation="right"
            tickFormatter={(v) => formatCompact(v)}
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
            formatter={(val, name) =>
              name === "Median Price" || name === "Avg Price"
                ? formatCurrency(val)
                : val
            }
          />
          <Legend iconSize={8} wrapperStyle={{ fontSize: 11, color: "#6b7280" }} />
          <Bar
            yAxisId="left"
            dataKey="count"
            name="Horses"
            fill="#93c5fd"
            radius={[4, 4, 0, 0]}
          />
          <Bar
            yAxisId="right"
            dataKey="medPrice"
            name="Median Price"
            fill="#16a34a"
            radius={[4, 4, 0, 0]}
          />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
