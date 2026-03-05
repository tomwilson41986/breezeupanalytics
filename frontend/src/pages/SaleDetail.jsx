import { useState, useEffect, useMemo } from "react";
import { useParams, Link } from "react-router-dom";
import { useSaleData } from "../hooks/useSaleData";
import { useLiveSaleTimes } from "../hooks/useLiveSaleTimes";
import { SALE_CATALOG } from "../lib/api";
import StatCard from "../components/StatCard";
import HipTable from "../components/HipTable";
import LoadingSpinner from "../components/LoadingSpinner";
import ErrorBanner from "../components/ErrorBanner";
import PriceDistributionChart from "../components/charts/PriceDistributionChart";
import SireLeaderboard from "../components/charts/SireLeaderboard";
import {
  formatCompact,
  formatNumber,
  formatPercent,
  formatCurrency,
} from "../lib/format";

export default function SaleDetail() {
  const { saleKey } = useParams();
  const { sale, stats, assetIndex, dataSource, loading, error } = useSaleData(saleKey);
  const [utVideos, setUtVideos] = useState(null);
  const [utLatest, setUtLatest] = useState(null);
  const [catalogTab, setCatalogTab] = useState("catalog");
  const { timesData, loading: timesLoading } = useLiveSaleTimes(saleKey);
  const hasTimesData = timesData && timesData.count > 0;

  const meta = SALE_CATALOG[saleKey];

  // Fetch Under Tack videos/links and latest UT data
  useEffect(() => {
    if (!saleKey) return;
    let cancelled = false;

    async function tryJson(url) {
      const res = await fetch(url);
      if (res.ok) return res.json();
      return null;
    }

    async function loadUtData() {
      // Try S3 first, fall back to static files
      let videos = null;
      let latest = null;
      try {
        [videos, latest] = await Promise.all([
          tryJson(`/.netlify/functions/sale-data?sale=${encodeURIComponent(saleKey)}&type=under-tack/videos`),
          tryJson(`/.netlify/functions/sale-data?sale=${encodeURIComponent(saleKey)}&type=under-tack/latest`),
        ]);
      } catch {}
      // Fallback to static files
      if (!videos) {
        try { videos = await tryJson(`/data/under-tack/${saleKey}/videos.json`); } catch {}
      }
      if (!latest) {
        try { latest = await tryJson(`/data/under-tack/${saleKey}/latest.json`); } catch {}
      }
      if (!cancelled) {
        setUtVideos(videos);
        setUtLatest(latest);
      }
    }
    loadUtData();
    return () => { cancelled = true; };
  }, [saleKey]);

  // Merge Under Tack data from latest.json into sale hips
  const mergedHips = useMemo(() => {
    if (!sale?.hips) return [];
    if (!utLatest?.hips?.length) return sale.hips;

    // Build lookup from UT latest data by hip_number
    const utMap = {};
    for (const uh of utLatest.hips) {
      utMap[uh.hip_number] = uh;
    }

    return sale.hips.map((hip) => {
      const ut = utMap[hip.hipNumber];
      if (!ut) return hip;
      return {
        ...hip,
        breezeTime: hip.breezeTime ?? ut.ut_time ?? null,
        breezeDistance: hip.breezeDistance ?? ut.ut_distance ?? null,
        breezeDate: hip.breezeDate ?? ut.ut_actual_date ?? null,
        videoUrl: hip.videoUrl ?? ut.video_url ?? null,
        walkVideoUrl: hip.walkVideoUrl ?? ut.walk_video_url ?? null,
      };
    });
  }, [sale, utLatest]);

  // Compute Under Tack summary from merged hips
  const utSummary = useMemo(() => {
    if (!mergedHips.length) return null;
    const breezed = mergedHips.filter((h) => h.breezeTime != null);
    if (breezed.length === 0) return null;
    const fastest = Math.min(...breezed.map((h) => h.breezeTime));
    const dates = [...new Set(breezed.map((h) => h.breezeDate).filter(Boolean))];
    return { breezedCount: breezed.length, fastest, dateCount: dates.length };
  }, [mergedHips]);

  if (loading) return <LoadingSpinner message="Loading sale catalog..." />;
  if (error) return <ErrorBanner message={error} />;

  // Asset-only mode for historical sales
  if (dataSource === "assets-only") {
    return (
      <AssetOnlySaleView
        saleKey={saleKey}
        meta={meta}
        assetIndex={assetIndex}
      />
    );
  }

  if (!sale) return <ErrorBanner message="Sale not found" />;

  const backLink = meta?.isLive ? "/live" : "/historic";
  const backLabel = meta?.isLive ? "Live Sales" : "Historic Sales";

  const hasUtVideos = utVideos?.videos?.length > 0 || utVideos?.links?.length > 0;

  return (
    <div className="space-y-6">
      {/* Breadcrumb */}
      <div className="flex items-center gap-2 text-sm">
        <Link
          to={backLink}
          className="text-gray-400 hover:text-brand-600 transition-colors"
        >
          {backLabel}
        </Link>
        <span className="text-gray-300">/</span>
        <span className="text-gray-700">{sale.saleName}</span>
      </div>

      {/* Header */}
      <div>
        <h1 className="text-2xl font-semibold text-gray-900 tracking-tight">
          {sale.saleName}
        </h1>
        <p className="text-sm text-gray-500 mt-1">
          {meta?.company || "OBS"} &middot; {meta?.location || "Ocala, FL"}
        </p>
      </div>

      {/* Key metrics */}
      <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-6 gap-3">
        <StatCard
          label="Cataloged"
          value={formatNumber(stats.totalHips)}
        />
        <StatCard
          label="Sold"
          value={formatNumber(stats.soldCount)}
          sub={`${formatPercent(
            (stats.soldCount / stats.totalHips) * 100
          )} of catalog`}
        />
        <StatCard
          label="RNA"
          value={formatNumber(stats.rnaCount)}
          sub={`${formatPercent(stats.buybackRate)} buyback`}
        />
        <StatCard
          label="Average"
          value={formatCompact(stats.avgPrice)}
          accent
        />
        <StatCard label="Median" value={formatCompact(stats.medianPrice)} />
        <StatCard
          label="Top Price"
          value={formatCurrency(stats.maxPrice)}
          accent
        />
      </div>

      {/* Under Tack summary */}
      {utSummary && (
        <div>
          <h2 className="text-lg font-semibold text-gray-900 mb-3 flex items-center gap-2">
            <svg className="w-5 h-5 text-emerald-500" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="10" />
              <polyline points="12 6 12 12 16 14" />
            </svg>
            Under Tack
          </h2>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <StatCard
              label="Breezed"
              value={formatNumber(utSummary.breezedCount)}
              sub={`of ${formatNumber(stats.totalHips)} cataloged`}
              accent
            />
            <StatCard
              label="Breeze Days"
              value={formatNumber(utSummary.dateCount)}
            />
            <StatCard
              label="Fastest"
              value={`${utSummary.fastest.toFixed(1)}s`}
              accent
            />
            <StatCard
              label="Breeze Rate"
              value={formatPercent(
                (utSummary.breezedCount / stats.totalHips) * 100
              )}
            />
          </div>
        </div>
      )}

      {/* Under Tack Videos & Reports */}
      {hasUtVideos && (
        <div className="rounded-xl border border-gray-100 bg-white p-4 shadow-[0_1px_3px_rgba(0,0,0,0.04)]">
          <h3 className="text-sm font-semibold text-gray-900 mb-3">
            Under Tack Videos & Reports
          </h3>
          <div className="flex flex-wrap gap-2">
            {utVideos.videos?.map((v, i) => (
              <a
                key={i}
                href={v.url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-red-50 text-red-700 text-xs font-medium border border-red-200 hover:bg-red-100 transition-colors"
              >
                <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="currentColor">
                  <path d="M19.615 3.184c-3.604-.246-11.631-.245-15.23 0-3.897.266-4.356 2.62-4.385 8.816.029 6.185.484 8.549 4.385 8.816 3.6.245 11.626.246 15.23 0 3.897-.266 4.356-2.62 4.385-8.816-.029-6.185-.484-8.549-4.385-8.816zM9 16V8l8 4-8 4z" />
                </svg>
                {v.text}
              </a>
            ))}
            {utVideos.links?.map((l, i) => (
              <a
                key={`link-${i}`}
                href={l.url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-blue-50 text-blue-700 text-xs font-medium border border-blue-200 hover:bg-blue-100 transition-colors"
              >
                <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" />
                  <polyline points="14 2 14 8 20 8" />
                </svg>
                {l.text}
              </a>
            ))}
          </div>
        </div>
      )}

      {/* Quick charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <PriceDistributionChart data={stats.priceDistribution} />
        <SireLeaderboard sires={stats.topSires} limit={10} />
      </div>

      {/* Hip table with tabs */}
      <div>
        <div className="flex items-center gap-1 mb-4">
          <button
            onClick={() => setCatalogTab("catalog")}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
              catalogTab === "catalog"
                ? "bg-brand-50 text-brand-700 border border-brand-200"
                : "text-gray-500 hover:text-gray-700 border border-gray-200 hover:border-gray-300"
            }`}
          >
            Full Catalog
          </button>
          <button
            onClick={() => setCatalogTab("times")}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors flex items-center gap-2 ${
              catalogTab === "times"
                ? "bg-brand-50 text-brand-700 border border-brand-200"
                : "text-gray-500 hover:text-gray-700 border border-gray-200 hover:border-gray-300"
            }`}
          >
            <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="10" />
              <polyline points="12 6 12 12 16 14" />
            </svg>
            Detailed Times
            {hasTimesData && (
              <span className="text-[10px] bg-brand-100 text-brand-600 px-1.5 py-0.5 rounded-full font-semibold">
                {timesData.count}
              </span>
            )}
          </button>
        </div>

        {catalogTab === "catalog" && (
          <HipTable hips={mergedHips} saleKey={saleKey} assetIndex={assetIndex} />
        )}

        {catalogTab === "times" && (
          <DetailedTimesTable
            timesData={timesData}
            timesLoading={timesLoading}
            saleKey={saleKey}
          />
        )}
      </div>
    </div>
  );
}

