import { useState, useEffect, useMemo } from "react";
import { Link } from "react-router-dom";
import { SALE_CATALOG, fetchSaleFromS3 } from "../lib/api";
import LoadingSpinner from "../components/LoadingSpinner";
import ErrorBanner from "../components/ErrorBanner";
import StatCard from "../components/StatCard";
import StatusBadge from "../components/StatusBadge";
import { formatNumber } from "../lib/format";

const API_BASE = "/.netlify/functions";

const ACTIVE_SALE_KEY = "obs_march_2026";

export default function UnderTack() {
  const [utData, setUtData] = useState(null);
  const [videos, setVideos] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selectedDate, setSelectedDate] = useState(null);
  const [sortField, setSortField] = useState("hip_number");
  const [sortDir, setSortDir] = useState("asc");
  const [distanceFilter, setDistanceFilter] = useState("all");

  const meta = SALE_CATALOG[ACTIVE_SALE_KEY];

  useEffect(() => {
    let cancelled = false;
    setLoading(true);

    async function load() {
      try {
        // Try S3 under-tack data first, fall back to full sale data
        const [utRes, videosRes, saleRes] = await Promise.allSettled([
          fetch(`${API_BASE}/sale-data?sale=${ACTIVE_SALE_KEY}&type=under-tack/latest`).then(r => r.ok ? r.json() : null),
          fetch(`${API_BASE}/sale-data?sale=${ACTIVE_SALE_KEY}&type=under-tack/videos`).then(r => r.ok ? r.json() : null),
          fetchSaleFromS3(ACTIVE_SALE_KEY),
        ]);

        if (cancelled) return;

        const ut = utRes.status === "fulfilled" ? utRes.value : null;
        const vids = videosRes.status === "fulfilled" ? videosRes.value : null;
        const sale = saleRes.status === "fulfilled" ? saleRes.value : null;

        if (ut && ut.hips) {
          setUtData(ut);
        } else if (sale && sale.hips) {
          // Build UT data from full sale data
          const hipsWithUt = sale.hips
            .filter(h => h.under_tack_time != null)
            .map(h => ({
              hip_number: h.hip_number,
              horse_name: h.horse_name || null,
              sex: h.sex || null,
              color: h.colour || null,
              sire: h.sire || null,
              dam: h.dam || null,
              dam_sire: h.dam_sire || null,
              consignor: h.consignor || null,
              session_number: h.session_number || null,
              ut_time: h.under_tack_time,
              ut_distance: h.under_tack_distance || null,
              ut_set: h.under_tack_set || null,
              ut_group: h.under_tack_group || null,
              ut_actual_date: h.under_tack_date || null,
              video_url: h.video_url || null,
              walk_video_url: h.walk_video_url || null,
              has_video: !!h.video_url,
              has_walk_video: !!h.walk_video_url,
            }));

          const dates = [...new Set(hipsWithUt.map(h => h.ut_actual_date).filter(Boolean))].sort();
          setUtData({
            sale_name: sale.sale_name,
            total_cataloged: sale.hips.length,
            total_breezed: hipsWithUt.length,
            ut_dates: dates,
            hips: hipsWithUt,
          });
        }

        if (vids) setVideos(vids);
      } catch (e) {
        if (!cancelled) setError(e.message);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    load();
    return () => { cancelled = true; };
  }, []);

  const filteredHips = useMemo(() => {
    if (!utData?.hips) return [];
    let hips = [...utData.hips];

    if (selectedDate && selectedDate !== "all") {
      hips = hips.filter(h => h.ut_actual_date === selectedDate);
    }

    if (distanceFilter !== "all") {
      hips = hips.filter(h => h.ut_distance === distanceFilter);
    }

    hips.sort((a, b) => {
      let va = a[sortField];
      let vb = b[sortField];
      if (va == null) return 1;
      if (vb == null) return -1;
      if (typeof va === "string") va = va.toLowerCase();
      if (typeof vb === "string") vb = vb.toLowerCase();
      if (va < vb) return sortDir === "asc" ? -1 : 1;
      if (va > vb) return sortDir === "asc" ? 1 : -1;
      return 0;
    });

    return hips;
  }, [utData, selectedDate, distanceFilter, sortField, sortDir]);

  const distances = useMemo(() => {
    if (!utData?.hips) return [];
    return [...new Set(utData.hips.map(h => h.ut_distance).filter(Boolean))].sort();
  }, [utData]);

  const dateStats = useMemo(() => {
    if (!utData?.hips) return {};
    const stats = {};
    for (const h of utData.hips) {
      const d = h.ut_actual_date || "Unknown";
      if (!stats[d]) stats[d] = { count: 0, times: [] };
      stats[d].count++;
      if (h.ut_time) stats[d].times.push(h.ut_time);
    }
    return stats;
  }, [utData]);

  function toggleSort(field) {
    if (sortField === field) {
      setSortDir(d => d === "asc" ? "desc" : "asc");
    } else {
      setSortField(field);
      setSortDir(field === "ut_time" ? "asc" : "asc");
    }
  }

  if (loading) return <LoadingSpinner message="Loading Under Tack data..." />;
  if (error) return <ErrorBanner message={error} />;
  if (!utData) return <ErrorBanner message="No Under Tack data available yet" />;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <div className="flex items-center gap-3 mb-1">
          <h1 className="text-2xl font-semibold text-gray-900 tracking-tight">
            Under Tack Show
          </h1>
          <span className="relative flex h-2.5 w-2.5">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
            <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-emerald-500" />
          </span>
        </div>
        <p className="text-sm text-gray-500 mt-1">
          {utData.sale_name || meta?.name} — Daily breeze times, videos &amp; data
        </p>
      </div>

      {/* Key stats */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <StatCard label="Cataloged" value={formatNumber(utData.total_cataloged)} />
        <StatCard label="Breezed" value={formatNumber(utData.total_breezed)} accent />
        <StatCard
          label="UT Days"
          value={formatNumber(utData.ut_dates?.length || 0)}
        />
        <StatCard
          label="Fastest"
          value={
            utData.hips.length > 0
              ? Math.min(...utData.hips.filter(h => h.ut_time).map(h => h.ut_time)).toFixed(1)
              : "—"
          }
          sub={utData.hips.length > 0 ? "seconds" : ""}
          accent
        />
      </div>

      {/* UT Videos & Links */}
      {(videos?.videos?.length > 0 || videos?.links?.length > 0) && (
        <div className="rounded-xl border border-gray-100 bg-white p-4 shadow-[0_1px_3px_rgba(0,0,0,0.04)]">
          <h3 className="text-sm font-semibold text-gray-900 mb-3">Under Tack Videos & Reports</h3>
          <div className="flex flex-wrap gap-2">
            {videos.videos?.map((v, i) => (
              <a
                key={i}
                href={v.url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-red-50 text-red-700 text-xs font-medium border border-red-200 hover:bg-red-100 transition-colors"
              >
                <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="currentColor"><path d="M19.615 3.184c-3.604-.246-11.631-.245-15.23 0-3.897.266-4.356 2.62-4.385 8.816.029 6.185.484 8.549 4.385 8.816 3.6.245 11.626.246 15.23 0 3.897-.266 4.356-2.62 4.385-8.816-.029-6.185-.484-8.549-4.385-8.816zM9 16V8l8 4-8 4z"/></svg>
                {v.text}
              </a>
            ))}
            {videos.links?.map((l, i) => (
              <a
                key={`link-${i}`}
                href={l.url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-blue-50 text-blue-700 text-xs font-medium border border-blue-200 hover:bg-blue-100 transition-colors"
              >
                <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
                {l.text}
              </a>
            ))}
          </div>
        </div>
      )}

      {/* Date selector */}
      {utData.ut_dates?.length > 0 && (
        <div className="flex flex-wrap gap-2">
          <button
            onClick={() => setSelectedDate("all")}
            className={`px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors ${
              !selectedDate || selectedDate === "all"
                ? "bg-brand-50 text-brand-700 border-brand-200"
                : "bg-white text-gray-600 border-gray-200 hover:bg-gray-50"
            }`}
          >
            All Days ({utData.total_breezed})
          </button>
          {utData.ut_dates.map(date => {
            const count = dateStats[date]?.count || 0;
            return (
              <button
                key={date}
                onClick={() => setSelectedDate(date)}
                className={`px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors ${
                  selectedDate === date
                    ? "bg-brand-50 text-brand-700 border-brand-200"
                    : "bg-white text-gray-600 border-gray-200 hover:bg-gray-50"
                }`}
              >
                {date} ({count})
              </button>
            );
          })}
        </div>
      )}

      {/* Distance filter */}
      {distances.length > 1 && (
        <div className="flex items-center gap-2">
          <span className="text-xs text-gray-500">Distance:</span>
          <select
            value={distanceFilter}
            onChange={e => setDistanceFilter(e.target.value)}
            className="text-xs border border-gray-200 rounded-lg px-2 py-1 bg-white text-gray-700"
          >
            <option value="all">All</option>
            {distances.map(d => (
              <option key={d} value={d}>{d}</option>
            ))}
          </select>
        </div>
      )}

      {/* Breeze table */}
      <div className="rounded-xl border border-gray-100 bg-white shadow-[0_1px_3px_rgba(0,0,0,0.04)] overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-100 bg-gray-50/50">
                {[
                  { key: "hip_number", label: "Hip" },
                  { key: "sire", label: "Sire" },
                  { key: "dam", label: "Dam" },
                  { key: "sex", label: "Sex" },
                  { key: "consignor", label: "Consignor" },
                  { key: "ut_time", label: "Time" },
                  { key: "ut_distance", label: "Dist" },
                  { key: "ut_set", label: "Set" },
                  { key: "ut_actual_date", label: "Date" },
                ].map(col => (
                  <th
                    key={col.key}
                    onClick={() => toggleSort(col.key)}
                    className="px-3 py-2.5 text-left text-[11px] font-semibold uppercase tracking-wider text-gray-500 cursor-pointer hover:text-gray-900 select-none"
                  >
                    {col.label}
                    {sortField === col.key && (
                      <span className="ml-1">{sortDir === "asc" ? "\u25B2" : "\u25BC"}</span>
                    )}
                  </th>
                ))}
                <th className="px-3 py-2.5 text-left text-[11px] font-semibold uppercase tracking-wider text-gray-500">
                  Media
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50">
              {filteredHips.map(hip => (
                <tr key={hip.hip_number} className="hover:bg-gray-50/50 transition-colors">
                  <td className="px-3 py-2">
                    <Link
                      to={`/sale/${ACTIVE_SALE_KEY}/hip/${hip.hip_number}`}
                      className="font-mono font-bold text-brand-600 hover:text-brand-700"
                    >
                      {hip.hip_number}
                    </Link>
                  </td>
                  <td className="px-3 py-2 text-gray-900 font-medium">{hip.sire || "—"}</td>
                  <td className="px-3 py-2 text-gray-600">{hip.dam || "—"}</td>
                  <td className="px-3 py-2 text-gray-600">{hip.sex || "—"}</td>
                  <td className="px-3 py-2 text-gray-600 max-w-[160px] truncate">{hip.consignor || "—"}</td>
                  <td className="px-3 py-2">
                    <span className={`font-mono font-bold ${
                      hip.ut_time && hip.ut_time <= 10.0
                        ? "text-emerald-600"
                        : hip.ut_time && hip.ut_time <= 10.2
                        ? "text-brand-600"
                        : "text-gray-900"
                    }`}>
                      {hip.ut_time != null ? hip.ut_time.toFixed(1) : "—"}
                    </span>
                  </td>
                  <td className="px-3 py-2 text-gray-600">{hip.ut_distance || "—"}</td>
                  <td className="px-3 py-2 text-gray-600">{hip.ut_set || "—"}</td>
                  <td className="px-3 py-2 text-gray-500 text-xs">{hip.ut_actual_date || "—"}</td>
                  <td className="px-3 py-2">
                    <div className="flex gap-1">
                      {hip.video_url && (
                        <a
                          href={hip.video_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="w-6 h-6 rounded flex items-center justify-center bg-emerald-50 text-emerald-600 border border-emerald-200 hover:bg-emerald-100 transition-colors"
                          title="Breeze video"
                        >
                          <svg className="w-3 h-3" viewBox="0 0 24 24" fill="currentColor"><polygon points="5 3 19 12 5 21 5 3"/></svg>
                        </a>
                      )}
                      {hip.walk_video_url && (
                        <a
                          href={hip.walk_video_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="w-6 h-6 rounded flex items-center justify-center bg-sky-50 text-sky-600 border border-sky-200 hover:bg-sky-100 transition-colors"
                          title="Walk video"
                        >
                          <span className="text-[9px] font-bold">W</span>
                        </a>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {filteredHips.length === 0 && (
          <div className="p-8 text-center text-gray-400 text-sm">
            No breeze data available for the selected filters
          </div>
        )}
        <div className="px-4 py-2 border-t border-gray-100 bg-gray-50/50 text-xs text-gray-500">
          Showing {filteredHips.length} of {utData.total_breezed} breezed hips
          {utData.fetched_at && (
            <span className="ml-2">
              &middot; Updated {new Date(utData.fetched_at).toLocaleString()}
            </span>
          )}
        </div>
      </div>
    </div>
  );
}
