import { useState, useEffect } from "react";
import {
  fetchSaleFromS3,
  fetchStatsFromS3,
  parseS3SaleResponse,
  fetchSale,
  parseSaleResponse,
  computeSaleStats,
  fetchSaleAssetIndex,
  SALE_CATALOG,
} from "../lib/api";

/**
 * Find the s3Key for a given catalog ID
 */
function getS3Key(catalogId) {
  const entry = Object.values(SALE_CATALOG).find(
    (m) => String(m.id) === String(catalogId)
  );
  return entry?.s3Key || null;
}

/**
 * Try S3 first (pre-processed data), fall back to live OBS API.
 */
async function loadSaleData(catalogId, s3Key) {
  // Try S3 first — fastest and has pre-computed stats
  if (s3Key) {
    const [s3Sale, s3Stats] = await Promise.all([
      fetchSaleFromS3(s3Key),
      fetchStatsFromS3(s3Key),
    ]);

    if (s3Sale && s3Sale.hips) {
      const parsed = parseS3SaleResponse(s3Sale);
      // Use pre-computed stats from S3, or compute from parsed hips
      const stats = s3Stats || computeSaleStats(parsed.hips);
      return { sale: parsed, stats, source: "s3" };
    }
  }

  // Fallback: fetch live from OBS API
  const raw = await fetchSale(catalogId);
  const parsed = parseSaleResponse(raw);
  const stats = computeSaleStats(parsed.hips);
  return { sale: parsed, stats, source: "obs" };
}

/**
 * Hook to fetch + parse sale data from S3 (primary) or OBS API (fallback),
 * and also load the S3 asset index for the sale.
 */
export function useSaleData(catalogId) {
  const [sale, setSale] = useState(null);
  const [stats, setStats] = useState(null);
  const [assetIndex, setAssetIndex] = useState(null);
  const [dataSource, setDataSource] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!catalogId) return;
    let cancelled = false;
    setLoading(true);
    setError(null);

    const s3Key = getS3Key(catalogId);

    // Fetch sale data and S3 asset index in parallel
    const dataPromise = loadSaleData(catalogId, s3Key);
    const assetsPromise = s3Key
      ? fetchSaleAssetIndex(s3Key)
      : Promise.resolve({});

    Promise.all([dataPromise, assetsPromise])
      .then(([{ sale: parsed, stats: computedStats, source }, s3Index]) => {
        if (cancelled) return;
        setSale(parsed);
        setStats(computedStats);
        setAssetIndex(s3Index);
        setDataSource(source);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err.message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [catalogId]);

  return { sale, stats, assetIndex, dataSource, loading, error };
}
