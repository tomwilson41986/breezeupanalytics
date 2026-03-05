import { useState, useEffect } from "react";

/**
 * Fetch detailed live sale times data for a given sale.
 * Returns the full times object keyed by hip number.
 *
 * Data shape from S3:
 *   { sale_key, generated_at, count, columns, hips: { "123": { hip_number, distance, time, ... } } }
 */
export function useLiveSaleTimes(saleKey) {
  const [timesData, setTimesData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!saleKey) {
      setLoading(false);
      return;
    }

    let cancelled = false;
    setLoading(true);
    setError(null);

    async function load() {
      // Try S3 via Netlify function first
      try {
        const res = await fetch(
          `/.netlify/functions/sale-data?sale=${encodeURIComponent(saleKey)}&type=live-sale-times`
        );
        if (res.ok) {
          const data = await res.json();
          if (!cancelled) {
            setTimesData(data);
            setLoading(false);
          }
          return;
        }
      } catch {}

      // Fallback to static file
      try {
        const res = await fetch(`/data/live-sale-times/${saleKey}.json`);
        if (res.ok) {
          const data = await res.json();
          if (!cancelled) {
            setTimesData(data);
            setLoading(false);
          }
          return;
        }
      } catch {}

      if (!cancelled) {
        setTimesData(null);
        setLoading(false);
      }
    }

    load();
    return () => { cancelled = true; };
  }, [saleKey]);

  return { timesData, loading, error };
}
