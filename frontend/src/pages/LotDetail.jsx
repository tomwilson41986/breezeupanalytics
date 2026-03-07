import { useState, useEffect, useMemo } from "react";
import { useParams, Link } from "react-router-dom";
import { useSaleData } from "../hooks/useSaleData";
import { useHipAssets } from "../hooks/useHipAssets";
import { useLiveSaleTimes } from "../hooks/useLiveSaleTimes";
import { SALE_CATALOG } from "../lib/api";
import StatusBadge from "../components/StatusBadge";
import LoadingSpinner from "../components/LoadingSpinner";
import ErrorBanner from "../components/ErrorBanner";
import {
  formatCurrency,
  formatBreezeTime,
  sexLabel,
  colorLabel,
} from "../lib/format";

export default function LotDetail() {
  const { saleKey, hipNumber } = useParams();
  const { sale, dataSource, loading, error } = useSaleData(saleKey);
  const [utLatest, setUtLatest] = useState(null);

  // Use s3Key directly for asset fetching
  const { assets: s3Assets, loading: assetsLoading } = useHipAssets(
    saleKey,
    hipNumber
  );

  // Fetch detailed live sale times
  const { timesData } = useLiveSaleTimes(saleKey);
  const hipTimes = timesData?.hips?.[String(hipNumber)] || null;
  const timesColumns = timesData?.columns || [];
  const columnLabels = timesData?.column_labels || {};

  const meta = SALE_CATALOG[saleKey];

  // Fetch Under Tack latest data for merging
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

  // Merge UT data into the hip (must be above conditional returns to satisfy Rules of Hooks)
  const rawHip = sale?.hips?.find((h) => String(h.hipNumber) === String(hipNumber)) ?? null;

  const hip = useMemo(() => {
    if (!rawHip) return rawHip;
    const utHip = utLatest?.hips?.find((uh) => uh.hip_number === rawHip.hipNumber);
    if (!utHip) return rawHip;
    return {
      ...rawHip,
      breezeTime: rawHip.breezeTime ?? utHip.ut_time ?? null,
      breezeDistance: rawHip.breezeDistance ?? utHip.ut_distance ?? null,
      breezeDate: rawHip.breezeDate ?? utHip.ut_actual_date ?? null,
      videoUrl: rawHip.videoUrl ?? utHip.video_url ?? null,
      walkVideoUrl: rawHip.walkVideoUrl ?? utHip.walk_video_url ?? null,
    };
  }, [rawHip, utLatest]);

  if (loading) return <LoadingSpinner message="Loading hip details..." />;
  if (error) return <ErrorBanner message={error} />;

  if (!hip && dataSource !== "assets-only") {
    return <ErrorBanner message={`Hip #${hipNumber} not found`} />;
  }

  // Merge S3 assets with OBS assets — S3 takes priority
  const videoUrl = s3Assets?.video || hip?.videoUrl;
  const walkVideoUrl = s3Assets?.walkVideo || hip?.walkVideoUrl;
  const photoUrl = s3Assets?.photo || hip?.photoUrl;
  const pedigreeUrl = s3Assets?.pedigree || hip?.pedigreeUrl;
  const hasAnyAsset = videoUrl || walkVideoUrl || photoUrl || pedigreeUrl;

  const saleName = sale?.saleName || meta?.name || saleKey;

  return (
    <div className="space-y-6 max-w-5xl">
      {/* Breadcrumb */}
      <div className="flex items-center gap-2 text-sm">
        <Link
          to={meta?.isLive ? "/live" : "/historic"}
          className="text-gray-400 hover:text-brand-600 transition-colors"
        >
          {meta?.isLive ? "Live Sales" : "Historic Sales"}
        </Link>
        <span className="text-gray-300">/</span>
        <Link
          to={`/sale/${saleKey}`}
          className="text-gray-400 hover:text-brand-600 transition-colors"
        >
          {saleName}
        </Link>
        <span className="text-gray-300">/</span>
        <span className="text-gray-700">Hip #{hipNumber}</span>
      </div>

      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <div className="flex items-center gap-3 mb-1">
            <span className="text-3xl font-bold font-mono text-brand-600">
              #{hipNumber}
            </span>
            {hip && <StatusBadge status={hip.status} />}
          </div>
          {hip && (
            <>
              <h1 className="text-xl font-semibold text-gray-900">
                {hip.horseName || (
                  <span className="text-gray-400 italic">Unnamed</span>
                )}
              </h1>
              <p className="text-sm text-gray-500 mt-1">
                {colorLabel(hip.color)} {sexLabel(hip.sex)} &middot;{" "}
                {hip.yearOfBirth || "—"} &middot; Consigned by {hip.consignor}
              </p>
            </>
          )}
          {!hip && (
            <h1 className="text-xl font-semibold text-gray-900">
              Hip #{hipNumber}
              <span className="text-sm text-gray-400 font-normal ml-2">
                ({saleName})
              </span>
            </h1>
          )}
        </div>
        {hip?.price && (
          <div className="text-right">
            <p className="text-[11px] uppercase tracking-wider text-gray-400">
              Hammer Price
            </p>
            <p className="text-2xl font-semibold text-gray-900">
              {formatCurrency(hip.price)}
            </p>
            {hip.buyer && (
              <p className="text-sm text-gray-500">to {hip.buyer}</p>
            )}
          </div>
        )}
      </div>

      {/* Info grid — only for sales with full data */}
      {hip && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {/* Pedigree */}
          <div className="rounded-xl border border-gray-100 bg-white p-5 shadow-[0_1px_3px_rgba(0,0,0,0.04)]">
            <h3 className="text-sm font-semibold text-gray-900 mb-3 flex items-center gap-2">
              <PedigreeIcon className="w-4 h-4 text-brand-500" />
              Pedigree
            </h3>
            <div className="space-y-3">
              <PedigreeRow label="Sire" value={hip.sire} highlight />
              <PedigreeRow label="Dam" value={hip.dam} />
              <PedigreeRow label="Dam Sire" value={hip.damSire} />
              {hip.stateBred && (
                <PedigreeRow label="State Bred" value={hip.stateBred} />
              )}
            </div>
          </div>

          {/* Under-tack */}
          <div className="rounded-xl border border-gray-100 bg-white p-5 shadow-[0_1px_3px_rgba(0,0,0,0.04)]">
            <h3 className="text-sm font-semibold text-gray-900 mb-3 flex items-center gap-2">
              <TimerIcon className="w-4 h-4 text-emerald-500" />
              Under-Tack (Breeze)
            </h3>
            {hip.breezeTime ? (
              <div className="space-y-3">
                <div className="flex items-baseline gap-3">
                  <span className="text-4xl font-bold font-mono text-gray-900">
                    {formatBreezeTime(hip.breezeTime)}
                  </span>
                  <span className="text-sm text-gray-500">
                    {hip.breezeDistance} mile
                  </span>
                </div>
                {hip.breezeDate && (
                  <p className="text-xs text-gray-400">
                    Breezed on {hip.breezeDate}
                  </p>
                )}
              </div>
            ) : (
              <p className="text-gray-400 text-sm">No breeze data recorded</p>
            )}
          </div>
        </div>
      )}

      {/* Ratings & Stride Analysis */}
      {hip?.ratings && (
        <div className="rounded-xl border border-gray-100 bg-white p-5 shadow-[0_1px_3px_rgba(0,0,0,0.04)]">
          <h3 className="text-sm font-semibold text-gray-900 mb-4 flex items-center gap-2">
            <ChartIcon className="w-4 h-4 text-brand-500" />
            Breeze Rating & Stride Analysis
            <span className="text-xs font-normal text-gray-400 ml-auto">
              Distance group: {hip.ratings.distanceUT || "—"}
            </span>
          </h3>

          {/* Rating hero */}
          <div className="flex items-center gap-6 mb-5">
            <div className="text-center">
              <div
                className={`text-4xl font-bold font-mono ${
                  hip.ratings.rating >= 80
                    ? "text-emerald-600"
                    : hip.ratings.rating >= 60
                    ? "text-sky-600"
                    : hip.ratings.rating >= 40
                    ? "text-amber-600"
                    : "text-red-600"
                }`}
              >
                {hip.ratings.rating?.toFixed(1)}
              </div>
              <div className="text-[11px] uppercase tracking-wider text-gray-400 mt-1">
                Breeze Rating
              </div>
            </div>
            <div className="flex-1 grid grid-cols-2 sm:grid-cols-3 gap-3">
              <MetricCard
                label="Stride UT"
                value={hip.ratings.strideLengthUT}
                unit="ft"
                rank={hip.ratings.rankStrideLengthUt}
              />
              <MetricCard
                label="Stride GO"
                value={hip.ratings.strideLengthGO}
                unit="ft"
                rank={hip.ratings.rankStrideLengthGo}
              />
              <MetricCard
                label="Time UT"
                value={hip.ratings.timeUT}
                unit="s"
                rank={hip.ratings.rankTimeUt}
              />
              <MetricCard
                label="Time GO"
                value={hip.ratings.timeGO}
                unit="s"
                rank={hip.ratings.rankTimeGo}
              />
              {hip.ratings.strideFreqUT != null && (
                <MetricCard
                  label="Freq UT"
                  value={hip.ratings.strideFreqUT}
                  unit="Hz"
                />
              )}
              {hip.ratings.strideFreqGO != null && (
                <MetricCard
                  label="Freq GO"
                  value={hip.ratings.strideFreqGO}
                  unit="Hz"
                />
              )}
            </div>
          </div>

          {/* Detail row */}
          <div className="grid grid-cols-2 gap-4 pt-4 border-t border-gray-50">
            <div className="text-center">
              <span className="text-[11px] uppercase tracking-wider text-gray-400 block">
                Diff (UT vs GO)
              </span>
              <span className="text-sm font-mono font-medium text-gray-700">
                {hip.ratings.diff != null ? hip.ratings.diff.toFixed(2) : "—"}
              </span>
              {hip.ratings.rankDiff != null && (
                <span className="text-[10px] text-gray-400 block">
                  Rank #{hip.ratings.rankDiff}
                </span>
              )}
            </div>
            <div className="text-center">
              <span className="text-[11px] uppercase tracking-wider text-gray-400 block">
                Mean Rank
              </span>
              <span className="text-sm font-mono font-medium text-gray-700">
                {hip.ratings.meanRank?.toFixed(2) || "—"}
              </span>
            </div>
          </div>
        </div>
      )}

      {/* Detailed Times */}
      {hipTimes && (
        <div className="rounded-xl border border-gray-100 bg-white p-5 shadow-[0_1px_3px_rgba(0,0,0,0.04)]">
          <h3 className="text-sm font-semibold text-gray-900 mb-4 flex items-center gap-2">
            <TimerIcon className="w-4 h-4 text-brand-500" />
            Detailed Times
          </h3>
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3">
            {timesColumns
              .filter((col) => col !== "hip_number" && hipTimes[col] != null)
              .map((col) => (
                <div key={col} className="rounded-lg bg-gray-50 p-3 text-center">
                  <div className="text-[11px] uppercase tracking-wider text-gray-400 mb-1">
                    {columnLabels[col] || col.replace(/_/g, " ")}
                  </div>
                  <div className="text-lg font-mono font-semibold text-gray-800">
                    {typeof hipTimes[col] === "number"
                      ? hipTimes[col] % 1 === 0
                        ? hipTimes[col]
                        : hipTimes[col].toFixed(2)
                      : hipTimes[col]}
                  </div>
                </div>
              ))}
          </div>
        </div>
      )}

      {/* Assets */}
      <div>
        <h2 className="text-lg font-semibold text-gray-900 mb-4 flex items-center gap-2">
          <MediaIcon className="w-5 h-5 text-brand-500" />
          Assets
          {assetsLoading && (
            <span className="text-xs font-normal text-gray-400 ml-2">Loading from S3...</span>
          )}
        </h2>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {videoUrl && (
            <AssetCard
              label="Breeze Video"
              type="video"
              url={videoUrl}
              accentColor="emerald"
              fromS3={!!s3Assets?.video}
              posterUrl={photoUrl}
              primary
            />
          )}
          {walkVideoUrl && (
            <AssetCard
              label="Walking Video"
              type="video"
              url={walkVideoUrl}
              accentColor="sky"
              fromS3={!!s3Assets?.walkVideo}
              posterUrl={photoUrl}
            />
          )}
          {photoUrl && (
            <AssetCard
              label="Conformation Photo"
              type="image"
              url={photoUrl}
              accentColor="violet"
              fromS3={!!s3Assets?.photo}
            />
          )}
          {pedigreeUrl && (
            <AssetCard
              label="Pedigree PDF"
              type="pdf"
              url={pedigreeUrl}
              accentColor="amber"
              fromS3={!!s3Assets?.pedigree}
            />
          )}
        </div>

        {!assetsLoading && !hasAnyAsset && (
          <div className="rounded-xl border border-gray-100 bg-white p-8 text-center shadow-[0_1px_3px_rgba(0,0,0,0.04)]">
            <p className="text-gray-400">
              No assets available for this hip
            </p>
          </div>
        )}
      </div>

      {/* Navigation */}
      <div className="flex items-center justify-between pt-4 border-t border-gray-100">
        {Number(hipNumber) > 1 ? (
          <Link
            to={`/sale/${saleKey}/hip/${Number(hipNumber) - 1}`}
            className="flex items-center gap-2 px-4 py-2 rounded-lg border border-gray-200 text-sm text-gray-600 hover:border-brand-300 hover:text-brand-600 transition-colors"
          >
            <span>&larr;</span> Hip #{Number(hipNumber) - 1}
          </Link>
        ) : (
          <div />
        )}
        <Link
          to={`/sale/${saleKey}/hip/${Number(hipNumber) + 1}`}
          className="flex items-center gap-2 px-4 py-2 rounded-lg border border-gray-200 text-sm text-gray-600 hover:border-brand-300 hover:text-brand-600 transition-colors"
        >
          Hip #{Number(hipNumber) + 1} <span>&rarr;</span>
        </Link>
      </div>
    </div>
  );
}

