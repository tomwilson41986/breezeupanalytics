import { useState, useEffect, useMemo } from "react";
import { Link } from "react-router-dom";
import { SALE_CATALOG } from "../lib/api";
import { useHistoricRecords } from "../hooks/useHistoricData";
import LoadingSpinner from "../components/LoadingSpinner";
import ErrorBanner from "../components/ErrorBanner";
import StatCard from "../components/StatCard";
import {
  formatNumber,
  formatCurrency,
  formatCompact,
  formatBreezeTime,
  formatPercent,
} from "../lib/format";
import {
  ScatterChart,
  Scatter,
  XAxis,
  YAxis,
  ZAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
  Cell,
  BarChart,
  Bar,
} from "recharts";

const analyticsSales = Object.entries(SALE_CATALOG)
  .filter(([, meta]) => meta.hasData)
  .sort(([, a], [, b]) => b.year - a.year || b.month - a.month);

/** Map sale name + year to s3Key */
function toSaleKey(saleName, year) {
  const map = {
    "OBS March Sale": "march",
    "OBS Spring Sale": "spring",
    "OBS June Sale": "june",
  };
  const season = map[saleName];
  if (!season) return null;
  return `obs_${season}_${year}`;
}

/** Get performance level */
function performanceLevel(r) {
  if (r.g1Winner) return "g1";
  if (r.gradedStakesWinner) return "gsw";
  if (r.stakesWinner) return "sw";
  if (r.winner) return "winner";
  if (r.runner) return "non-winner";
  return "unraced";
}

const LEVEL_CONFIG = {
  g1: { label: "G1 Winner", color: "#ef4444", order: 5 },
  gsw: { label: "Graded SW", color: "#8b5cf6", order: 4 },
  sw: { label: "Stakes Winner", color: "#3b82f6", order: 3 },
  winner: { label: "Winner", color: "#22c55e", order: 2 },
  "non-winner": { label: "Non-Winner", color: "#f59e0b", order: 1 },
  unraced: { label: "Unraced", color: "#d1d5db", order: 0 },
};

function saleName(key) {
  const meta = SALE_CATALOG[key];
  if (!meta) return key;
  const month =
    meta.month === 3 ? "March" : meta.month === 4 ? "Spring" : "June";
  return `${month} ${meta.year}`;
}

