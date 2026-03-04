import { useState, useEffect, useMemo } from "react";
import { Link } from "react-router-dom";
import { SALE_CATALOG } from "../lib/api";
import LoadingSpinner from "../components/LoadingSpinner";
import ErrorBanner from "../components/ErrorBanner";
import StatCard from "../components/StatCard";
import { formatNumber, formatBreezeTime } from "../lib/format";

/* ── Helpers ──────────────────────────────────────────────── */

function median(arr) {
  if (!arr.length) return 0;
  const sorted = [...arr].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
}

function avg(arr) {
  if (!arr.length) return 0;
  return arr.reduce((s, v) => s + v, 0) / arr.length;
}

const analyticsSales = Object.entries(SALE_CATALOG)
  .filter(([, meta]) => meta.hasData)
  .sort(([, a], [, b]) => b.year - a.year || b.month - a.month);

function saleName(key) {
  const meta = SALE_CATALOG[key];
  if (!meta) return key;
  const month = meta.month === 3 ? "March" : meta.month === 4 ? "Spring" : "June";
  return `${month} ${meta.year}`;
}

/* ── Main Page ────────────────────────────────────────────── */

export default function VendorSireAnalytics() {
  const [activeTab, setActiveTab] = useState("vendor");
  const [selectedSaleKey, setSelectedSaleKey] = useState("all");
  const [allSaleData, setAllSaleData] = useState({});
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);

    async function loadAll() {
      const results = {};
      for (const [key] of analyticsSales) {
        try {
          const res = await fetch(
            `/.netlify/functions/sale-data?sale=${encodeURIComponent(key)}`
          );
          if (res.ok) {
            const data = await res.json();
            if (data && data.hips) results[key] = data.hips;
          }
        } catch {
          // Skip failed sales
        }
      }
      if (!cancelled) {
        setAllSaleData(results);
        setLoading(false);
      }
    }

    loadAll();
    return () => { cancelled = true; };
  }, []);

  // Normalize all hips with times
  const allHips = useMemo(() => {
    const hips = [];
    for (const [saleKey, rawHips] of Object.entries(allSaleData)) {
      const meta = SALE_CATALOG[saleKey];
      for (const h of rawHips) {
        const time = h.under_tack_time ? parseFloat(h.under_tack_time) : null;
        const distance = h.under_tack_distance ? h.under_tack_distance.trim() : null;
        if (!time || !distance) continue;

        hips.push({
          saleKey,
          hip: h.hip_number,
          time,
          distance,
          sire: h.sire || "Unknown",
          consignor: h.consignor || "Unknown",
          price: h.sale_price || null,
          status: (h.sale_status || "pending").toLowerCase(),
          horseName: h.horse_name || null,
          year: meta?.year || null,
          saleName: saleName(saleKey),
        });
      }
    }
    return hips;
  }, [allSaleData]);

  // Filter by sale
  const filtered = useMemo(() => {
    if (selectedSaleKey === "all") return allHips;
    return allHips.filter((h) => h.saleKey === selectedSaleKey);
  }, [allHips, selectedSaleKey]);

  // Global benchmarks (overall median/avg by distance)
  const benchmarks = useMemo(() => {
    const eighthTimes = filtered.filter((h) => h.distance === "1/8").map((h) => h.time);
    const quarterTimes = filtered.filter((h) => h.distance === "1/4").map((h) => h.time);
    return {
      eighth: { avg: avg(eighthTimes), median: median(eighthTimes), count: eighthTimes.length },
      quarter: { avg: avg(quarterTimes), median: median(quarterTimes), count: quarterTimes.length },
    };
  }, [filtered]);

  // Aggregate by vendor (consignor)
  const vendorStats = useMemo(() => {
    return buildGroupStats(filtered, (h) => h.consignor);
  }, [filtered]);

  // Aggregate by sire
  const sireStats = useMemo(() => {
    return buildGroupStats(filtered, (h) => h.sire);
  }, [filtered]);

  const TABS = [
    { key: "vendor", label: "Vendor Benchmarks" },
    { key: "sire", label: "Sire Benchmarks" },
    { key: "insights", label: "Faster Than Benchmark" },
  ];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-gray-900 tracking-tight">
            Vendor & Sire Benchmark Times
          </h1>
          <p className="text-sm text-gray-500 mt-1">
            Average and median breeze times by vendor and sire, with faster-than-benchmark insights
          </p>
        </div>
        <select
          value={selectedSaleKey}
          onChange={(e) => setSelectedSaleKey(e.target.value)}
          className="bg-white border border-gray-200 rounded-lg px-3 py-2 text-sm text-gray-700 focus:outline-none focus:border-brand-400 focus:ring-2 focus:ring-brand-100"
        >
          <option value="all">All Sales</option>
          {analyticsSales.map(([key]) => (
            <option key={key} value={key}>{saleName(key)}</option>
          ))}
        </select>
      </div>

      {loading && <LoadingSpinner message="Loading breeze time data..." />}

      {!loading && allHips.length === 0 && (
        <ErrorBanner message="No breeze time data available yet." />
      )}

      {!loading && allHips.length > 0 && (
        <>
          {/* Global benchmark cards */}
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
            <StatCard label="Total Timed" value={formatNumber(filtered.length)} />
            <StatCard
              label="1/8 Avg"
              value={benchmarks.eighth.count ? formatBreezeTime(benchmarks.eighth.avg) : "—"}
            />
            <StatCard
              label="1/8 Median"
              value={benchmarks.eighth.count ? formatBreezeTime(benchmarks.eighth.median) : "—"}
              accent
            />
            <StatCard
              label="1/4 Avg"
              value={benchmarks.quarter.count ? formatBreezeTime(benchmarks.quarter.avg) : "—"}
            />
            <StatCard
              label="1/4 Median"
              value={benchmarks.quarter.count ? formatBreezeTime(benchmarks.quarter.median) : "—"}
              accent
            />
            <StatCard
              label="Unique Sires"
              value={formatNumber(sireStats.length)}
            />
          </div>

          {/* Tab bar */}
          <div className="flex gap-1 border-b border-gray-200">
            {TABS.map((tab) => (
              <button
                key={tab.key}
                onClick={() => setActiveTab(tab.key)}
                className={`px-4 py-2.5 text-sm font-medium transition-colors border-b-2 -mb-px ${
                  activeTab === tab.key
                    ? "border-brand-600 text-brand-700"
                    : "border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300"
                }`}
              >
                {tab.label}
              </button>
            ))}
          </div>

          {/* Tab panels */}
          {activeTab === "vendor" && (
            <BenchmarkTable
              data={vendorStats}
              groupLabel="Vendor"
              benchmarks={benchmarks}
            />
          )}
          {activeTab === "sire" && (
            <BenchmarkTable
              data={sireStats}
              groupLabel="Sire"
              benchmarks={benchmarks}
            />
          )}
          {activeTab === "insights" && (
            <InsightsPanel
              vendorStats={vendorStats}
              sireStats={sireStats}
              benchmarks={benchmarks}
              hips={filtered}
            />
          )}
        </>
      )}
    </div>
  );
}