/* Sub-components */

function PedigreeRow({ label, value, highlight }) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-[11px] uppercase tracking-wider text-gray-400">
        {label}
      </span>
      <span
        className={`text-sm font-medium ${
          highlight ? "text-brand-600" : "text-gray-700"
        }`}
      >
        {value}
      </span>
    </div>
  );
}

function getYouTubeId(url) {
  if (!url) return null;
  const m = url.match(/(?:youtube\.com\/watch\?v=|youtu\.be\/)([\w-]{11})/);
  return m ? m[1] : null;
}

function AssetCard({ label, type, url, accentColor, fromS3, posterUrl, primary }) {
  const accentMap = {
    emerald: "border-gray-100 hover:border-emerald-200",
    sky: "border-gray-100 hover:border-sky-200",
    violet: "border-gray-100 hover:border-violet-200",
    amber: "border-gray-100 hover:border-amber-200",
  };

  const ytId = type === "video" ? getYouTubeId(url) : null;

  return (
    <div
      className={`rounded-xl border bg-white overflow-hidden transition-colors shadow-[0_1px_3px_rgba(0,0,0,0.04)] ${accentMap[accentColor]}`}
    >
      {type === "video" && ytId && (
        <iframe
          src={`https://www.youtube.com/embed/${ytId}`}
          title={label}
          allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
          allowFullScreen
          className="w-full aspect-video bg-gray-50"
        />
      )}
      {type === "video" && !ytId && (
        <video
          src={url}
          controls
          preload={primary ? "auto" : "metadata"}
          playsInline
          poster={posterUrl || undefined}
          className="w-full aspect-video bg-gray-50"
        />
      )}
      {type === "image" && (
        <img
          src={url}
          alt={label}
          className="w-full aspect-video object-cover bg-gray-50"
          loading="lazy"
        />
      )}
      {type === "pdf" && (
        <div className="aspect-video bg-gray-50 flex items-center justify-center">
          <a
            href={url}
            target="_blank"
            rel="noopener noreferrer"
            className="flex flex-col items-center gap-2 text-gray-400 hover:text-brand-600 transition-colors"
          >
            <svg
              className="w-10 h-10"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.5"
            >
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
              <polyline points="14,2 14,8 20,8" />
              <line x1="16" y1="13" x2="8" y2="13" />
              <line x1="16" y1="17" x2="8" y2="17" />
              <polyline points="10,9 9,9 8,9" />
            </svg>
            <span className="text-sm font-medium">View Pedigree PDF</span>
          </a>
        </div>
      )}
      <div className="p-3">
        <div className="flex items-center justify-between">
          <span className="text-xs font-medium text-gray-600">
            {label}
            {fromS3 && (
              <span className="ml-1.5 text-[10px] text-brand-500 font-normal">S3</span>
            )}
          </span>
          <a
            href={url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-xs text-gray-400 hover:text-brand-600 transition-colors"
          >
            Open &rarr;
          </a>
        </div>
      </div>
    </div>
  );
}

function MetricCard({ label, value, unit, rank }) {
  return (
    <div className="rounded-lg bg-gray-50 p-2.5 text-center">
      <div className="text-[11px] uppercase tracking-wider text-gray-400 mb-1">
        {label}
      </div>
      <div className="text-lg font-mono font-semibold text-gray-800">
        {value != null ? value.toFixed(2) : "—"}
        {value != null && (
          <span className="text-xs font-normal text-gray-400">{unit}</span>
        )}
      </div>
      {rank != null && (
        <div className="text-[10px] text-gray-400 mt-0.5">Rank #{rank}</div>
      )}
    </div>
  );
}

/* Icons */
function ChartIcon({ className }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <line x1="18" y1="20" x2="18" y2="10" />
      <line x1="12" y1="20" x2="12" y2="4" />
      <line x1="6" y1="20" x2="6" y2="14" />
    </svg>
  );
}

function PedigreeIcon({ className }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" />
      <circle cx="9" cy="7" r="4" />
      <path d="M23 21v-2a4 4 0 0 0-3-3.87" />
      <path d="M16 3.13a4 4 0 0 1 0 7.75" />
    </svg>
  );
}

function TimerIcon({ className }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <circle cx="12" cy="12" r="10" />
      <polyline points="12,6 12,12 16,14" />
    </svg>
  );
}

function MediaIcon({ className }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <polygon points="23,7 16,12 23,17 23,7" />
      <rect x="1" y="5" width="15" height="14" rx="2" ry="2" />
    </svg>
  );
}
