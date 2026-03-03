import { useState, useMemo } from "react";
import { useParams, useNavigate } from "react-router-dom";
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

const TABS = [
  { key: "overall", path: "/vendors", label: "Overall Performance" },
  { key: "by-sale", path: "/vendors/by-sale", label: "By Sale" },
  { key: "records", path: "/vendors/records", label: "Sale Records" },
];

export default function Vendors() {
  const { tab } = useParams();
  const navigate = useNavigate();
  const activeTab = tab || "overall";

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-semibold text-gray-900 tracking-tight">
          Vendor Performance
        </h1>
        <p className="text-sm text-gray-500 mt-1">
          Historic consignor performance data from USA 2YO sales (2015–2025)
        </p>
      </div>

      {/* Tab bar */}
      <div className="flex gap-1 border-b border-gray-200">
        {TABS.map((tab) => (
          <button
            key={tab.key}
            onClick={() => navigate(tab.path)}
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
      {activeTab === "overall" && <OverallTab />}
      {activeTab === "by-sale" && <BySaleTab />}
      {activeTab === "records" && <RecordsTab />}
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════════
   TAB 1 — Overall Vendor Performance
   ═══════════════════════════════════════════════════════════════ */

function OverallTab() {
  const { vendors, grandTotal, loading } = useHistoricVendors();
  const [sortBy, setSortBy] = useState("runners");
  const [sortDir, setSortDir] = useState("desc");
  const [filter, setFilter] = useState("");

  const sorted = useMemo(() => {
    if (!vendors.length) return [];
    return [...vendors]
      .filter(
        (v) => !filter || v.vendor.toLowerCase().includes(filter.toLowerCase())
      )
      .sort((a, b) => {
        let av = a[sortBy];
        let bv = b[sortBy];
        if (typeof av === "string") { av = av.toLowerCase(); bv = bv.toLowerCase(); }
        if (av < bv) return sortDir === "asc" ? -1 : 1;
        if (av > bv) return sortDir === "asc" ? 1 : -1;
        return 0;
      });
  }, [vendors, sortBy, sortDir, filter]);

  function handleSort(key) {
    if (sortBy === key) setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    else { setSortBy(key); setSortDir("desc"); }
  }

  if (loading) return <LoadingSpinner message="Loading vendor data..." />;

  return (
    <div className="space-y-4">
      {/* Summary stats */}
      {grandTotal && (
        <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-3">
          <StatCard label="Vendors" value={formatNumber(vendors.length)} />
          <StatCard label="Runners" value={formatNumber(grandTotal.runners)} />
          <StatCard label="Winners" value={formatNumber(grandTotal.winners)} accent />
          <StatCard label="Win %" value={formatPercent(grandTotal.winPct, 1)} />
          <StatCard label="Stakes Winners" value={formatNumber(grandTotal.stakesWinners)} />
          <StatCard label="Graded SW" value={formatNumber(grandTotal.gradedStakesWinners)} />
          <StatCard label="G1 Winners" value={formatNumber(grandTotal.g1Winners)} accent />
        </div>
      )}

      {/* Search */}
      <div className="flex items-center gap-3">
        <input
          type="text"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          placeholder="Search vendors..."
          className="flex-1 max-w-sm bg-white border border-gray-200 rounded-lg px-3 py-2 text-sm text-gray-900 placeholder:text-gray-400 focus:outline-none focus:border-brand-400 focus:ring-2 focus:ring-brand-100 transition-shadow"
        />
        <span className="text-xs text-gray-400">{sorted.length} vendors</span>
      </div>

      {/* Table */}
      <div className="overflow-x-auto rounded-xl border border-gray-100 bg-white shadow-[0_1px_3px_rgba(0,0,0,0.04)]">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-100">
              <th className="px-3 py-3 text-left text-[11px] font-medium uppercase tracking-wider text-gray-400">
                #
              </th>
              <SortHeader field="vendor" current={sortBy} dir={sortDir} onSort={handleSort}>
                Vendor
              </SortHeader>
              <SortHeader field="runners" current={sortBy} dir={sortDir} onSort={handleSort} className="text-center">
                Runners
              </SortHeader>
              <SortHeader field="winners" current={sortBy} dir={sortDir} onSort={handleSort} className="text-center">
                Winners
              </SortHeader>
              <SortHeader field="winPct" current={sortBy} dir={sortDir} onSort={handleSort} className="text-right">
                Win %
              </SortHeader>
              <SortHeader field="stakesWinners" current={sortBy} dir={sortDir} onSort={handleSort} className="text-center">
                SW
              </SortHeader>
              <SortHeader field="stakesWinPct" current={sortBy} dir={sortDir} onSort={handleSort} className="text-right">
                SW %
              </SortHeader>
              <SortHeader field="gradedStakesWinners" current={sortBy} dir={sortDir} onSort={handleSort} className="text-center">
                GSW
              </SortHeader>
              <SortHeader field="gradedStakesWinPct" current={sortBy} dir={sortDir} onSort={handleSort} className="text-right">
                GSW %
              </SortHeader>
              <SortHeader field="g1Winners" current={sortBy} dir={sortDir} onSort={handleSort} className="text-center">
                G1
              </SortHeader>
              <SortHeader field="g1WinPct" current={sortBy} dir={sortDir} onSort={handleSort} className="text-right">
                G1 %
              </SortHeader>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-50">
            {sorted.map((v, i) => (
              <tr key={v.vendor} className="table-row-hover">
                <td className="px-3 py-2.5 font-mono text-gray-400 text-xs">{i + 1}</td>
                <td className="px-3 py-2.5 font-medium text-gray-900 max-w-[220px]">
                  <div className="truncate">{v.vendor}</div>
                </td>
                <td className="px-3 py-2.5 text-center font-mono text-gray-600">{v.runners}</td>
                <td className="px-3 py-2.5 text-center font-mono text-gray-600">{v.winners}</td>
                <td className="px-3 py-2.5 text-right">
                  <WinPctBadge value={v.winPct} />
                </td>
                <td className="px-3 py-2.5 text-center font-mono text-gray-600">{v.stakesWinners}</td>
                <td className="px-3 py-2.5 text-right font-mono text-gray-500 text-xs">{formatPercent(v.stakesWinPct, 1)}</td>
                <td className="px-3 py-2.5 text-center font-mono text-gray-600">{v.gradedStakesWinners}</td>
                <td className="px-3 py-2.5 text-right font-mono text-gray-500 text-xs">{formatPercent(v.gradedStakesWinPct, 1)}</td>
                <td className="px-3 py-2.5 text-center font-mono font-medium text-gray-900">{v.g1Winners}</td>
                <td className="px-3 py-2.5 text-right font-mono text-gray-500 text-xs">{formatPercent(v.g1WinPct, 1)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {sorted.length === 0 && (
          <div className="text-center py-12 text-gray-400">No vendors match your search</div>
        )}
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════════
   TAB 2 — Vendor Stats By Sale
   ═══════════════════════════════════════════════════════════════ */

function BySaleTab() {
  const { salesData, saleNames, loading } = useHistoricVendorBySale();
  const [selectedSale, setSelectedSale] = useState("");
  const [sortBy, setSortBy] = useState("totalRevenue");
  const [sortDir, setSortDir] = useState("desc");
  const [filter, setFilter] = useState("");

  // Set default selected sale once data loads
  const effectiveSale = selectedSale || (saleNames.length > 0 ? saleNames[0] : "");
  const vendors = salesData[effectiveSale] || [];

  const sorted = useMemo(() => {
    return [...vendors]
      .filter(
        (v) => !filter || v.vendor.toLowerCase().includes(filter.toLowerCase())
      )
      .sort((a, b) => {
        let av = a[sortBy];
        let bv = b[sortBy];
        if (typeof av === "string") { av = av.toLowerCase(); bv = bv.toLowerCase(); }
        if (av < bv) return sortDir === "asc" ? -1 : 1;
        if (av > bv) return sortDir === "asc" ? 1 : -1;
        return 0;
      });
  }, [vendors, sortBy, sortDir, filter]);

  function handleSort(key) {
    if (sortBy === key) setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    else { setSortBy(key); setSortDir("desc"); }
  }

  if (loading) return <LoadingSpinner message="Loading sale data..." />;

  const totalRevenue = vendors.reduce((s, v) => s + v.totalRevenue, 0);
  const totalSold = vendors.reduce((s, v) => s + v.sold, 0);
  const totalCataloged = vendors.reduce((s, v) => s + v.cataloged, 0);
  const totalRunners = vendors.reduce((s, v) => s + v.runners, 0);
  const totalWinners = vendors.reduce((s, v) => s + v.winners, 0);
  const totalSW = vendors.reduce((s, v) => s + v.stakesWinners, 0);
  const totalGSW = vendors.reduce((s, v) => s + v.gradedStakesWinners, 0);
  const totalG1 = vendors.reduce((s, v) => s + v.g1Winners, 0);

  return (
    <div className="space-y-4">
      {/* Sale selector */}
      <div className="flex flex-wrap items-center gap-3">
        <label className="text-sm font-medium text-gray-700">Sale:</label>
        <select
          value={effectiveSale}
          onChange={(e) => { setSelectedSale(e.target.value); setFilter(""); }}
          className="bg-white border border-gray-200 rounded-lg px-3 py-2 text-sm text-gray-900 focus:outline-none focus:border-brand-400 focus:ring-2 focus:ring-brand-100 max-w-lg"
        >
          {saleNames.map((name) => (
            <option key={name} value={name}>{name}</option>
          ))}
        </select>
      </div>

      {/* Summary */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-9 gap-3">
        <StatCard label="Vendors" value={formatNumber(vendors.length)} />
        <StatCard label="Cataloged" value={formatNumber(totalCataloged)} />
        <StatCard label="Sold" value={formatNumber(totalSold)} />
        <StatCard label="Revenue" value={formatCompact(totalRevenue)} accent />
        <StatCard label="Runners" value={formatNumber(totalRunners)} />
        <StatCard label="Winners" value={formatNumber(totalWinners)} />
        <StatCard label="Stakes Winners" value={formatNumber(totalSW)} />
        <StatCard label="Graded SW" value={formatNumber(totalGSW)} />
        <StatCard label="G1 Winners" value={formatNumber(totalG1)} accent />
      </div>

      {/* Filter */}
      <div className="flex items-center gap-3">
        <input
          type="text"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          placeholder="Search vendors..."
          className="flex-1 max-w-sm bg-white border border-gray-200 rounded-lg px-3 py-2 text-sm text-gray-900 placeholder:text-gray-400 focus:outline-none focus:border-brand-400 focus:ring-2 focus:ring-brand-100 transition-shadow"
        />
        <span className="text-xs text-gray-400">{sorted.length} vendors</span>
      </div>

      {/* Table */}
      <div className="overflow-x-auto rounded-xl border border-gray-100 bg-white shadow-[0_1px_3px_rgba(0,0,0,0.04)]">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-100">
              <th className="px-3 py-3 text-left text-[11px] font-medium uppercase tracking-wider text-gray-400">#</th>
              <SortHeader field="vendor" current={sortBy} dir={sortDir} onSort={handleSort}>Vendor</SortHeader>
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
            {sorted.map((v, i) => (
              <tr key={v.vendor} className="table-row-hover">
                <td className="px-3 py-2.5 font-mono text-gray-400 text-xs">{i + 1}</td>
                <td className="px-3 py-2.5 font-medium text-gray-900 max-w-[200px]">
                  <div className="truncate">{v.vendor}</div>
                </td>
                <td className="px-3 py-2.5 text-center text-gray-600">{v.cataloged}</td>
                <td className="px-3 py-2.5 text-center text-gray-600">{v.sold}</td>
                <td className="px-3 py-2.5 text-right font-mono font-medium text-gray-900">
                  {formatCompact(v.totalRevenue)}
                </td>
                <td className="px-3 py-2.5 text-right font-mono text-gray-600">
                  {formatCompact(v.avgPrice)}
                </td>
                <td className="px-3 py-2.5 text-right font-mono text-gray-600">
                  {formatCompact(v.medianPrice)}
                </td>
                <td className="px-3 py-2.5 text-right font-mono font-medium text-gray-900">
                  {v.maxPrice > 0 ? formatCurrency(v.maxPrice) : "—"}
                </td>
                <td className="px-3 py-2.5 text-center font-mono text-gray-600">{v.runners}</td>
                <td className="px-3 py-2.5 text-center font-mono text-gray-600">{v.winners}</td>
                <td className="px-3 py-2.5 text-center font-mono text-gray-600">{v.stakesWinners}</td>
                <td className="px-3 py-2.5 text-center font-mono text-gray-600">{v.gradedStakesWinners}</td>
                <td className="px-3 py-2.5 text-center font-mono font-medium text-gray-900">{v.g1Winners}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {sorted.length === 0 && (
          <div className="text-center py-12 text-gray-400">No vendors match your search</div>
        )}
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════════
   TAB 3 — Historic Sale Records
   ═══════════════════════════════════════════════════════════════ */

const PAGE_SIZE = 50;

function RecordsTab() {
  const { records, loading, error, load } = useHistoricRecords();
  const [vendorFilter, setVendorFilter] = useState("");
  const [saleFilter, setSaleFilter] = useState("");
  const [yearFilter, setYearFilter] = useState("");
  const [sireFilter, setSireFilter] = useState("");
  const [sortBy, setSortBy] = useState("price");
  const [sortDir, setSortDir] = useState("desc");
  const [page, setPage] = useState(0);

  // Load data on first render of this tab
  useState(() => { load(); });

  const { saleOptions, yearOptions } = useMemo(() => {
    if (!records) return { saleOptions: [], yearOptions: [] };
    const sales = [...new Set(records.map((r) => r.sale).filter(Boolean))].sort();
    const years = [...new Set(records.map((r) => r.year).filter(Boolean))].sort((a, b) => b - a);
    return { saleOptions: sales, yearOptions: years };
  }, [records]);

  const filtered = useMemo(() => {
    if (!records) return [];
    let data = records;
    if (vendorFilter) data = data.filter((r) => r.vendor?.toLowerCase().includes(vendorFilter.toLowerCase()));
    if (saleFilter) data = data.filter((r) => r.sale === saleFilter);
    if (yearFilter) data = data.filter((r) => String(r.year) === yearFilter);
    if (sireFilter) data = data.filter((r) => r.sire?.toLowerCase().includes(sireFilter.toLowerCase()));

    data = [...data].sort((a, b) => {
      let av = a[sortBy] ?? 0;
      let bv = b[sortBy] ?? 0;
      if (typeof av === "string") { av = av.toLowerCase(); bv = (bv || "").toLowerCase(); }
      if (av < bv) return sortDir === "asc" ? -1 : 1;
      if (av > bv) return sortDir === "asc" ? 1 : -1;
      return 0;
    });
    return data;
  }, [records, vendorFilter, saleFilter, yearFilter, sireFilter, sortBy, sortDir]);

  const totalPages = Math.ceil(filtered.length / PAGE_SIZE);
  const pageData = filtered.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);

  function handleSort(key) {
    if (sortBy === key) setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    else { setSortBy(key); setSortDir("desc"); }
    setPage(0);
  }

  function resetFilters() {
    setVendorFilter("");
    setSaleFilter("");
    setYearFilter("");
    setSireFilter("");
    setPage(0);
  }

  if (loading || !records) return <LoadingSpinner message="Loading historic records..." />;
  if (error) return <div className="text-red-500 text-sm">Error loading data: {error.message}</div>;

  // Summary of filtered data
  const totalRevenue = filtered.reduce((s, r) => s + (r.price || 0), 0);
  const withPrice = filtered.filter((r) => r.price > 0);
  const totalRunners = filtered.filter((r) => r.runner).length;
  const totalWinners = filtered.filter((r) => r.winner).length;
  const totalSW = filtered.filter((r) => r.stakesWinner).length;

  return (
    <div className="space-y-4">
      {/* Filters */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <div>
          <label className="block text-[11px] uppercase tracking-wider text-gray-400 mb-1">Vendor</label>
          <input
            type="text"
            value={vendorFilter}
            onChange={(e) => { setVendorFilter(e.target.value); setPage(0); }}
            placeholder="Filter by vendor..."
            className="w-full bg-white border border-gray-200 rounded-lg px-3 py-2 text-sm text-gray-900 placeholder:text-gray-400 focus:outline-none focus:border-brand-400 focus:ring-2 focus:ring-brand-100"
          />
        </div>
        <div>
          <label className="block text-[11px] uppercase tracking-wider text-gray-400 mb-1">Sire</label>
          <input
            type="text"
            value={sireFilter}
            onChange={(e) => { setSireFilter(e.target.value); setPage(0); }}
            placeholder="Filter by sire..."
            className="w-full bg-white border border-gray-200 rounded-lg px-3 py-2 text-sm text-gray-900 placeholder:text-gray-400 focus:outline-none focus:border-brand-400 focus:ring-2 focus:ring-brand-100"
          />
        </div>
        <div>
          <label className="block text-[11px] uppercase tracking-wider text-gray-400 mb-1">Sale</label>
          <select
            value={saleFilter}
            onChange={(e) => { setSaleFilter(e.target.value); setPage(0); }}
            className="w-full bg-white border border-gray-200 rounded-lg px-3 py-2 text-sm text-gray-900 focus:outline-none focus:border-brand-400 focus:ring-2 focus:ring-brand-100"
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
            className="w-full bg-white border border-gray-200 rounded-lg px-3 py-2 text-sm text-gray-900 focus:outline-none focus:border-brand-400 focus:ring-2 focus:ring-brand-100"
          >
            <option value="">All Years</option>
            {yearOptions.map((y) => (
              <option key={y} value={y}>{y}</option>
            ))}
          </select>
        </div>
      </div>

      {(vendorFilter || saleFilter || yearFilter || sireFilter) && (
        <button
          onClick={resetFilters}
          className="text-xs text-brand-600 hover:text-brand-800 font-medium"
        >
          Clear all filters
        </button>
      )}

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
              <SortHeader field="vendor" current={sortBy} dir={sortDir} onSort={handleSort}>Vendor</SortHeader>
              <SortHeader field="price" current={sortBy} dir={sortDir} onSort={handleSort} className="text-right">Price</SortHeader>
              <SortHeader field="sale" current={sortBy} dir={sortDir} onSort={handleSort}>Sale</SortHeader>
              <SortHeader field="year" current={sortBy} dir={sortDir} onSort={handleSort} className="text-center">Year</SortHeader>
              <th className="px-3 py-3 text-center text-[11px] font-medium uppercase tracking-wider text-gray-400">Performance</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-50">
            {pageData.map((r, i) => (
              <tr key={`${r.hip}-${r.sale}-${i}`} className="table-row-hover">
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
                <td className="px-3 py-2.5 text-gray-700 max-w-[160px]">
                  <div className="truncate">{r.vendor || "—"}</div>
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

function WinPctBadge({ value }) {
  const color = value >= 65
    ? "text-emerald-600"
    : value >= 50
      ? "text-amber-600"
      : "text-red-500";
  return <span className={`text-xs font-medium ${color}`}>{formatPercent(value, 1)}</span>;
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
