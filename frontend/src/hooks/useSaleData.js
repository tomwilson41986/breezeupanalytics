import { useState, useEffect } from "react";
import {
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
 * Hook to fetch + parse sale data from OBS API via Netlify proxy,
 * and also load the S3 asset index for the sale
 */
export function useSaleData(catalogId) {
  const [sale, setSale] = useState(null);
  const [stats, setStats] = useState(null);
  const [assetIndex, setAssetIndex] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!catalogId) return;
    let cancelled = false;
    setLoading(true);
    setError(null);

    const s3Key = getS3Key(catalogId);

    // Fetch OBS data and S3 asset index in parallel
    const obsPromise = fetchSale(catalogId);
    const s3Promise = s3Key ? fetchSaleAssetIndex(s3Key) : Promise.resolve({});

    Promise.all([obsPromise, s3Promise])
      .then(([raw, s3Index]) => {
        if (cancelled) return;
        const parsed = parseSaleResponse(raw);
        setSale(parsed);
        setStats(computeSaleStats(parsed.hips));
        setAssetIndex(s3Index);
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

  return { sale, stats, assetIndex, loading, error };
}