/* ── Build group stats (used for both vendor and sire) ──── */

function buildGroupStats(hips, groupFn) {
  const map = {};
  for (const h of hips) {
    const key = groupFn(h);
    if (!map[key]) {
      map[key] = { name: key, eighthTimes: [], quarterTimes: [], hips: [] };
    }
    map[key].hips.push(h);
    if (h.distance === "1/8") map[key].eighthTimes.push(h.time);
    else if (h.distance === "1/4") map[key].quarterTimes.push(h.time);
  }

  return Object.values(map)
    .map((g) => ({
      name: g.name,
      totalCount: g.hips.length,
      eighthCount: g.eighthTimes.length,
      eighthAvg: avg(g.eighthTimes),
      eighthMedian: median(g.eighthTimes),
      eighthFastest: g.eighthTimes.length ? Math.min(...g.eighthTimes) : null,
      quarterCount: g.quarterTimes.length,
      quarterAvg: avg(g.quarterTimes),
      quarterMedian: median(g.quarterTimes),
      quarterFastest: g.quarterTimes.length ? Math.min(...g.quarterTimes) : null,
      hips: g.hips,
    }))
    .sort((a, b) => b.totalCount - a.totalCount);
}

/* ── Benchmark Table Component ────────────────────────────── */

function BenchmarkTable({ data, groupLabel, benchmarks }) {
  const [sortKey, setSortKey] = useState("totalCount");
  const [sortDir, setSortDir] = useState("desc");
  const [filter, setFilter] = useState("");
  const [minCount, setMinCount] = useState(3);
  const [page, setPage] = useState(0);
  const PER_PAGE = 30;

  function handleSort(key) {
    if (sortKey === key) setSortDir(sortDir === "asc" ? "desc" : "asc");
    else { setSortKey(key); setSortDir(key === "name" ? "asc" : "desc"); }
    setPage(0);
  }

  const filtered_ = useMemo(() => {
    let result = data;
    if (filter) {
      result = result.filter((d) => d.name.toLowerCase().includes(filter.toLowerCase()));
    }
    if (minCount > 0) {
      result = result.filter((d) => d.totalCount >= minCount);
    }
    return [...result].sort((a, b) => {
      let va = a[sortKey];
      let vb = b[sortKey];
      if (typeof va === "string") { va = va.toLowerCase(); vb = vb.toLowerCase(); }
      if (va == null || va === 0) va = sortDir === "asc" ? Infinity : -Infinity;
      if (vb == null || vb === 0) vb = sortDir === "asc" ? Infinity : -Infinity;
      return sortDir === "asc" ? (va < vb ? -1 : va > vb ? 1 : 0) : (va > vb ? -1 : va < vb ? 1 : 0);
    });
  }, [data, filter, minCount, sortKey, sortDir]);

  const pageData = filtered_.slice(page * PER_PAGE, (page + 1) * PER_PAGE);
  const totalPages = Math.ceil(filtered_.length / PER_PAGE);

  const cols = [
    { key: "name", label: groupLabel, align: "left" },
    { key: "totalCount", label: "Total", align: "center" },
    { key: "eighthCount", label: "1/8 #", align: "center" },
    { key: "eighthAvg", label: "1/8 Avg", align: "right" },
    { key: "eighthMedian", label: "1/8 Med", align: "right" },
    { key: "eighthFastest", label: "1/8 Fast", align: "right" },
    { key: "quarterCount", label: "1/4 #", align: "center" },
    { key: "quarterAvg", label: "1/4 Avg", align: "right" },
    { key: "quarterMedian", label: "1/4 Med", align: "right" },
    { key: "quarterFastest", label: "1/4 Fast", align: "right" },
  ];

  return (
    <div className="space-y-4">
      {/* Filters */}
      <div className="flex flex-wrap items-center gap-3">
        <input
          type="text"
          value={filter}
          onChange={(e) => { setFilter(e.target.value); setPage(0); }}
          placeholder={`Search ${groupLabel.toLowerCase()}s...`}
          className="flex-1 max-w-sm bg-white border border-gray-200 rounded-lg px-3 py-2 text-sm text-gray-900 placeholder:text-gray-400 focus:outline-none focus:border-brand-400 focus:ring-2 focus:ring-brand-100 transition-shadow"
        />
        <label className="flex items-center gap-2 text-sm text-gray-600">
          Min runners:
          <select
            value={minCount}
            onChange={(e) => { setMinCount(Number(e.target.value)); setPage(0); }}
            className="bg-white border border-gray-200 rounded-lg px-2 py-1.5 text-sm focus:outline-none focus:border-brand-400"
          >
            {[1, 2, 3, 5, 10, 20, 50].map((n) => (
              <option key={n} value={n}>{n}+</option>
            ))}
          </select>
        </label>
        <span className="text-xs text-gray-400">{filtered_.length} {groupLabel.toLowerCase()}s</span>
      </div>

      {/* Benchmark reference */}
      <div className="rounded-lg border border-blue-100 bg-blue-50/50 px-4 py-3 text-xs text-blue-700">
        <strong>Benchmark reference:</strong>{" "}
        1/8 mile — Avg: {benchmarks.eighth.count ? formatBreezeTime(benchmarks.eighth.avg) : "—"},{" "}
        Median: {benchmarks.eighth.count ? formatBreezeTime(benchmarks.eighth.median) : "—"}
        {" | "}
        1/4 mile — Avg: {benchmarks.quarter.count ? formatBreezeTime(benchmarks.quarter.avg) : "—"},{" "}
        Median: {benchmarks.quarter.count ? formatBreezeTime(benchmarks.quarter.median) : "—"}
      </div>

      {/* Table */}
      <div className="overflow-x-auto rounded-xl border border-gray-100 bg-white shadow-[0_1px_3px_rgba(0,0,0,0.04)]">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-100">
              <th className="px-3 py-3 text-left text-[11px] font-medium uppercase tracking-wider text-gray-400">#</th>
              {cols.map((c) => (
                <th
                  key={c.key}
                  onClick={() => handleSort(c.key)}
                  className={`px-3 py-3 text-[11px] font-medium uppercase tracking-wider text-gray-400 cursor-pointer hover:text-gray-700 select-none ${
                    c.align === "left" ? "text-left" : c.align === "center" ? "text-center" : "text-right"
                  }`}
                >
                  <span className="inline-flex items-center gap-1">
                    {c.label}
                    {sortKey === c.key && (
                      <span className="text-brand-600">{sortDir === "asc" ? "↑" : "↓"}</span>
                    )}
                  </span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-50">
            {pageData.map((d, i) => {
              const eighthFaster = d.eighthAvg > 0 && benchmarks.eighth.avg > 0 && d.eighthAvg < benchmarks.eighth.avg;
              const quarterFaster = d.quarterAvg > 0 && benchmarks.quarter.avg > 0 && d.quarterAvg < benchmarks.quarter.avg;

              return (
                <tr key={d.name} className="table-row-hover">
                  <td className="px-3 py-2.5 font-mono text-gray-400 text-xs">
                    {page * PER_PAGE + i + 1}
                  </td>
                  <td className="px-3 py-2.5 font-medium text-gray-900 max-w-[220px]">
                    <div className="truncate">{d.name}</div>
                  </td>
                  <td className="px-3 py-2.5 text-center font-mono text-gray-600">{d.totalCount}</td>
                  <td className="px-3 py-2.5 text-center font-mono text-gray-500 text-xs">
                    {d.eighthCount || "—"}
                  </td>
                  <td className={`px-3 py-2.5 text-right font-mono font-semibold ${eighthFaster ? "text-emerald-600" : "text-gray-700"}`}>
                    {d.eighthCount ? formatBreezeTime(d.eighthAvg) : "—"}
                  </td>
                  <td className={`px-3 py-2.5 text-right font-mono ${eighthFaster ? "text-emerald-600" : "text-gray-500"}`}>
                    {d.eighthCount ? formatBreezeTime(d.eighthMedian) : "—"}
                  </td>
                  <td className="px-3 py-2.5 text-right font-mono text-brand-600 font-semibold">
                    {d.eighthFastest != null ? formatBreezeTime(d.eighthFastest) : "—"}
                  </td>
                  <td className="px-3 py-2.5 text-center font-mono text-gray-500 text-xs">
                    {d.quarterCount || "—"}
                  </td>
                  <td className={`px-3 py-2.5 text-right font-mono font-semibold ${quarterFaster ? "text-emerald-600" : "text-gray-700"}`}>
                    {d.quarterCount ? formatBreezeTime(d.quarterAvg) : "—"}
                  </td>
                  <td className={`px-3 py-2.5 text-right font-mono ${quarterFaster ? "text-emerald-600" : "text-gray-500"}`}>
                    {d.quarterCount ? formatBreezeTime(d.quarterMedian) : "—"}
                  </td>
                  <td className="px-3 py-2.5 text-right font-mono text-brand-600 font-semibold">
                    {d.quarterFastest != null ? formatBreezeTime(d.quarterFastest) : "—"}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {pageData.length === 0 && (
          <div className="text-center py-12 text-gray-400">No results match your filters</div>
        )}
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between">
          <span className="text-xs text-gray-400">
            Page {page + 1} of {totalPages} ({formatNumber(filtered_.length)} {groupLabel.toLowerCase()}s)
          </span>
          <div className="flex gap-1">
            <PaginationBtn onClick={() => setPage(0)} disabled={page === 0}>First</PaginationBtn>
            <PaginationBtn onClick={() => setPage((p) => p - 1)} disabled={page === 0}>Prev</PaginationBtn>
            <PaginationBtn onClick={() => setPage((p) => p + 1)} disabled={page >= totalPages - 1}>Next</PaginationBtn>
            <PaginationBtn onClick={() => setPage(totalPages - 1)} disabled={page >= totalPages - 1}>Last</PaginationBtn>
          </div>
        </div>
      )}
    </div>
  );
}

/* ── Insights Panel ───────────────────────────────────────── */

function InsightsPanel({ vendorStats, sireStats, benchmarks, hips }) {
  // Vendors with avg faster than benchmark (min 5 runners)
  const fastVendorsEighth = useMemo(() => {
    return vendorStats
      .filter((v) => v.eighthCount >= 5 && v.eighthAvg > 0 && benchmarks.eighth.avg > 0 && v.eighthAvg < benchmarks.eighth.avg)
      .sort((a, b) => a.eighthAvg - b.eighthAvg);
  }, [vendorStats, benchmarks]);

  const fastVendorsQuarter = useMemo(() => {
    return vendorStats
      .filter((v) => v.quarterCount >= 5 && v.quarterAvg > 0 && benchmarks.quarter.avg > 0 && v.quarterAvg < benchmarks.quarter.avg)
      .sort((a, b) => a.quarterAvg - b.quarterAvg);
  }, [vendorStats, benchmarks]);

  const fastSiresEighth = useMemo(() => {
    return sireStats
      .filter((s) => s.eighthCount >= 5 && s.eighthAvg > 0 && benchmarks.eighth.avg > 0 && s.eighthAvg < benchmarks.eighth.avg)
      .sort((a, b) => a.eighthAvg - b.eighthAvg);
  }, [sireStats, benchmarks]);

  const fastSiresQuarter = useMemo(() => {
    return sireStats
      .filter((s) => s.quarterCount >= 5 && s.quarterAvg > 0 && benchmarks.quarter.avg > 0 && s.quarterAvg < benchmarks.quarter.avg)
      .sort((a, b) => a.quarterAvg - b.quarterAvg);
  }, [sireStats, benchmarks]);

  // Individual runners faster than benchmark median
  const fastRunners = useMemo(() => {
    return hips
      .filter((h) => {
        const bm = h.distance === "1/8" ? benchmarks.eighth : benchmarks.quarter;
        return bm.median > 0 && h.time < bm.median;
      })
      .sort((a, b) => {
        // Sort by how much faster than benchmark
        const aDiff = a.time - (a.distance === "1/8" ? benchmarks.eighth.median : benchmarks.quarter.median);
        const bDiff = b.time - (b.distance === "1/8" ? benchmarks.eighth.median : benchmarks.quarter.median);
        return aDiff - bDiff;
      })
      .slice(0, 50);
  }, [hips, benchmarks]);

  return (
    <div className="space-y-6">
      {/* Fast Vendors */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <InsightCard
          title="Vendors Faster Than Benchmark (1/8)"
          subtitle={`Avg benchmark: ${formatBreezeTime(benchmarks.eighth.avg)} — min 5 runners`}
          items={fastVendorsEighth}
          benchmarkAvg={benchmarks.eighth.avg}
          distKey="eighth"
        />
        <InsightCard
          title="Vendors Faster Than Benchmark (1/4)"
          subtitle={`Avg benchmark: ${formatBreezeTime(benchmarks.quarter.avg)} — min 5 runners`}
          items={fastVendorsQuarter}
          benchmarkAvg={benchmarks.quarter.avg}
          distKey="quarter"
        />
      </div>

      {/* Fast Sires */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <InsightCard
          title="Sires Faster Than Benchmark (1/8)"
          subtitle={`Avg benchmark: ${formatBreezeTime(benchmarks.eighth.avg)} — min 5 runners`}
          items={fastSiresEighth}
          benchmarkAvg={benchmarks.eighth.avg}
          distKey="eighth"
        />
        <InsightCard
          title="Sires Faster Than Benchmark (1/4)"
          subtitle={`Avg benchmark: ${formatBreezeTime(benchmarks.quarter.avg)} — min 5 runners`}
          items={fastSiresQuarter}
          benchmarkAvg={benchmarks.quarter.avg}
          distKey="quarter"
        />
      </div>

      {/* Individual fast runners */}
      <div className="rounded-xl border border-gray-100 bg-white p-5 shadow-[0_1px_3px_rgba(0,0,0,0.04)]">
        <h3 className="text-sm font-semibold text-gray-900 mb-1">
          Top 50 Fastest Runners vs Benchmark Median
        </h3>
        <p className="text-xs text-gray-500 mb-4">
          Individual horses that breezed faster than the overall median for their distance
        </p>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-100">
                <th className="px-3 py-2 text-left text-[11px] font-medium uppercase tracking-wider text-gray-400">#</th>
                <th className="px-3 py-2 text-left text-[11px] font-medium uppercase tracking-wider text-gray-400">Hip</th>
                <th className="px-3 py-2 text-left text-[11px] font-medium uppercase tracking-wider text-gray-400">Horse</th>
                <th className="px-3 py-2 text-left text-[11px] font-medium uppercase tracking-wider text-gray-400">Sire</th>
                <th className="px-3 py-2 text-left text-[11px] font-medium uppercase tracking-wider text-gray-400">Vendor</th>
                <th className="px-3 py-2 text-center text-[11px] font-medium uppercase tracking-wider text-gray-400">Dist</th>
                <th className="px-3 py-2 text-right text-[11px] font-medium uppercase tracking-wider text-gray-400">Time</th>
                <th className="px-3 py-2 text-right text-[11px] font-medium uppercase tracking-wider text-gray-400">Benchmark</th>
                <th className="px-3 py-2 text-right text-[11px] font-medium uppercase tracking-wider text-gray-400">Diff</th>
                <th className="px-3 py-2 text-left text-[11px] font-medium uppercase tracking-wider text-gray-400">Sale</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50">
              {fastRunners.map((h, i) => {
                const bm = h.distance === "1/8" ? benchmarks.eighth.median : benchmarks.quarter.median;
                const diff = h.time - bm;
                return (
                  <tr key={`${h.saleKey}-${h.hip}-${i}`} className="table-row-hover">
                    <td className="px-3 py-2 font-mono text-gray-400 text-xs">{i + 1}</td>
                    <td className="px-3 py-2 font-mono font-semibold text-brand-600">
                      <Link to={`/sale/${h.saleKey}/hip/${h.hip}`} className="hover:underline">
                        #{h.hip}
                      </Link>
                    </td>
                    <td className="px-3 py-2 text-gray-900 text-xs max-w-[140px] truncate">
                      {h.horseName || "—"}
                    </td>
                    <td className="px-3 py-2 text-gray-700 text-xs max-w-[120px] truncate">{h.sire}</td>
                    <td className="px-3 py-2 text-gray-700 text-xs max-w-[140px] truncate">{h.consignor}</td>
                    <td className="px-3 py-2 text-center text-gray-500">{h.distance}</td>
                    <td className="px-3 py-2 text-right font-mono font-semibold text-gray-900">
                      {formatBreezeTime(h.time)}
                    </td>
                    <td className="px-3 py-2 text-right font-mono text-gray-400">
                      {formatBreezeTime(bm)}
                    </td>
                    <td className="px-3 py-2 text-right font-mono font-semibold text-emerald-600">
                      {diff.toFixed(2)}s
                    </td>
                    <td className="px-3 py-2 text-gray-500 text-xs">{h.saleName}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

/* ── Insight Card ─────────────────────────────────────────── */

function InsightCard({ title, subtitle, items, benchmarkAvg, distKey }) {
  if (items.length === 0) {
    return (
      <div className="rounded-xl border border-gray-100 bg-white p-5 shadow-[0_1px_3px_rgba(0,0,0,0.04)]">
        <h3 className="text-sm font-semibold text-gray-900 mb-1">{title}</h3>
        <p className="text-xs text-gray-500">{subtitle}</p>
        <p className="text-gray-400 text-sm mt-6 text-center">No data available</p>
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-gray-100 bg-white p-5 shadow-[0_1px_3px_rgba(0,0,0,0.04)]">
      <h3 className="text-sm font-semibold text-gray-900 mb-1">{title}</h3>
      <p className="text-xs text-gray-500 mb-4">{subtitle}</p>
      <div className="space-y-2">
        {items.slice(0, 15).map((item, i) => {
          const itemAvg = distKey === "eighth" ? item.eighthAvg : item.quarterAvg;
          const itemCount = distKey === "eighth" ? item.eighthCount : item.quarterCount;
          const diff = itemAvg - benchmarkAvg;
          const pctFaster = ((benchmarkAvg - itemAvg) / benchmarkAvg * 100).toFixed(1);

          return (
            <div key={item.name} className="flex items-center gap-3 py-1.5 border-b border-gray-50 last:border-0">
              <span className="w-5 text-right font-mono text-gray-400 text-xs">{i + 1}</span>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-gray-900 truncate">{item.name}</p>
                <p className="text-[11px] text-gray-400">{itemCount} runners</p>
              </div>
              <div className="text-right">
                <p className="text-sm font-mono font-semibold text-emerald-600">
                  {formatBreezeTime(itemAvg)}
                </p>
                <p className="text-[11px] font-mono text-emerald-500">
                  {diff.toFixed(2)}s ({pctFaster}% faster)
                </p>
              </div>
            </div>
          );
        })}
      </div>
      {items.length > 15 && (
        <p className="text-xs text-gray-400 mt-3 text-center">
          + {items.length - 15} more
        </p>
      )}
    </div>
  );
}

/* ── Shared ───────────────────────────────────────────────── */

function PaginationBtn({ onClick, disabled, children }) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className={`px-3 py-1.5 text-xs rounded-lg border transition-colors ${
        disabled
          ? "border-gray-100 text-gray-300 cursor-not-allowed"
          : "border-gray-200 text-gray-600 hover:bg-gray-50 hover:text-gray-900"
      }`}
    >
      {children}
    </button>
  );
}
