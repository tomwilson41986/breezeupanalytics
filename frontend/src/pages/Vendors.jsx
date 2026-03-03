import { useState, useEffect } from "react";
import {
  SALE_CATALOG,
  fetchSaleFromS3,
  parseS3SaleResponse,
} from "../lib/api";
import LoadingSpinner from "../components/LoadingSpinner";
import { formatCompact, formatNumber, formatCurrency } from "../lib/format";

export default function Vendors() {
  const [vendors, setVendors] = useState(null);
  const [loading, setLoading] = useState(true);
  const [sortBy, setSortBy] = useState("totalRevenue");
  const [sortDir, setSortDir] = useState("desc");
  const [filter, setFilter] = useState("");

  useEffect(() => {
    async function loadVendorData() {
      // Load all sales that have data
      const dataSales = Object.entries(SALE_CATALOG).filter(
        ([, m]) => m.hasData
      );

      const results = await Promise.allSettled(
        dataSales.map(async ([key, meta]) => {
          const res = await fetchSaleFromS3(key);
          if (res?.hips) {
            const parsed = parseS3SaleResponse(res);
            return { ...parsed, saleName: meta.name, saleKey: key };
          }
          return null;
        })
      );

      // Aggregate consignor data across all sales
      const consignorMap = {};
      for (const r of results) {
        const sale = r.status === "fulfilled" ? r.value : null;
        if (!sale) continue;

        for (const hip of sale.hips) {
          const name = hip.consignor;
          if (name === "—") continue;

          if (!consignorMap[name]) {
            consignorMap[name] = {
              name,
              hipCount: 0,
              soldCount: 0,
              rnaCount: 0,
              outCount: 0,
              totalRevenue: 0,
              prices: [],
              maxPrice: 0,
              sales: new Set(),
              topHip: null,
            };
          }

          const v = consignorMap[name];
          v.hipCount++;
          v.sales.add(sale.saleName);

          if (hip.status === "sold" && hip.price) {
            v.soldCount++;
            v.totalRevenue += hip.price;
            v.prices.push(hip.price);
            if (hip.price > v.maxPrice) {
              v.maxPrice = hip.price;
              v.topHip = { number: hip.hipNumber, sire: hip.sire, price: hip.price };
            }
          } else if (hip.status === "rna") {
            v.rnaCount++;
          } else if (hip.status === "out") {
            v.outCount++;
          }
        }
      }

      const vendorList = Object.values(consignorMap)
        .map((v) => ({
          ...v,
          avgPrice: v.soldCount > 0 ? v.totalRevenue / v.soldCount : 0,
          medianPrice: getMedian(v.prices),
          clearanceRate:
            v.soldCount + v.rnaCount > 0
              ? (v.soldCount / (v.soldCount + v.rnaCount)) * 100
              : 0,
          saleCount: v.sales.size,
        }))
        .sort((a, b) => b.totalRevenue - a.totalRevenue);

      setVendors(vendorList);
      setLoading(false);
    }

    loadVendorData();
  }, []);

  function handleSort(key) {
    if (sortBy === key) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortBy(key);
      setSortDir("desc");
    }
  }

  const sorted = vendors
    ? [...vendors]
        .filter(
          (v) =>
            !filter || v.name.toLowerCase().includes(filter.toLowerCase())
        )
        .sort((a, b) => {
          let av = a[sortBy];
          let bv = b[sortBy];
          if (av == null) return 1;
          if (bv == null) return -1;
          if (typeof av === "string") av = av.toLowerCase();
          if (typeof bv === "string") bv = bv.toLowerCase();
          if (av < bv) return sortDir === "asc" ? -1 : 1;
          if (av > bv) return sortDir === "asc" ? 1 : -1;
          return 0;
        })
    : [];

  if (loading) return <LoadingSpinner message="Loading vendor data..." />;

  const totalVendors = vendors?.length || 0;
  const totalRevenue = vendors?.reduce((s, v) => s + v.totalRevenue, 0) || 0;
  const totalSold = vendors?.reduce((s, v) => s + v.soldCount, 0) || 0;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-semibold text-gray-900 tracking-tight">
          Vendors
        </h1>
        <p className="text-sm text-gray-500 mt-1">
          Consignor performance data aggregated across all sales with available
          data
        </p>
      </div>

      {/* Summary stats */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <StatCard label="Total Vendors" value={formatNumber(totalVendors)} />
        <StatCard
          label="Horses Sold"
          value={formatNumber(totalSold)}
        />
        <StatCard
          label="Combined Revenue"
          value={formatCompact(totalRevenue)}
          accent
        />
        <StatCard
          label="Avg Sale Price"
          value={formatCompact(totalSold > 0 ? totalRevenue / totalSold : 0)}
        />
      </div>

      {/* Search */}
      <div className="flex items-center gap-3">
        <input
          type="text"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          placeholder="Search vendors..."
          className="flex-1 max-w-sm bg-white border border-gray-200 rounded-lg px-3 py-2 text-sm text-gray-900 placeholder:text-gray-400 focus:outline-none focus:border-brand-400 focus:ring-2 focus:ring-brand-100 transition-shadow"
        />
        <span className="text-xs text-gray-400">
          {sorted.length} vendors
        </span>
      </div>

      {/* Vendor table */}
      <div className="overflow-x-auto rounded-xl border border-gray-100 bg-white shadow-[0_1px_3px_rgba(0,0,0,0.04)]">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-100">
              <th className="px-3 py-3 text-left text-[11px] font-medium uppercase tracking-wider text-gray-400">
                #
              </th>
              <SortHeader
                field="name"
                current={sortBy}
                dir={sortDir}
                onSort={handleSort}
              >
                Vendor
              </SortHeader>
              <SortHeader
                field="hipCount"
                current={sortBy}
                dir={sortDir}
                onSort={handleSort}
                className="text-center"
              >
                Hips
              </SortHeader>
              <SortHeader
                field="soldCount"
                current={sortBy}
                dir={sortDir}
                onSort={handleSort}
                className="text-center"
              >
                Sold
              </SortHeader>
              <SortHeader
                field="clearanceRate"
                current={sortBy}
                dir={sortDir}
                onSort={handleSort}
                className="text-right"
              >
                Clearance
              </SortHeader>
              <SortHeader
                field="totalRevenue"
                current={sortBy}
                dir={sortDir}
                onSort={handleSort}
                className="text-right"
              >
                Revenue
              </SortHeader>
              <SortHeader
                field="avgPrice"
                current={sortBy}
                dir={sortDir}
                onSort={handleSort}
                className="text-right"
              >
                Avg Price
              </SortHeader>
              <SortHeader
                field="medianPrice"
                current={sortBy}
                dir={sortDir}
                onSort={handleSort}
                className="text-right"
              >
                Median
              </SortHeader>
              <SortHeader
                field="maxPrice"
                current={sortBy}
                dir={sortDir}
                onSort={handleSort}
                className="text-right"
              >
                Top Price
              </SortHeader>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-50">
            {sorted.map((v, i) => (
              <tr key={v.name} className="table-row-hover">
                <td className="px-3 py-2.5 font-mono text-gray-400 text-xs">
                  {i + 1}
                </td>
                <td className="px-3 py-2.5 font-medium text-gray-900 max-w-[240px]">
                  <div className="truncate">{v.name}</div>
                  {v.saleCount > 1 && (
                    <span className="text-[10px] text-gray-400">
                      {v.saleCount} sales
                    </span>
                  )}
                </td>
                <td className="px-3 py-2.5 text-center text-gray-600">
                  {v.hipCount}
                </td>
                <td className="px-3 py-2.5 text-center text-gray-600">
                  {v.soldCount}
                </td>
                <td className="px-3 py-2.5 text-right">
                  <span
                    className={`text-xs font-medium ${
                      v.clearanceRate >= 70
                        ? "text-emerald-600"
                        : v.clearanceRate >= 50
                          ? "text-amber-600"
                          : "text-red-500"
                    }`}
                  >
                    {v.clearanceRate.toFixed(0)}%
                  </span>
                </td>
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
                  {formatCurrency(v.maxPrice)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {sorted.length === 0 && (
          <div className="text-center py-12 text-gray-400">
            No vendors match your search
          </div>
        )}
      </div>
    </div>
  );
}

/* ── Helpers ─────────────────────────────────────────────── */

function getMedian(prices) {
  if (!prices.length) return 0;
  const sorted = [...prices].sort((a, b) => a - b);
  return sorted[Math.floor(sorted.length / 2)];
}

function StatCard({ label, value, accent }) {
  return (
    <div className="rounded-xl border border-gray-100 bg-white p-4 shadow-[0_1px_3px_rgba(0,0,0,0.04)]">
      <p className="text-[10px] uppercase tracking-wider text-gray-400 mb-1">
        {label}
      </p>
      <p
        className={`text-lg font-semibold ${
          accent ? "text-brand-600" : "text-gray-800"
        }`}
      >
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
          <span className="text-brand-600">
            {dir === "asc" ? "\u2191" : "\u2193"}
          </span>
        )}
      </span>
    </th>
  );
}
