import { useState, useEffect } from "react";
import { fetchHipAssets } from "../lib/api";

/**
 * Hook to fetch S3 pre-signed asset URLs for a specific hip
 */
export function useHipAssets(s3Key, hipNumber) {
  const [assets, setAssets] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!s3Key || !hipNumber) return;
    let cancelled = false;
    setLoading(true);

    fetchHipAssets(s3Key, hipNumber)
      .then((data) => {
        if (!cancelled) setAssets(data);
      })
      .catch(() => {
        if (!cancelled) setAssets({});
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [s3Key, hipNumber]);

  return { assets, loading };
}
