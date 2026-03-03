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
  { key: "breezeTime", label: "Breeze" },
  { key: "sire", label: "Sire" },
];

export default function HipTable({ hips, saleId }) {
  const [sortBy, setSortBy] = useState("hipNumber");
  const [sortDir, setSortDir] = useState("asc");
  const [filter, setFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");

  const filtered = useMemo(() => {
    let list = [...hips];

    // Status filter
    if (statusFilter !== "all") {
      list = list.filter((h) => h.status === statusFilter);
    }

    // Text filter
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

    // Sort
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
      className={`px-3 py-2.5 text-left text-xs font-semibold uppercase tracking-wider text-slate-400 cursor-pointer hover:text-slate-200 select-none ${className}`}
      onClick={() => handleSort(field)}
    >
      <span className="flex items-center gap-1">
        {children}
        {sortBy === field && (
          <span className="text-brand-400">
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
          className="flex-1 min-w-[200px] bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white placeholder:text-slate-500 focus:outline-none focus:border-brand-500/50 focus:ring-1 focus:ring-brand-500/25"
        />
        <div className="flex gap-1">
          {["all", "sold", "rna", "out", "pending"].map((s) => (
            <button
              key={s}
              onClick={() => setStatusFilter(s)}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium capitalize transition-colors ${
                statusFilter === s
                  ? "bg-brand-500/20 text-brand-400 border border-brand-500/30"
                  : "text-slate-400 hover:text-slate-200 border border-slate-700 hover:border-slate-600"
              }`}
            >
              {s}
            </button>
          ))}
        </div>
        <span className="text-xs text-slate-500">
          {filtered.length} of {hips.length} hips
        </span>
      </div>

      {/* Table */}
      <div className="overflow-x-auto rounded-xl border border-slate-800">
        <table className="w-full text-sm">
          <thead className="bg-slate-900/80">
            <tr>
              <SortHeader field="hipNumber" className="w-16">
                Hip
              </SortHeader>
              <th className="px-3 py-2.5 text-left text-xs font-semibold uppercase tracking-wider text-slate-400">
                Horse
              </th>
              <SortHeader field="sire">Sire</SortHeader>
              <th className="px-3 py-2.5 text-left text-xs font-semibold uppercase tracking-wider text-slate-400">
                Dam
              </th>
              <th className="px-3 py-2.5 text-left text-xs font-semibold uppercase tracking-wider text-slate-400">
                Sex
              </th>
              <th className="px-3 py-2.5 text-left text-xs font-semibold uppercase tracking-wider text-slate-400">
                Consignor
              </th>
              <SortHeader field="breezeTime">Breeze</SortHeader>
              <th className="px-3 py-2.5 text-left text-xs font-semibold uppercase tracking-wider text-slate-400">
                Status
              </th>
              <SortHeader field="price" className="text-right">
                Price
              </SortHeader>
              <th className="px-3 py-2.5 text-left text-xs font-semibold uppercase tracking-wider text-slate-400">
                Assets
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800/60">
            {filtered.map((hip) => (
              <tr key={hip.hipNumber} className="table-row-hover">
                <td className="px-3 py-2.5 font-mono font-semibold text-brand-400">
                  <Link
                    to={`/sale/${saleId}/hip/${hip.hipNumber}`}
                    className="hover:underline"
                  >
                    {hip.hipNumber}
                  </Link>
                </td>
                <td className="px-3 py-2.5 text-white font-medium">
                  {hip.horseName || (
                    <span className="text-slate-500 italic">Unnamed</span>
                  )}
                </td>
                <td className="px-3 py-2.5 text-slate-300">{hip.sire}</td>
                <td className="px-3 py-2.5 text-slate-400">{hip.dam}</td>
                <td className="px-3 py-2.5 text-slate-400">
                  {sexLabel(hip.sex)}
                </td>
                <td className="px-3 py-2.5 text-slate-400 text-xs max-w-[200px] truncate">
                  {hip.consignor}
                </td>
                <td className="px-3 py-2.5 font-mono text-slate-300">
                  {hip.breezeTime
                    ? `${formatBreezeTime(hip.breezeTime)} (${hip.breezeDistance})`
                    : "—"}
                </td>
                <td className="px-3 py-2.5">
                  <StatusBadge status={hip.status} />
                </td>
                <td className="px-3 py-2.5 text-right font-mono font-medium text-white">
                  {hip.price ? formatCurrency(hip.price) : "—"}
                </td>
                <td className="px-3 py-2.5">
                  <div className="flex gap-1.5">
                    {hip.videoUrl && (
                      <AssetDot label="V" title="Breeze Video" />
                    )}
                    {hip.walkVideoUrl && (
                      <AssetDot label="W" title="Walk Video" color="sky" />
                    )}
                    {hip.photoUrl && (
                      <AssetDot label="P" title="Photo" color="violet" />
                    )}
                    {hip.pedigreeUrl && (
                      <AssetDot label="D" title="Pedigree" color="amber" />
                    )}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {filtered.length === 0 && (
          <div className="text-center py-12 text-slate-500">
            No hips match your filters
          </div>
        )}
      </div>
    </div>
  );
}

function AssetDot({ label, title, color = "emerald" }) {
  const colorMap = {
    emerald: "bg-emerald-500/20 text-emerald-400 border-emerald-500/30",
    sky: "bg-sky-500/20 text-sky-400 border-sky-500/30",
    violet: "bg-violet-500/20 text-violet-400 border-violet-500/30",
    amber: "bg-amber-500/20 text-amber-400 border-amber-500/30",
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
