import { useState, useEffect } from "react";
import {
  fetchSaleFromS3,
  fetchStatsFromS3,
  fetchRatingsFromS3,
  parseS3SaleResponse,
  fetchSale,
  parseSaleResponse,
  computeSaleStats,
  fetchSaleAssetIndex,
  SALE_CATALOG,
} from "../lib/api";

/**
 * Try S3 first (pre-processed data), fall back to live OBS API,
 * or return asset-only data for historical sales.
 */
async function loadSaleData(s3Key) {
  const meta = SALE_CATALOG[s3Key];

  // Try S3 pre-processed JSON first (only exists for 2025 sales)
  const [s3Sale, s3Stats] = await Promise.allSettled([
    fetchSaleFromS3(s3Key),
    fetchStatsFromS3(s3Key),
  ]);

  const saleData = s3Sale.status === "fulfilled" ? s3Sale.value : null;
  const statsData = s3Stats.status === "fulfilled" ? s3Stats.value : null;

  if (saleData && saleData.hips) {
    const parsed = parseS3SaleResponse(saleData);
    const stats = statsData || computeSaleStats(parsed.hips);
    return { sale: parsed, stats, source: "s3" };
  }

  // Fallback: try OBS API if we have a known numeric ID
  if (meta?.id) {
    try {
      const raw = await fetchSale(meta.id);
      const parsed = parseSaleResponse(raw);
      const stats = computeSaleStats(parsed.hips);
      return { sale: parsed, stats, source: "obs" };
    } catch {
      // OBS API failed, fall through to asset-only mode
    }
  }

  // Asset-only mode: no sale JSON available, will rely on S3 asset listing
  return { sale: null, stats: null, source: "assets-only" };
}

/**
 * Hook to fetch + parse sale data from S3 (primary) or OBS API (fallback),
 * and also load the S3 asset index for the sale.
 *
 * @param {string} s3Key - The S3 key identifier (e.g. "obs_march_2025")
 */
export function useSaleData(s3Key) {
  const [sale, setSale] = useState(null);
  const [stats, setStats] = useState(null);
  const [assetIndex, setAssetIndex] = useState(null);
  const [dataSource, setDataSource] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!s3Key) return;
    let cancelled = false;
    setLoading(true);
    setError(null);

    // Fetch sale data, S3 asset index, and ratings in parallel
    const dataPromise = loadSaleData(s3Key);
    const assetsPromise = fetchSaleAssetIndex(s3Key);
    const ratingsPromise = fetchRatingsFromS3(s3Key);

    Promise.all([dataPromise, assetsPromise, ratingsPromise])
      .then(([{ sale: parsed, stats: computedStats, source }, s3Index, ratings]) => {
        if (cancelled) return;

        // Merge ratings into hip data if available
        if (parsed && parsed.hips && ratings) {
          parsed.hips = parsed.hips.map((hip) => {
            const r = ratings[String(hip.hipNumber)];
            if (r) {
              // Convert stride lengths from metres to feet if still in metres
              // (backend now outputs feet ~20-25, old data has metres ~6-8)
              const METRES_TO_FEET = 3.28084;
              const converted = { ...r };
              if (converted.strideLengthUT != null && converted.strideLengthUT < 15) {
                converted.strideLengthUT = Math.round(converted.strideLengthUT * METRES_TO_FEET * 100) / 100;
              }
              if (converted.strideLengthGO != null && converted.strideLengthGO < 15) {
                converted.strideLengthGO = Math.round(converted.strideLengthGO * METRES_TO_FEET * 100) / 100;
              }
              return { ...hip, ratings: converted };
            }
            return hip;
          });
        }

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
  }, [s3Key]);

  return { sale, stats, assetIndex, dataSource, loading, error };
}