export default function BreezePerformance() {
  const [distanceFilter, setDistanceFilter] = useState("all");
  const [levelFilter, setLevelFilter] = useState("all");
  const [selectedSaleKey, setSelectedSaleKey] = useState("all");
  const [search, setSearch] = useState("");

  // Load S3 sale data (has breeze times)
  const [allSaleData, setAllSaleData] = useState({});
  const [loadingSales, setLoadingSales] = useState(true);

  // Load historic records (has performance outcomes)
  const {
    records: historicRecords,
    loading: loadingRecords,
    load: loadRecords,
  } = useHistoricRecords();

  useEffect(() => {
    loadRecords();
  }, []);

  useEffect(() => {
    let cancelled = false;
    setLoadingSales(true);

    async function loadAll() {
      const entries = await Promise.all(
        analyticsSales.map(async ([key]) => {
          try {
            const res = await fetch(
              `/.netlify/functions/sale-data?sale=${encodeURIComponent(key)}`
            );
            if (res.ok) {
              const data = await res.json();
              if (data && data.hips) return [key, data.hips];
            }
          } catch {
            // Skip failed sales
          }
          return null;
        })
      );
      if (!cancelled) {
        const results = {};
        for (const entry of entries) {
          if (entry) results[entry[0]] = entry[1];
        }
        setAllSaleData(results);
        setLoadingSales(false);
      }
    }

    loadAll();
    return () => {
      cancelled = true;
    };
  }, []);

  const loading = loadingSales || loadingRecords;

  // Build performance lookup from historic records: saleKey+hip -> performance level
  const performanceLookup = useMemo(() => {
    if (!historicRecords) return {};
    const lookup = {};
    for (const r of historicRecords) {
      const saleKey = toSaleKey(r.sale, r.year);
      if (!saleKey) continue;
      const key = `${saleKey}:${r.hip}`;
      lookup[key] = {
        level: performanceLevel(r),
        name: r.name,
        runner: r.runner,
        winner: r.winner,
        stakesWinner: r.stakesWinner,
        gradedStakesWinner: r.gradedStakesWinner,
        g1Winner: r.g1Winner,
      };
    }
    return lookup;
  }, [historicRecords]);

  // Merge S3 breeze data with performance outcomes
  const mergedHips = useMemo(() => {
    const hips = [];
    for (const [saleKey, rawHips] of Object.entries(allSaleData)) {
      for (const h of rawHips) {
        const time = h.under_tack_time ? parseFloat(h.under_tack_time) : null;
        const distance = h.under_tack_distance
          ? h.under_tack_distance.trim()
          : null;
        if (!time || !distance) continue;

        const lookupKey = `${saleKey}:${h.hip_number}`;
        const perf = performanceLookup[lookupKey] || { level: "unraced" };

        hips.push({
          saleKey,
          hip: h.hip_number,
          time,
          distance,
          price: h.sale_price || null,
          status: (h.sale_status || "pending").toLowerCase(),
          sire: h.sire || "Unknown",
          dam: h.dam || "Unknown",
          sex: h.sex || "\u2014",
          consignor: h.consignor || "\u2014",
          horseName: h.horse_name || perf.name || null,
          level: perf.level,
          levelConfig: LEVEL_CONFIG[perf.level],
        });
      }
    }
    // Sort so elite performers render on top (last painted = on top in SVG)
    return hips.sort(
      (a, b) => (a.levelConfig?.order || 0) - (b.levelConfig?.order || 0)
    );
  }, [allSaleData, performanceLookup]);

  // Apply filters
  const filtered = useMemo(() => {
    let result = mergedHips;

    if (selectedSaleKey !== "all") {
      result = result.filter((h) => h.saleKey === selectedSaleKey);
    }
    if (distanceFilter !== "all") {
      result = result.filter((h) => h.distance === distanceFilter);
    }
    if (levelFilter !== "all") {
      if (levelFilter === "performers") {
        result = result.filter(
          (h) => h.level !== "unraced" && h.level !== "non-winner"
        );
      } else {
        result = result.filter((h) => h.level === levelFilter);
      }
    }
    if (search.trim()) {
      const q = search.toLowerCase().trim();
      result = result.filter(
        (h) =>
          (h.horseName && h.horseName.toLowerCase().includes(q)) ||
          (h.sire && h.sire.toLowerCase().includes(q)) ||
          (h.dam && h.dam.toLowerCase().includes(q)) ||
          (h.consignor && h.consignor.toLowerCase().includes(q)) ||
          String(h.hip).includes(q)
      );
    }

    return result;
  }, [mergedHips, selectedSaleKey, distanceFilter, levelFilter, search]);

  // Split by distance
  const eighthHips = useMemo(
    () => filtered.filter((h) => h.distance === "1/8"),
    [filtered]
  );
  const quarterHips = useMemo(
    () => filtered.filter((h) => h.distance === "1/4"),
    [filtered]
  );

  // Stats
  const levelCounts = useMemo(() => {
    const counts = {};
    for (const h of filtered) {
      counts[h.level] = (counts[h.level] || 0) + 1;
    }
    return counts;
  }, [filtered]);

  const availableDistances = useMemo(() => {
    const set = new Set(mergedHips.map((h) => h.distance));
    return [...set].sort();
  }, [mergedHips]);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-xl sm:text-2xl font-semibold text-gray-900 tracking-tight">
          Breeze Performance
        </h1>
        <p className="text-sm text-gray-500 mt-1">
          Under-tack breeze times colored by racing performance outcome —
          identify patterns among elite performers
        </p>
      </div>

      {loading && (
        <LoadingSpinner message="Loading breeze and performance data..." />
      )}

      {!loading && mergedHips.length === 0 && (
        <ErrorBanner message="No merged breeze + performance data available. This tool requires sales with both under-tack data (S3) and historic performance outcomes." />
      )}

      {!loading && mergedHips.length > 0 && (
        <>
          {/* Legend */}
          <div className="rounded-xl border border-gray-100 bg-white p-3 sm:p-4 shadow-[0_1px_3px_rgba(0,0,0,0.04)]">
            <div className="flex flex-wrap items-center gap-3 sm:gap-4">
              <span className="text-xs font-medium text-gray-500 uppercase tracking-wider">
                Legend:
              </span>
              {Object.entries(LEVEL_CONFIG)
                .sort(([, a], [, b]) => b.order - a.order)
                .map(([key, cfg]) => (
                  <button
                    key={key}
                    onClick={() =>
                      setLevelFilter(levelFilter === key ? "all" : key)
                    }
                    className={`flex items-center gap-1.5 text-xs transition-opacity ${
                      levelFilter !== "all" && levelFilter !== key
                        ? "opacity-40"
                        : ""
                    }`}
                  >
                    <span
                      className="w-3 h-3 rounded-full border border-white shadow-sm"
                      style={{ backgroundColor: cfg.color }}
                    />
                    <span className="text-gray-600">
                      {cfg.label} ({levelCounts[key] || 0})
                    </span>
                  </button>
                ))}
            </div>
          </div>

          {/* Filters */}
          <div className="flex flex-col sm:flex-row flex-wrap items-stretch sm:items-center gap-2 sm:gap-3">
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
            <select
              value={levelFilter}
              onChange={(e) => setLevelFilter(e.target.value)}
              className="bg-white border border-gray-200 rounded-lg px-3 py-2 text-sm text-gray-700 focus:outline-none focus:border-brand-400 focus:ring-2 focus:ring-brand-100"
            >
              <option value="all">All Status</option>
              <option value="performers">Performers Only</option>
              {Object.entries(LEVEL_CONFIG)
                .sort(([, a], [, b]) => b.order - a.order)
                .map(([key, cfg]) => (
                  <option key={key} value={key}>
                    {cfg.label}
                  </option>
                ))}
            </select>
            <div className="flex-1 min-w-0 sm:min-w-[200px]">
              <input
                type="text"
                placeholder="Search horse, sire, dam..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="w-full bg-white border border-gray-200 rounded-lg px-3 py-2 text-sm text-gray-700 placeholder-gray-400 focus:outline-none focus:border-brand-400 focus:ring-2 focus:ring-brand-100"
              />
            </div>
          </div>

          {/* Summary stats */}
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
            <StatCard
              label="Total Timed"
              value={formatNumber(filtered.length)}
            />
            <StatCard
              label="Winners"
              value={formatNumber(levelCounts["winner"] || 0)}
              sub={
                filtered.length
                  ? formatPercent(
                      ((levelCounts["winner"] || 0) / filtered.length) * 100
                    )
                  : "\u2014"
              }
            />
            <StatCard
              label="Stakes W"
              value={formatNumber(levelCounts["sw"] || 0)}
              accent
            />
            <StatCard
              label="Graded SW"
              value={formatNumber(levelCounts["gsw"] || 0)}
            />
            <StatCard
              label="G1 Winners"
              value={formatNumber(levelCounts["g1"] || 0)}
              accent
            />
            <StatCard
              label="1/8 | 1/4"
              value={`${eighthHips.length} | ${quarterHips.length}`}
            />
          </div>

          {/* Scatter charts by distance */}
          <div className="grid grid-cols-1 gap-4">
            {(distanceFilter === "all" || distanceFilter === "1/8") &&
              eighthHips.length > 0 && (
                <BreezeScatterByPerformance
                  hips={eighthHips}
                  title="1/8 Mile: Breeze Time vs Price by Performance"
                  distance="1/8"
                  minDomain={9}
                />
              )}
            {(distanceFilter === "all" || distanceFilter === "1/4") &&
              quarterHips.length > 0 && (
                <BreezeScatterByPerformance
                  hips={quarterHips}
                  title="1/4 Mile: Breeze Time vs Price by Performance"
                  distance="1/4"
                  minDomain={19}
                />
              )}
          </div>

          {/* Time distribution by performance level */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {eighthHips.length > 0 && (
              <TimeByPerformance
                hips={eighthHips}
                title="1/8 Mile: Avg Time by Performance Level"
                distance="1/8"
              />
            )}
            {quarterHips.length > 0 && (
              <TimeByPerformance
                hips={quarterHips}
                title="1/4 Mile: Avg Time by Performance Level"
                distance="1/4"
              />
            )}
          </div>

          {/* Detailed table of elite performers */}
          <ElitePerformersTable hips={filtered} />
        </>
      )}
    </div>
  );
}

