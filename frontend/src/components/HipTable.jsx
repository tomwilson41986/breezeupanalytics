import { useState, useMemo } from "react";
import { Link } from "react-router-dom";
import StatusBadge from "./StatusBadge";
import {
  formatCurrency,
  formatBreezeTime,
  sexLabel,
  colorLabel,
} from "../lib/format";

const SORT_FIELDS = [
  { key: "hipNumber", label: "Hip #" },
  { key: "price", label: "Price" },
  { key: "breezeTime", label: "UT Time" },
  { key: "sire", label: "Sire" },
];

export default function HipTable({ hips, saleKey, assetIndex }) {
  const [sortBy, setSortBy] = useState("hipNumber");
  const [sortDir, setSortDir] = useState("asc");
  const [filter, setFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");

  const filtered = useMemo(() => {
    let list = [...hips];

    if (statusFilter !== "all") {
      list = list.filter((h) => h.status === statusFilter);
    }

    if (filter) {
      const q = filter.toLowerCase();
      list = list.filter(
        (h) =>
          String(h.hipNumber).includes(q) ||
          (h.horseName && h.horseName.toLowerCase().includes(q)) ||
          h.sire.toLowerCase().includes(q) ||
          h.dam.toLowerCase().includes(q) ||
          h.consignor.toLowerCase().includes(q) ||
          (h.buyer && h.buyer.toLowerCase().includes(q))
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
  }, [hips, filter, statusFilter, sortBy, sortDir]);

  function handleSort(key) {
    if (sortBy === key) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortBy(key);
      setSortDir("asc");
    }
  }

  const SortHeader = ({ field, children, className = "" }) => (
    <th
      className={`px-3 py-3 text-left text-[11px] font-medium uppercase tracking-wider text-gray-400 cursor-pointer hover:text-gray-700 select-none ${className}`}
      onClick={() => handleSort(field)}
    >
      <span className="flex items-center gap-1">
        {children}
        {sortBy === field && (
          <span className="text-brand-600">
            {sortDir === "asc" ? "↑" : "↓"}
          </span>
        )}
      </span>
    </th>
  );

  return (
    <div>
      {/* Controls */}
      <div className="flex flex-wrap items-center gap-3 mb-4">
        <input
          type="text"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          placeholder="Search hip, sire, dam, consignor, buyer..."
          className="flex-1 min-w-[200px] bg-white border border-gray-200 rounded-lg px-3 py-2 text-sm text-gray-900 placeholder:text-gray-400 focus:outline-none focus:border-brand-400 focus:ring-2 focus:ring-brand-100 transition-shadow"
        />
        <div className="flex gap-1">
          {["all", "sold", "rna", "out", "pending"].map((s) => (
            <button
              key={s}
              onClick={() => setStatusFilter(s)}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium capitalize transition-colors ${
                statusFilter === s
                  ? "bg-brand-50 text-brand-700 border border-brand-200"
                  : "text-gray-500 hover:text-gray-700 border border-gray-200 hover:border-gray-300"
              }`}
            >
              {s}
            </button>
          ))}
        </div>
        <span className="text-xs text-gray-400">
          {filtered.length} of {hips.length} hips
        </span>
      </div>

      {/* Table */}
      <div className="overflow-x-auto rounded-xl border border-gray-100 bg-white shadow-[0_1px_3px_rgba(0,0,0,0.04)]">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-100">
              <SortHeader field="hipNumber" className="w-16">
                Hip
              </SortHeader>
              <th className="px-3 py-3 text-left text-[11px] font-medium uppercase tracking-wider text-gray-400">
                Horse
              </th>
              <SortHeader field="sire">Sire</SortHeader>
              <th className="px-3 py-3 text-left text-[11px] font-medium uppercase tracking-wider text-gray-400">
                Dam
              </th>
              <th className="px-3 py-3 text-left text-[11px] font-medium uppercase tracking-wider text-gray-400">
                Sex
              </th>
              <th className="px-3 py-3 text-left text-[11px] font-medium uppercase tracking-wider text-gray-400">
                Consignor
              </th>
              <SortHeader field="breezeTime">UT Time</SortHeader>
              <th className="px-3 py-3 text-left text-[11px] font-medium uppercase tracking-wider text-gray-400 w-10">
                UT Video
              </th>
              <th className="px-3 py-3 text-left text-[11px] font-medium uppercase tracking-wider text-gray-400">
                Status
              </th>
              <SortHeader field="price" className="text-right">
                Price
              </SortHeader>
              <th className="px-3 py-3 text-left text-[11px] font-medium uppercase tracking-wider text-gray-400">
                Assets
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-50">
            {filtered.map((hip) => (
              <tr key={hip.hipNumber} className="table-row-hover">
                <td className="px-3 py-2.5 font-mono font-semibold text-brand-600">
                  <Link
                    to={`/sale/${saleKey}/hip/${hip.hipNumber}`}
                    className="hover:underline"
                  >
                    {hip.hipNumber}
                  </Link>
                </td>
                <td className="px-3 py-2.5 text-gray-900 font-medium">
                  {hip.horseName || (
                    <span className="text-gray-400 italic">Unnamed</span>
                  )}
                </td>
                <td className="px-3 py-2.5 text-gray-700">{hip.sire}</td>
                <td className="px-3 py-2.5 text-gray-500">{hip.dam}</td>
                <td className="px-3 py-2.5 text-gray-500">
                  {sexLabel(hip.sex)}
                </td>
                <td className="px-3 py-2.5 text-gray-500 text-xs max-w-[200px] truncate">
                  {hip.consignor}
                </td>
                <td className="px-3 py-2.5 font-mono text-gray-600">
                  {hip.breezeTime
                    ? formatBreezeTime(hip.breezeTime)
                    : "—"}
                </td>
                <td className="px-3 py-2.5">
                  {(() => {
                    const videoLink = hip.videoUrl || assetIndex?.[String(hip.hipNumber)]?.video;
                    return videoLink ? (
                      <a
                        href={videoLink}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-brand-500 hover:text-brand-700 transition-colors"
                        title="Watch Under Tack Video"
                      >
                        <svg className="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
                          <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z" />
                          <circle cx="12" cy="13" r="4" />
                        </svg>
                      </a>
                    ) : "—";
                  })()}
                </td>
                <td className="px-3 py-2.5">
                  <StatusBadge status={hip.status} />
                </td>
                <td className="px-3 py-2.5 text-right font-mono font-medium text-gray-900">
                  {hip.price ? formatCurrency(hip.price) : "—"}
                </td>
                <td className="px-3 py-2.5">
                  <AssetIndicators hip={hip} assetIndex={assetIndex} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {filtered.length === 0 && (
          <div className="text-center py-12 text-gray-400">
            No hips match your filters
          </div>
        )}
      </div>
    </div>
  );
}

function AssetIndicators({ hip, assetIndex }) {
  const s3 = assetIndex?.[String(hip.hipNumber)] || {};
  const hasVideo = hip.videoUrl || s3.video;
  const hasWalk = hip.walkVideoUrl || s3.walkVideo;
  const hasPhoto = hip.photoUrl || s3.photo;
  const hasPedigree = hip.pedigreeUrl || s3.pedigree;

  return (
    <div className="flex gap-1.5">
      {hasVideo && <AssetDot label="V" title="Breeze Video" />}
      {hasWalk && <AssetDot label="W" title="Walk Video" color="sky" />}
      {hasPhoto && <AssetDot label="P" title="Photo" color="violet" />}
      {hasPedigree && <AssetDot label="D" title="Pedigree" color="amber" />}
    </div>
  );
}

function AssetDot({ label, title, color = "emerald" }) {
  const colorMap = {
    emerald: "bg-emerald-50 text-emerald-600 border-emerald-200",
    sky: "bg-sky-50 text-sky-600 border-sky-200",
    violet: "bg-violet-50 text-violet-600 border-violet-200",
    amber: "bg-amber-50 text-amber-600 border-amber-200",
  };
  return (
    <span
      title={title}
      className={`w-5 h-5 rounded text-[10px] font-bold flex items-center justify-center border ${colorMap[color]}`}
    >
      {label}
    </span>
  );
}