/**
 * Table view for detailed live sale times data.
 * Shows all columns from the uploaded CSV with sorting and search.
 */
function DetailedTimesTable({ timesData, timesLoading, saleKey }) {
  const [sortBy, setSortBy] = useState("hip_number");
  const [sortDir, setSortDir] = useState("asc");
  const [filter, setFilter] = useState("");

  const columns = useMemo(() => {
    if (!timesData?.columns) return [];
    return timesData.columns;
  }, [timesData]);

  const displayColumns = useMemo(
    () => columns.filter((c) => c !== "hip_number"),
    [columns]
  );

  const rows = useMemo(() => {
    if (!timesData?.hips) return [];
    let list = Object.values(timesData.hips);

    if (filter) {
      const q = filter.toLowerCase();
      list = list.filter((r) =>
        String(r.hip_number).includes(q) ||
        Object.values(r).some((v) => String(v).toLowerCase().includes(q))
      );
    }

    list.sort((a, b) => {
      let av = a[sortBy];
      let bv = b[sortBy];
      if (av == null) return 1;
      if (bv == null) return -1;
      if (typeof av === "string") av = av.toLowerCase();
      if (typeof bv === "string") bv = bv.toLowerCase();
      if (av < bv) return sortDir === "asc" ? -1 : 1;
      if (av > bv) return sortDir === "asc" ? 1 : -1;
      return 0;
    });

    return list;
  }, [timesData, filter, sortBy, sortDir]);

  function handleSort(key) {
    if (sortBy === key) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortBy(key);
      setSortDir("asc");
    }
  }

  if (timesLoading) {
    return (
      <div className="rounded-xl border border-gray-100 bg-white p-12 text-center shadow-[0_1px_3px_rgba(0,0,0,0.04)]">
        <p className="text-gray-400 text-sm">Loading detailed times...</p>
      </div>
    );
  }

  if (!timesData || !timesData.count) {
    return (
      <div className="rounded-xl border border-gray-100 bg-white p-12 text-center shadow-[0_1px_3px_rgba(0,0,0,0.04)]">
        <div className="flex flex-col items-center gap-3">
          <svg className="w-10 h-10 text-gray-300" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="10" />
            <polyline points="12 6 12 12 16 14" />
          </svg>
          <p className="text-gray-400 text-sm">
            No detailed times data available yet.
          </p>
          <p className="text-gray-300 text-xs">
            Upload a CSV using the upload script to populate this view.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div>
      {/* Controls */}
      <div className="flex flex-wrap items-center gap-3 mb-4">
        <input
          type="text"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          placeholder="Search by hip number..."
          className="flex-1 min-w-[200px] bg-white border border-gray-200 rounded-lg px-3 py-2 text-sm text-gray-900 placeholder:text-gray-400 focus:outline-none focus:border-brand-400 focus:ring-2 focus:ring-brand-100 transition-shadow"
        />
        <span className="text-xs text-gray-400">
          {rows.length} of {timesData.count} hips
        </span>
        {timesData.generated_at && (
          <span className="text-xs text-gray-300">
            Updated {new Date(timesData.generated_at).toLocaleDateString()}
          </span>
        )}
      </div>

      {/* Table */}
      <div className="overflow-x-auto rounded-xl border border-gray-100 bg-white shadow-[0_1px_3px_rgba(0,0,0,0.04)]">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-100">
              <th
                className="px-3 py-3 text-left text-[11px] font-medium uppercase tracking-wider text-gray-400 cursor-pointer hover:text-gray-700 select-none w-16 sticky left-0 bg-white z-10"
                onClick={() => handleSort("hip_number")}
              >
                <span className="flex items-center gap-1">
                  Hip
                  {sortBy === "hip_number" && (
                    <span className="text-brand-600">
                      {sortDir === "asc" ? "↑" : "↓"}
                    </span>
                  )}
                </span>
              </th>
              {displayColumns.map((col) => (
                <th
                  key={col}
                  className="px-3 py-3 text-left text-[11px] font-medium uppercase tracking-wider text-gray-400 cursor-pointer hover:text-gray-700 select-none whitespace-nowrap"
                  onClick={() => handleSort(col)}
                >
                  <span className="flex items-center gap-1">
                    {col.replace(/_/g, " ")}
                    {sortBy === col && (
                      <span className="text-brand-600">
                        {sortDir === "asc" ? "↑" : "↓"}
                      </span>
                    )}
                  </span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-50">
            {rows.map((row) => (
              <tr key={row.hip_number} className="table-row-hover">
                <td className="px-3 py-2.5 font-mono font-semibold text-brand-600 sticky left-0 bg-white z-10">
                  <Link
                    to={`/sale/${saleKey}/hip/${row.hip_number}`}
                    className="hover:underline"
                  >
                    {row.hip_number}
                  </Link>
                </td>
                {displayColumns.map((col) => (
                  <td
                    key={col}
                    className="px-3 py-2.5 font-mono text-gray-600 whitespace-nowrap"
                  >
                    {row[col] != null
                      ? typeof row[col] === "number"
                        ? row[col] % 1 === 0
                          ? row[col]
                          : row[col].toFixed(2)
                        : row[col]
                      : <span className="text-gray-300">—</span>}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
        {rows.length === 0 && (
          <div className="text-center py-12 text-gray-400">
            No hips match your search
          </div>
        )}
      </div>
    </div>
  );
}

/**
 * View for historical sales that only have S3 assets (no JSON sale data).
 * Displays a hip grid derived from the S3 asset index.
 */
function AssetOnlySaleView({ saleKey, meta, assetIndex }) {
  const hipNumbers = Object.keys(assetIndex || {})
    .map(Number)
    .sort((a, b) => a - b);

  const backLink = meta?.isLive ? "/live" : "/historic";
  const backLabel = meta?.isLive ? "Live Sales" : "Historic Sales";

  return (
    <div className="space-y-6">
      {/* Breadcrumb */}
      <div className="flex items-center gap-2 text-sm">
        <Link
          to={backLink}
          className="text-gray-400 hover:text-brand-600 transition-colors"
        >
          {backLabel}
        </Link>
        <span className="text-gray-300">/</span>
        <span className="text-gray-700">{meta?.name || saleKey}</span>
      </div>

      {/* Header */}
      <div>
        <h1 className="text-2xl font-semibold text-gray-900 tracking-tight">
          {meta?.name || saleKey}
        </h1>
        <p className="text-sm text-gray-500 mt-1">
          {meta?.company || "OBS"} &middot; {meta?.location || "Ocala, FL"} &middot;{" "}
          <span className="text-amber-600">Asset-only view</span>
        </p>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <StatCard label="Hips with Assets" value={formatNumber(hipNumbers.length)} accent />
        <StatCard
          label="Videos"
          value={formatNumber(
            Object.values(assetIndex || {}).filter((a) => a.video).length
          )}
        />
        <StatCard
          label="Photos"
          value={formatNumber(
            Object.values(assetIndex || {}).filter((a) => a.photo).length
          )}
        />
        <StatCard
          label="Pedigree PDFs"
          value={formatNumber(
            Object.values(assetIndex || {}).filter((a) => a.pedigree).length
          )}
        />
      </div>

      {/* Hip grid */}
      <div>
        <h2 className="text-lg font-semibold text-gray-900 mb-4">
          Browse by Hip Number
        </h2>
        {hipNumbers.length === 0 ? (
          <div className="rounded-xl border border-gray-100 bg-white p-8 text-center shadow-[0_1px_3px_rgba(0,0,0,0.04)]">
            <p className="text-gray-400">No assets found for this sale</p>
          </div>
        ) : (
          <div className="grid grid-cols-4 sm:grid-cols-6 md:grid-cols-8 lg:grid-cols-10 gap-2">
            {hipNumbers.map((hip) => {
              const assets = assetIndex[String(hip)] || {};
              return (
                <Link
                  key={hip}
                  to={`/sale/${saleKey}/hip/${hip}`}
                  className="flex flex-col items-center rounded-lg border border-gray-100 bg-white p-3 hover:border-brand-300 hover:shadow-sm transition-all group"
                >
                  <span className="text-lg font-mono font-bold text-brand-600 group-hover:text-brand-700">
                    #{hip}
                  </span>
                  <div className="flex gap-1 mt-1.5">
                    {assets.video && (
                      <span className="w-4 h-4 rounded text-[8px] font-bold flex items-center justify-center bg-emerald-50 text-emerald-600 border border-emerald-200">
                        V
                      </span>
                    )}
                    {assets.walkVideo && (
                      <span className="w-4 h-4 rounded text-[8px] font-bold flex items-center justify-center bg-sky-50 text-sky-600 border border-sky-200">
                        W
                      </span>
                    )}
                    {assets.photo && (
                      <span className="w-4 h-4 rounded text-[8px] font-bold flex items-center justify-center bg-violet-50 text-violet-600 border border-violet-200">
                        P
                      </span>
                    )}
                    {assets.pedigree && (
                      <span className="w-4 h-4 rounded text-[8px] font-bold flex items-center justify-center bg-amber-50 text-amber-600 border border-amber-200">
                        D
                      </span>
                    )}
                  </div>
                </Link>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