/* ── Scatter chart colored by performance ──────────────────── */

function BreezeScatterByPerformance({ hips, title, minDomain }) {
  // Group by performance level for legend
  const groups = {};
  for (const h of hips) {
    if (!groups[h.level]) groups[h.level] = [];
    groups[h.level].push({
      time: h.time,
      price: h.price || 0,
      label: `Hip #${h.hip} — ${h.horseName || h.sire} (${LEVEL_CONFIG[h.level]?.label})`,
      hip: h.hip,
      saleKey: h.saleKey,
      horseName: h.horseName,
      sire: h.sire,
      level: h.level,
    });
  }

  // Only show groups that have sold horses (price > 0)
  const priceHips = hips.filter((h) => h.price && h.price > 0);

  return (
    <div className="rounded-xl border border-gray-100 bg-white p-4 sm:p-5 shadow-[0_1px_3px_rgba(0,0,0,0.04)]">
      <h3 className="text-sm font-semibold text-gray-900 mb-3 sm:mb-4">{title}</h3>
      <ResponsiveContainer width="100%" height={340}>
        <ScatterChart margin={{ top: 10, right: 20, left: 10, bottom: 10 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#f3f4f6" />
          <XAxis
            dataKey="time"
            name="Time"
            unit="s"
            type="number"
            domain={minDomain != null ? [minDomain, 'auto'] : ['auto', 'auto']}
            tick={{ fill: "#6b7280", fontSize: 11 }}
            axisLine={{ stroke: "#e5e7eb" }}
            tickLine={false}
            label={{
              value: "Breeze Time (seconds)",
              position: "insideBottom",
              offset: -5,
              style: { fill: "#9ca3af", fontSize: 11 },
            }}
          />
          <YAxis
            dataKey="price"
            name="Price"
            type="number"
            tickFormatter={(v) => formatCompact(v)}
            tick={{ fill: "#6b7280", fontSize: 11 }}
            axisLine={{ stroke: "#e5e7eb" }}
            tickLine={false}
            label={{
              value: "Sale Price ($)",
              angle: -90,
              position: "insideLeft",
              style: { fill: "#9ca3af", fontSize: 11 },
            }}
          />
          <ZAxis range={[40, 40]} />
          <Tooltip
            content={<CustomTooltip />}
          />
          <Legend
            iconSize={10}
            wrapperStyle={{ fontSize: 11, color: "#6b7280" }}
          />
          {Object.entries(LEVEL_CONFIG)
            .sort(([, a], [, b]) => a.order - b.order)
            .map(([level, cfg]) => {
              const data = (groups[level] || []).filter((d) => d.price > 0);
              if (data.length === 0) return null;
              return (
                <Scatter
                  key={level}
                  name={cfg.label}
                  data={data}
                  fill={cfg.color}
                  fillOpacity={level === "unraced" ? 0.3 : 0.7}
                  shape={level === "g1" || level === "gsw" ? "star" : "circle"}
                />
              );
            })}
        </ScatterChart>
      </ResponsiveContainer>
      <p className="text-[11px] text-gray-400 mt-2 text-center">
        Showing {formatNumber(priceHips.length)} sold horses with breeze times
      </p>
    </div>
  );
}

function CustomTooltip({ active, payload }) {
  if (!active || !payload || !payload.length) return null;
  const d = payload[0]?.payload;
  if (!d) return null;

  const cfg = LEVEL_CONFIG[d.level];

  return (
    <div className="bg-white border border-gray-200 rounded-lg shadow-lg p-3 text-sm max-w-[260px]">
      <div className="flex items-center gap-2 mb-1">
        <span
          className="w-2.5 h-2.5 rounded-full"
          style={{ backgroundColor: cfg?.color }}
        />
        <span className="font-semibold text-gray-900">
          Hip #{d.hip}
        </span>
        <span className="text-[11px] text-gray-400">
          {cfg?.label}
        </span>
      </div>
      {d.horseName && (
        <p className="text-gray-700 font-medium">{d.horseName}</p>
      )}
      <p className="text-gray-500 text-xs">{d.sire}</p>
      <div className="flex gap-4 mt-1.5 text-xs">
        <span className="text-gray-600">
          Time: <span className="font-mono font-semibold">{d.time?.toFixed(1)}s</span>
        </span>
        <span className="text-gray-600">
          Price: <span className="font-mono font-semibold">{d.price ? formatCurrency(d.price) : "\u2014"}</span>
        </span>
      </div>
    </div>
  );
}

/* ── Average time by performance level ─────────────────────── */

function TimeByPerformance({ hips, title, distance }) {
  const levelStats = {};
  for (const h of hips) {
    if (!levelStats[h.level]) levelStats[h.level] = { times: [], prices: [] };
    levelStats[h.level].times.push(h.time);
    if (h.price) levelStats[h.level].prices.push(h.price);
  }

  const data = Object.entries(LEVEL_CONFIG)
    .sort(([, a], [, b]) => b.order - a.order)
    .filter(([key]) => levelStats[key]?.times.length > 0)
    .map(([key, cfg]) => {
      const times = levelStats[key].times;
      const prices = levelStats[key].prices;
      const avg = times.reduce((s, t) => s + t, 0) / times.length;
      const avgPrice = prices.length
        ? prices.reduce((s, p) => s + p, 0) / prices.length
        : 0;
      return {
        level: cfg.label,
        avgTime: +avg.toFixed(2),
        count: times.length,
        avgPrice,
        color: cfg.color,
      };
    });

  const xMin = distance === "1/4" ? 19 : 9;

  return (
    <div className="rounded-xl border border-gray-100 bg-white p-4 sm:p-5 shadow-[0_1px_3px_rgba(0,0,0,0.04)]">
      <h3 className="text-sm font-semibold text-gray-900 mb-3 sm:mb-4">{title}</h3>
      <ResponsiveContainer width="100%" height={240}>
        <BarChart
          data={data}
          margin={{ top: 5, right: 10, left: 10, bottom: 5 }}
          layout="vertical"
        >
          <CartesianGrid strokeDasharray="3 3" stroke="#f3f4f6" />
          <XAxis
            type="number"
            domain={[xMin, 'auto']}
            tick={{ fill: "#6b7280", fontSize: 11 }}
            axisLine={{ stroke: "#e5e7eb" }}
            tickLine={false}
            unit="s"
          />
          <YAxis
            dataKey="level"
            type="category"
            tick={{ fill: "#6b7280", fontSize: 10 }}
            axisLine={{ stroke: "#e5e7eb" }}
            tickLine={false}
            width={100}
          />
          <Tooltip
            contentStyle={{
              backgroundColor: "#ffffff",
              border: "1px solid #e5e7eb",
              borderRadius: 8,
              fontSize: 12,
              boxShadow: "0 4px 12px rgba(0,0,0,0.08)",
            }}
            formatter={(val, name) => [
              name === "Avg Price" ? formatCurrency(val) : `${val}s`,
              name,
            ]}
          />
          <Bar dataKey="avgTime" name="Avg Time" radius={[0, 4, 4, 0]}>
            {data.map((entry, i) => (
              <Cell key={i} fill={entry.color} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

/* ── Elite Performers Table ────────────────────────────────── */

function ElitePerformersTable({ hips }) {
  const [sortKey, setSortKey] = useState("levelOrder");
  const [sortDir, setSortDir] = useState("desc");
  const [page, setPage] = useState(0);
  const PER_PAGE = 25;

  // Filter to only performers (winners+)
  const performers = useMemo(() => {
    return hips
      .filter(
        (h) =>
          h.level === "winner" ||
          h.level === "sw" ||
          h.level === "gsw" ||
          h.level === "g1"
      )
      .map((h) => ({
        ...h,
        levelOrder: LEVEL_CONFIG[h.level]?.order || 0,
      }));
  }, [hips]);

  const sorted = useMemo(() => {
    return [...performers].sort((a, b) => {
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
  }, [performers, sortKey, sortDir]);

  const pageHips = sorted.slice(page * PER_PAGE, (page + 1) * PER_PAGE);
  const totalPages = Math.ceil(sorted.length / PER_PAGE);

  function handleSort(key) {
    if (sortKey === key) setSortDir(sortDir === "asc" ? "desc" : "asc");
    else {
      setSortKey(key);
      setSortDir(key === "time" ? "asc" : "desc");
    }
    setPage(0);
  }

  if (performers.length === 0) return null;

  const cols = [
    { key: "hip", label: "Hip", align: "left" },
    { key: "horseName", label: "Horse", align: "left" },
    { key: "saleKey", label: "Sale", align: "left" },
    { key: "distance", label: "Dist", align: "center" },
    { key: "time", label: "Time", align: "right" },
    { key: "price", label: "Price", align: "right" },
    { key: "sire", label: "Sire", align: "left" },
    { key: "levelOrder", label: "Status", align: "center" },
  ];

  return (
    <div className="rounded-xl border border-gray-100 bg-white p-4 sm:p-5 shadow-[0_1px_3px_rgba(0,0,0,0.04)]">
      <h3 className="text-sm font-semibold text-gray-900 mb-3 sm:mb-4">
        Performers with Breeze Data ({formatNumber(performers.length)} horses)
      </h3>
      <div className="overflow-x-auto -mx-4 sm:-mx-5 px-4 sm:px-5">
        <table className="w-full text-sm min-w-[700px]">
          <thead>
            <tr className="border-b border-gray-100">
              {cols.map((c) => (
                <th
                  key={c.key}
                  onClick={() => handleSort(c.key)}
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
            {pageHips.map((h, i) => {
              const cfg = LEVEL_CONFIG[h.level];
              return (
                <tr
                  key={`${h.saleKey}-${h.hip}-${i}`}
                  className="table-row-hover"
                >
                  <td className="py-2 px-3 font-mono font-semibold text-brand-600">
                    <Link
                      to={`/sale/${h.saleKey}/hip/${h.hip}`}
                      className="hover:underline"
                    >
                      #{h.hip}
                    </Link>
                  </td>
                  <td className="py-2 px-3 text-gray-900 font-medium max-w-[160px] truncate">
                    {h.horseName ? (
                      <Link
                        to={`/sale/${h.saleKey}/hip/${h.hip}`}
                        className="hover:underline hover:text-brand-600"
                      >
                        {h.horseName}
                      </Link>
                    ) : (
                      <span className="text-gray-400 italic">Unnamed</span>
                    )}
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
                  <td className="py-2 px-3 text-right font-mono text-gray-700">
                    {h.price ? formatCurrency(h.price) : "\u2014"}
                  </td>
                  <td className="py-2 px-3 text-gray-600 text-xs max-w-[120px] truncate">
                    {h.sire}
                  </td>
                  <td className="py-2 px-3 text-center">
                    <span
                      className="inline-flex items-center gap-1 text-[11px] font-medium"
                      style={{ color: cfg?.color }}
                    >
                      <span
                        className="w-2.5 h-2.5 rounded-full"
                        style={{ backgroundColor: cfg?.color }}
                      />
                      {cfg?.label}
                    </span>
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
            {formatNumber(sorted.length)} performers \u2014 Page {page + 1} of{" "}
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
