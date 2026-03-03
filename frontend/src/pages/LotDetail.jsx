import { useParams, Link } from "react-router-dom";
import { useSaleData } from "../hooks/useSaleData";
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
  const { saleId, hipNumber } = useParams();
  const { sale, loading, error } = useSaleData(saleId);

  if (loading) return <LoadingSpinner message="Loading hip details..." />;
  if (error) return <ErrorBanner message={error} />;

  const hip = sale?.hips.find((h) => String(h.hipNumber) === String(hipNumber));
  if (!hip) return <ErrorBanner message={`Hip #${hipNumber} not found`} />;

  return (
    <div className="space-y-6 max-w-5xl">
      {/* Breadcrumb */}
      <div className="flex items-center gap-2 text-sm">
        <Link
          to="/"
          className="text-slate-400 hover:text-brand-400 transition-colors"
        >
          Dashboard
        </Link>
        <span className="text-slate-600">/</span>
        <Link
          to={`/sale/${saleId}`}
          className="text-slate-400 hover:text-brand-400 transition-colors"
        >
          {sale.saleName}
        </Link>
        <span className="text-slate-600">/</span>
        <span className="text-slate-200">Hip #{hipNumber}</span>
      </div>

      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <div className="flex items-center gap-3 mb-1">
            <span className="text-3xl font-bold font-mono text-brand-400">
              #{hip.hipNumber}
            </span>
            <StatusBadge status={hip.status} />
          </div>
          <h1 className="text-xl font-bold text-white">
            {hip.horseName || (
              <span className="text-slate-400 italic">Unnamed</span>
            )}
          </h1>
          <p className="text-sm text-slate-400 mt-1">
            {colorLabel(hip.color)} {sexLabel(hip.sex)} &middot;{" "}
            {hip.yearOfBirth || "—"} &middot; Consigned by {hip.consignor}
          </p>
        </div>
        {hip.price && (
          <div className="text-right">
            <p className="text-xs uppercase tracking-wider text-slate-400">
              Hammer Price
            </p>
            <p className="text-2xl font-bold text-white">
              {formatCurrency(hip.price)}
            </p>
            {hip.buyer && (
              <p className="text-sm text-slate-400">to {hip.buyer}</p>
            )}
          </div>
        )}
      </div>

      {/* Info grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Pedigree */}
        <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-5">
          <h3 className="text-sm font-semibold text-white mb-3 flex items-center gap-2">
            <PedigreeIcon className="w-4 h-4 text-brand-400" />
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
        <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-5">
          <h3 className="text-sm font-semibold text-white mb-3 flex items-center gap-2">
            <TimerIcon className="w-4 h-4 text-accent-400" />
            Under-Tack (Breeze)
          </h3>
          {hip.breezeTime ? (
            <div className="space-y-3">
              <div className="flex items-baseline gap-3">
                <span className="text-4xl font-bold font-mono text-white">
                  {formatBreezeTime(hip.breezeTime)}
                </span>
                <span className="text-sm text-slate-400">
                  {hip.breezeDistance} mile
                </span>
              </div>
              {hip.breezeDate && (
                <p className="text-xs text-slate-500">
                  Breezed on {hip.breezeDate}
                </p>
              )}
            </div>
          ) : (
            <p className="text-slate-500 text-sm">No breeze data recorded</p>
          )}
        </div>
      </div>

      {/* Assets */}
      <div>
        <h2 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
          <MediaIcon className="w-5 h-5 text-brand-400" />
          Assets
        </h2>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {/* Breeze video */}
          {hip.videoUrl && (
            <AssetCard
              label="Breeze Video"
              type="video"
              url={hip.videoUrl}
              accentColor="emerald"
            />
          )}

          {/* Walk video */}
          {hip.walkVideoUrl && (
            <AssetCard
              label="Walking Video"
              type="video"
              url={hip.walkVideoUrl}
              accentColor="sky"
            />
          )}

          {/* Photo */}
          {hip.photoUrl && (
            <AssetCard
              label="Conformation Photo"
              type="image"
              url={hip.photoUrl}
              accentColor="violet"
            />
          )}

          {/* Pedigree PDF */}
          {hip.pedigreeUrl && (
            <AssetCard
              label="Pedigree PDF"
              type="pdf"
              url={hip.pedigreeUrl}
              accentColor="amber"
            />
          )}
        </div>

        {!hip.videoUrl &&
          !hip.walkVideoUrl &&
          !hip.photoUrl &&
          !hip.pedigreeUrl && (
            <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-8 text-center">
              <p className="text-slate-500">
                No assets available for this hip
              </p>
            </div>
          )}
      </div>

      {/* Navigation */}
      <div className="flex items-center justify-between pt-4 border-t border-slate-800">
        {hip.hipNumber > 1 ? (
          <Link
            to={`/sale/${saleId}/hip/${hip.hipNumber - 1}`}
            className="flex items-center gap-2 px-4 py-2 rounded-lg border border-slate-700 text-sm text-slate-300 hover:border-brand-500/40 hover:text-brand-400 transition-colors"
          >
            <span>&larr;</span> Hip #{hip.hipNumber - 1}
          </Link>
        ) : (
          <div />
        )}
        <Link
          to={`/sale/${saleId}/hip/${hip.hipNumber + 1}`}
          className="flex items-center gap-2 px-4 py-2 rounded-lg border border-slate-700 text-sm text-slate-300 hover:border-brand-500/40 hover:text-brand-400 transition-colors"
        >
          Hip #{hip.hipNumber + 1} <span>&rarr;</span>
        </Link>
      </div>
    </div>
  );
}

/* Sub-components */

function PedigreeRow({ label, value, highlight }) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-xs uppercase tracking-wider text-slate-500">
        {label}
      </span>
      <span
        className={`text-sm font-medium ${
          highlight ? "text-brand-400" : "text-slate-200"
        }`}
      >
        {value}
      </span>
    </div>
  );
}

function AssetCard({ label, type, url, accentColor }) {
  const accentMap = {
    emerald: "border-emerald-500/30 hover:border-emerald-500/60",
    sky: "border-sky-500/30 hover:border-sky-500/60",
    violet: "border-violet-500/30 hover:border-violet-500/60",
    amber: "border-amber-500/30 hover:border-amber-500/60",
  };

  return (
    <div
      className={`rounded-xl border bg-slate-900/50 overflow-hidden transition-colors ${accentMap[accentColor]}`}
    >
      {type === "video" && (
        <video
          src={url}
          controls
          preload="metadata"
          className="w-full aspect-video bg-black"
        />
      )}
      {type === "image" && (
        <img
          src={url}
          alt={label}
          className="w-full aspect-video object-cover bg-slate-800"
          loading="lazy"
        />
      )}
      {type === "pdf" && (
        <div className="aspect-video bg-slate-800/50 flex items-center justify-center">
          <a
            href={url}
            target="_blank"
            rel="noopener noreferrer"
            className="flex flex-col items-center gap-2 text-slate-400 hover:text-brand-400 transition-colors"
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
          <span className="text-xs font-medium text-slate-300">{label}</span>
          <a
            href={url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-xs text-slate-500 hover:text-brand-400 transition-colors"
          >
            Open &rarr;
          </a>
        </div>
      </div>
    </div>
  );
}

/* Icons */
function PedigreeIcon({ className }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
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
      strokeWidth="2"
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
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <polygon points="23,7 16,12 23,17 23,7" />
      <rect x="1" y="5" width="15" height="14" rx="2" ry="2" />
    </svg>
  );
}
