import { useState, useEffect } from "react";
import { fetchSale, parseSaleResponse, computeSaleStats } from "../lib/api";

/**
 * Hook to fetch + parse sale data from OBS API via Netlify proxy
 */
export function useSaleData(catalogId) {
  const [sale, setSale] = useState(null);
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!catalogId) return;
    let cancelled = false;
    setLoading(true);
    setError(null);

    fetchSale(catalogId)
      .then((raw) => {
        if (cancelled) return;
        const parsed = parseSaleResponse(raw);
        setSale(parsed);
        setStats(computeSaleStats(parsed.hips));
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

  return { sale, stats, loading, error };
}
