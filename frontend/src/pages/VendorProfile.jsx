import { useState, useMemo } from "react";
import { useParams, Link } from "react-router-dom";
import {
  useHistoricVendors,
  useHistoricVendorBySale,
  useHistoricRecords,
} from "../hooks/useHistoricData";
import LoadingSpinner from "../components/LoadingSpinner";
import {
  formatCompact,
  formatNumber,
  formatCurrency,
  formatPercent,
} from "../lib/format";

const PAGE_SIZE = 50;

export default function VendorProfile() {
  const { vendorName } = useParams();
  const decodedName = decodeURIComponent(vendorName || "");

  const { vendors, loading: vendorsLoading } = useHistoricVendors();
  const { salesData, loading: salesLoading } = useHistoricVendorBySale();
  const { records, loading: recordsLoading, load } = useHistoricRecords();

  // Trigger records load on mount
  useState(() => { load(); });

  const vendor = useMemo(
    () => vendors.find((v) => v.vendor === decodedName) || null,
    [vendors, decodedName]
  );

  // Gather per-sale data for this vendor
  const saleSummaries = useMemo(() => {
    if (!salesData || !decodedName) return [];
    const results = [];
    for (const [saleName, vendorsList] of Object.entries(salesData)) {
      const match = vendorsList.find((v) => v.vendor === decodedName);
      if (match) results.push({ saleName, ...match });
    }
    results.sort((a, b) => b.totalRevenue - a.totalRevenue);
    return results;
  }, [salesData, decodedName]);

  // Compute overall sale aggregates
  const saleAggregates = useMemo(() => {
    if (!saleSummaries.length) return null;
    return {
      totalCataloged: saleSummaries.reduce((s, v) => s + v.cataloged, 0),
      totalSold: saleSummaries.reduce((s, v) => s + v.sold, 0),
      totalRevenue: saleSummaries.reduce((s, v) => s + v.totalRevenue, 0),
      salesCount: saleSummaries.length,
    };
  }, [saleSummaries]);

  // Filter individual records for this vendor
  const vendorRecords = useMemo(() => {
    if (!records || !decodedName) return [];
    return records.filter(
      (r) => r.vendor === decodedName
    );
  }, [records, decodedName]);

  const loading = vendorsLoading || salesLoading;

  if (loading) return <LoadingSpinner message="Loading vendor profile..." />;

  if (!vendor && saleSummaries.length === 0 && vendorRecords.length === 0) {
    return (
      <div className="space-y-4">
        <Link to="/vendors" className="text-sm text-brand-600 hover:text-brand-800">
          &larr; Back to Vendors
        </Link>
        <div className="text-center py-12 text-gray-400">
          Vendor "{decodedName}" not found
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Breadcrumb */}
      <div className="flex items-center gap-2 text-sm">
        <Link to="/vendors" className="text-gray-400 hover:text-brand-600 transition-colors">
          Vendors
        </Link>
        <span className="text-gray-300">/</span>
        <span className="text-gray-700">{decodedName}</span>
      </div>

      {/* Header */}
      <div>
        <h1 className="text-2xl font-semibold text-gray-900 tracking-tight">
          {decodedName}
        </h1>
        <p className="text-sm text-gray-500 mt-1">
          Vendor profile &middot; Historic data from USA 2YO sales (2015–2025)
        </p>
      </div>

      {/* Overall Performance */}
      {vendor && <OverallSection vendor={vendor} saleAggregates={saleAggregates} />}

      {/* Per-Sale Breakdown */}
      {saleSummaries.length > 0 && <SaleBreakdown saleSummaries={saleSummaries} />}

      {/* Individual Records */}
      <RecordsSection records={vendorRecords} loading={recordsLoading} />
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════════
   Overall Performance Section
   ═══════════════════════════════════════════════════════════════ */

function OverallSection({ vendor, saleAggregates }) {
  return (
    <div className="space-y-4">
      <h2 className="text-lg font-semibold text-gray-900">Overall Performance</h2>

      {/* Racing Performance Stats */}
      <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-3">
        <StatCard label="Runners" value={formatNumber(vendor.runners)} />
        <StatCard label="Winners" value={formatNumber(vendor.winners)} accent />
        <StatCard label="Win %" value={formatPercent(vendor.winPct, 1)} />
        <StatCard label="Stakes Winners" value={formatNumber(vendor.stakesWinners)} />
        <StatCard label="SW %" value={formatPercent(vendor.stakesWinPct, 1)} />
        <StatCard label="Graded SW" value={formatNumber(vendor.gradedStakesWinners)} />
        <StatCard label="G1 Winners" value={formatNumber(vendor.g1Winners)} accent />
      </div>

      {/* Sales Aggregates */}
      {saleAggregates && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <StatCard label="Sales Appeared" value={formatNumber(saleAggregates.salesCount)} />
          <StatCard label="Total Cataloged" value={formatNumber(saleAggregates.totalCataloged)} />
          <StatCard label="Total Sold" value={formatNumber(saleAggregates.totalSold)} />
          <StatCard label="Total Revenue" value={formatCompact(saleAggregates.totalRevenue)} accent />
        </div>
      )}
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════════
   Per-Sale Breakdown
   ═══════════════════════════════════════════════════════════════ */

function SaleBreakdown({ saleSummaries }) {
  const [sortBy, setSortBy] = useState("totalRevenue");
  const [sortDir, setSortDir] = useState("desc");

  const sorted = useMemo(() => {
    return [...saleSummaries].sort((a, b) => {
      let av = a[sortBy];
      let bv = b[sortBy];
      if (typeof av === "string") { av = av.toLowerCase(); bv = bv.toLowerCase(); }
      if (av < bv) return sortDir === "asc" ? -1 : 1;
      if (av > bv) return sortDir === "asc" ? 1 : -1;
      return 0;
    });
  }, [saleSummaries, sortBy, sortDir]);

  function handleSort(key) {
    if (sortBy === key) setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    else { setSortBy(key); setSortDir("desc"); }
  }

  return (
    <div className="space-y-4">
      <h2 className="text-lg font-semibold text-gray-900">
        Breakdown by Sale
        <span className="text-sm font-normal text-gray-400 ml-2">
          ({saleSummaries.length} {saleSummaries.length === 1 ? "sale" : "sales"})
        </span>
      </h2>

      <div className="overflow-x-auto rounded-xl border border-gray-100 bg-white shadow-[0_1px_3px_rgba(0,0,0,0.04)]">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-100">
              <SortHeader field="saleName" current={sortBy} dir={sortDir} onSort={handleSort}>Sale</SortHeader>
              <SortHeader field="cataloged" current={sortBy} dir={sortDir} onSort={handleSort} className="text-center">Cataloged</SortHeader>
              <SortHeader field="sold" current={sortBy} dir={sortDir} onSort={handleSort} className="text-center">Sold</SortHeader>
              <SortHeader field="totalRevenue" current={sortBy} dir={sortDir} onSort={handleSort} className="text-right">Revenue</SortHeader>
              <SortHeader field="avgPrice" current={sortBy} dir={sortDir} onSort={handleSort} className="text-right">Avg Price</SortHeader>
              <SortHeader field="medianPrice" current={sortBy} dir={sortDir} onSort={handleSort} className="text-right">Median</SortHeader>
              <SortHeader field="maxPrice" current={sortBy} dir={sortDir} onSort={handleSort} className="text-right">Top Price</SortHeader>
              <SortHeader field="runners" current={sortBy} dir={sortDir} onSort={handleSort} className="text-center">Runners</SortHeader>
              <SortHeader field="winners" current={sortBy} dir={sortDir} onSort={handleSort} className="text-center">Winners</SortHeader>
              <SortHeader field="stakesWinners" current={sortBy} dir={sortDir} onSort={handleSort} className="text-center">SW</SortHeader>
              <SortHeader field="gradedStakesWinners" current={sortBy} dir={sortDir} onSort={handleSort} className="text-center">GSW</SortHeader>
              <SortHeader field="g1Winners" current={sortBy} dir={sortDir} onSort={handleSort} className="text-center">G1</SortHeader>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-50">
            {sorted.map((s) => (
              <tr key={s.saleName} className="table-row-hover">
                <td className="px-3 py-2.5 font-medium text-gray-900 max-w-[220px]">
                  <div className="truncate">{s.saleName}</div>
                </td>
                <td className="px-3 py-2.5 text-center text-gray-600">{s.cataloged}</td>
                <td className="px-3 py-2.5 text-center text-gray-600">{s.sold}</td>
                <td className="px-3 py-2.5 text-right font-mono font-medium text-gray-900">
                  {formatCompact(s.totalRevenue)}
                </td>
                <td className="px-3 py-2.5 text-right font-mono text-gray-600">
                  {formatCompact(s.avgPrice)}
                </td>
                <td className="px-3 py-2.5 text-right font-mono text-gray-600">
                  {formatCompact(s.medianPrice)}
                </td>
                <td className="px-3 py-2.5 text-right font-mono font-medium text-gray-900">
                  {s.maxPrice > 0 ? formatCurrency(s.maxPrice) : "—"}
                </td>
                <td className="px-3 py-2.5 text-center font-mono text-gray-600">{s.runners}</td>
                <td className="px-3 py-2.5 text-center font-mono text-gray-600">{s.winners}</td>
                <td className="px-3 py-2.5 text-center font-mono text-gray-600">{s.stakesWinners}</td>
                <td className="px-3 py-2.5 text-center font-mono text-gray-600">{s.gradedStakesWinners}</td>
                <td className="px-3 py-2.5 text-center font-mono font-medium text-gray-900">{s.g1Winners}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════════
   Individual Records
   ═══════════════════════════════════════════════════════════════ */

function RecordsSection({ records, loading }) {
  const [sortBy, setSortBy] = useState("price");
  const [sortDir, setSortDir] = useState("desc");
  const [saleFilter, setSaleFilter] = useState("");
  const [yearFilter, setYearFilter] = useState("");
  const [page, setPage] = useState(0);

  const { saleOptions, yearOptions } = useMemo(() => {
    if (!records.length) return { saleOptions: [], yearOptions: [] };
    const sales = [...new Set(records.map((r) => r.sale).filter(Boolean))].sort();
    const years = [...new Set(records.map((r) => r.year).filter(Boolean))].sort((a, b) => b - a);
    return { saleOptions: sales, yearOptions: years };
  }, [records]);

  const filtered = useMemo(() => {
    let data = records;
    if (saleFilter) data = data.filter((r) => r.sale === saleFilter);
    if (yearFilter) data = data.filter((r) => String(r.year) === yearFilter);

    data = [...data].sort((a, b) => {
      let av = a[sortBy] ?? 0;
      let bv = b[sortBy] ?? 0;
      if (typeof av === "string") { av = av.toLowerCase(); bv = (bv || "").toLowerCase(); }
      if (av < bv) return sortDir === "asc" ? -1 : 1;
      if (av > bv) return sortDir === "asc" ? 1 : -1;
      return 0;
    });
    return data;
  }, [records, saleFilter, yearFilter, sortBy, sortDir]);

  const totalPages = Math.ceil(filtered.length / PAGE_SIZE);
  const pageData = filtered.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);

  function handleSort(key) {
    if (sortBy === key) setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    else { setSortBy(key); setSortDir("desc"); }
    setPage(0);
  }

  if (loading) return <LoadingSpinner message="Loading individual records..." />;
  if (!records.length) return null;

  const totalRevenue = filtered.reduce((s, r) => s + (r.price > 0 ? r.price : 0), 0);
  const withPrice = filtered.filter((r) => r.price > 0);
  const totalRunners = filtered.filter((r) => r.runner).length;
  const totalWinners = filtered.filter((r) => r.winner).length;
  const totalSW = filtered.filter((r) => r.stakesWinner).length;

  return (
    <div className="space-y-4">
      <h2 className="text-lg font-semibold text-gray-900">
        Individual Records
        <span className="text-sm font-normal text-gray-400 ml-2">
          ({formatNumber(records.length)} horses)
        </span>
      </h2>

      {/* Filters */}
      <div className="flex flex-wrap items-end gap-3">
        <div>
          <label className="block text-[11px] uppercase tracking-wider text-gray-400 mb-1">Sale</label>
          <select
            value={saleFilter}
            onChange={(e) => { setSaleFilter(e.target.value); setPage(0); }}
            className="bg-white border border-gray-200 rounded-lg px-3 py-2 text-sm text-gray-900 focus:outline-none focus:border-brand-400 focus:ring-2 focus:ring-brand-100"
          >
            <option value="">All Sales</option>
            {saleOptions.map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
        </div>
        <div>
          <label className="block text-[11px] uppercase tracking-wider text-gray-400 mb-1">Year</label>
          <select
            value={yearFilter}
            onChange={(e) => { setYearFilter(e.target.value); setPage(0); }}
            className="bg-white border border-gray-200 rounded-lg px-3 py-2 text-sm text-gray-900 focus:outline-none focus:border-brand-400 focus:ring-2 focus:ring-brand-100"
          >
            <option value="">All Years</option>
            {yearOptions.map((y) => (
              <option key={y} value={y}>{y}</option>
            ))}
          </select>
        </div>
        {(saleFilter || yearFilter) && (
          <button
            onClick={() => { setSaleFilter(""); setYearFilter(""); setPage(0); }}
            className="text-xs text-brand-600 hover:text-brand-800 font-medium pb-2"
          >
            Clear filters
          </button>
        )}
      </div>

      {/* Summary */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
        <StatCard label="Records" value={formatNumber(filtered.length)} />
        <StatCard label="Sold" value={formatNumber(withPrice.length)} />
        <StatCard label="Total Revenue" value={formatCompact(totalRevenue)} accent />
        <StatCard label="Avg Price" value={formatCompact(withPrice.length > 0 ? totalRevenue / withPrice.length : 0)} />
        <StatCard label="Runners" value={formatNumber(totalRunners)} />
        <StatCard label="Winners" value={formatNumber(totalWinners)} />
      </div>

      {/* Table */}
      <div className="overflow-x-auto rounded-xl border border-gray-100 bg-white shadow-[0_1px_3px_rgba(0,0,0,0.04)]">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-100">
              <SortHeader field="hip" current={sortBy} dir={sortDir} onSort={handleSort} className="text-center">Hip</SortHeader>
              <SortHeader field="name" current={sortBy} dir={sortDir} onSort={handleSort}>Horse</SortHeader>
              <SortHeader field="sex" current={sortBy} dir={sortDir} onSort={handleSort} className="text-center">Sex</SortHeader>
              <SortHeader field="sire" current={sortBy} dir={sortDir} onSort={handleSort}>Sire</SortHeader>
              <SortHeader field="dam" current={sortBy} dir={sortDir} onSort={handleSort}>Dam</SortHeader>
              <SortHeader field="price" current={sortBy} dir={sortDir} onSort={handleSort} className="text-right">Price</SortHeader>
              <SortHeader field="sale" current={sortBy} dir={sortDir} onSort={handleSort}>Sale</SortHeader>
              <SortHeader field="year" current={sortBy} dir={sortDir} onSort={handleSort} className="text-center">Year</SortHeader>
              <th className="px-3 py-3 text-center text-[11px] font-medium uppercase tracking-wider text-gray-400">Performance</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-50">
            {pageData.map((r, i) => (
              <tr key={`${r.hip}-${r.sale}-${r.year}-${i}`} className="table-row-hover">
                <td className="px-3 py-2.5 text-center font-mono text-gray-600 text-xs">{r.hip || "—"}</td>
                <td className="px-3 py-2.5 font-medium text-gray-900 max-w-[160px]">
                  <div className="truncate">{r.name || "—"}</div>
                </td>
                <td className="px-3 py-2.5 text-center text-gray-600 text-xs">{r.sex || "—"}</td>
                <td className="px-3 py-2.5 text-gray-700 max-w-[140px]">
                  <div className="truncate">{r.sire || "—"}</div>
                </td>
                <td className="px-3 py-2.5 text-gray-700 max-w-[140px]">
                  <div className="truncate">{r.dam || "—"}</div>
                </td>
                <td className="px-3 py-2.5 text-right font-mono font-medium text-gray-900">
                  {r.price > 0 ? formatCurrency(r.price) : "—"}
                </td>
                <td className="px-3 py-2.5 text-gray-500 text-xs max-w-[180px]">
                  <div className="truncate">{r.sale || "—"}</div>
                </td>
                <td className="px-3 py-2.5 text-center font-mono text-gray-600 text-xs">{r.year || "—"}</td>
                <td className="px-3 py-2.5 text-center">
                  <PerformanceBadges record={r} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {pageData.length === 0 && (
          <div className="text-center py-12 text-gray-400">No records match your filters</div>
        )}
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between">
          <span className="text-xs text-gray-400">
            Showing {page * PAGE_SIZE + 1}–{Math.min((page + 1) * PAGE_SIZE, filtered.length)} of {formatNumber(filtered.length)}
          </span>
          <div className="flex gap-1">
            <PaginationBtn onClick={() => setPage(0)} disabled={page === 0}>First</PaginationBtn>
            <PaginationBtn onClick={() => setPage((p) => p - 1)} disabled={page === 0}>Prev</PaginationBtn>
            <span className="px-3 py-1.5 text-xs text-gray-600">
              Page {page + 1} / {totalPages}
            </span>
            <PaginationBtn onClick={() => setPage((p) => p + 1)} disabled={page >= totalPages - 1}>Next</PaginationBtn>
            <PaginationBtn onClick={() => setPage(totalPages - 1)} disabled={page >= totalPages - 1}>Last</PaginationBtn>
          </div>
        </div>
      )}
    </div>
  );
}

/* ── Shared sub-components ──────────────────────────────────── */

function StatCard({ label, value, accent }) {
  return (
    <div className="rounded-xl border border-gray-100 bg-white p-4 shadow-[0_1px_3px_rgba(0,0,0,0.04)]">
      <p className="text-[10px] uppercase tracking-wider text-gray-400 mb-1">{label}</p>
      <p className={`text-lg font-semibold ${accent ? "text-brand-600" : "text-gray-800"}`}>
        {value}
      </p>
    </div>
  );
}

function SortHeader({ field, current, dir, onSort, children, className = "" }) {
  return (
    <th
      className={`px-3 py-3 text-[11px] font-medium uppercase tracking-wider text-gray-400 cursor-pointer hover:text-gray-700 select-none ${className}`}
      onClick={() => onSort(field)}
    >
      <span className="inline-flex items-center gap-1">
        {children}
        {current === field && (
          <span className="text-brand-600">{dir === "asc" ? "↑" : "↓"}</span>
        )}
      </span>
    </th>
  );
}

function PerformanceBadges({ record }) {
  const badges = [];
  if (record.g1Winner) badges.push({ label: "G1", color: "bg-purple-100 text-purple-700" });
  else if (record.gradedStakesWinner) badges.push({ label: "GSW", color: "bg-indigo-100 text-indigo-700" });
  else if (record.stakesWinner) badges.push({ label: "SW", color: "bg-blue-100 text-blue-700" });
  else if (record.winner) badges.push({ label: "W", color: "bg-emerald-100 text-emerald-700" });
  else if (record.runner) badges.push({ label: "R", color: "bg-gray-100 text-gray-600" });

  if (badges.length === 0) return <span className="text-gray-300 text-xs">—</span>;

  return (
    <div className="flex justify-center gap-1">
      {badges.map((b) => (
        <span key={b.label} className={`inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium ${b.color}`}>
          {b.label}
        </span>
      ))}
    </div>
  );
}

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
