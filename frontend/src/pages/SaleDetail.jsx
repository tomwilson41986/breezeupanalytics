import { useState, useEffect, useMemo } from "react";
import { useParams, Link } from "react-router-dom";
import { useSaleData } from "../hooks/useSaleData";
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

      {/* Hip table */}
      <div>
        <h2 className="text-lg font-semibold text-gray-900 mb-4">
          Full Catalog
        </h2>
        <HipTable hips={mergedHips} saleKey={saleKey} assetIndex={assetIndex} />
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
