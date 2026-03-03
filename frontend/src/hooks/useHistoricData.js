import { useState, useEffect } from "react";

const BASE = "/data/historic";

/** Fetch and cache a single JSON file from the historic data directory */
const cache = {};

async function fetchJson(file) {
  if (cache[file]) return cache[file];
  const res = await fetch(`${BASE}/${file}`);
  if (!res.ok) throw new Error(`Failed to load ${file}`);
  const data = await res.json();
  cache[file] = data;
  return data;
}

/**
 * Load overall historic vendor performance data (536 vendors).
 * Returns { vendors, grandTotal, loading, error }
 */
export function useHistoricVendors() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetchJson("vendors.json")
      .then(setData)
      .catch(setError)
      .finally(() => setLoading(false));
  }, []);

  return {
    vendors: data?.vendors || [],
    grandTotal: data?.grandTotal || null,
    loading,
    error,
  };
}

/**
 * Load vendor-by-sale aggregated data.
 * Returns { salesData, saleNames, loading, error }
 */
export function useHistoricVendorBySale() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetchJson("vendor-by-sale.json")
      .then((d) => setData(d))
      .catch(setError)
      .finally(() => setLoading(false));
  }, []);

  const saleNames = data ? Object.keys(data).sort() : [];

  return { salesData: data || {}, saleNames, loading, error };
}

/**
 * Load sales summary data.
 * Returns { sales, loading, error }
 */
export function useHistoricSalesSummary() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetchJson("sales-summary.json")
      .then(setData)
      .catch(setError)
      .finally(() => setLoading(false));
  }, []);

  return { sales: data || [], loading, error };
}

/**
 * Load individual horse records (large dataset, ~33K records).
 * Only loads when explicitly called.
 * Returns { records, loading, error, load }
 */
export function useHistoricRecords() {
  const [records, setRecords] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  function load() {
    if (records || loading) return;
    setLoading(true);
    fetchJson("vendor-data.json")
      .then(setRecords)
      .catch(setError)
      .finally(() => setLoading(false));
  }

  return { records, loading, error, load };
}
