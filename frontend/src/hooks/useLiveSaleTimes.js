import { useState, useEffect } from "react";

/**
 * Parse a CSV string into our standard times data shape.
 * Auto-detects columns and normalises header names.
 */
function parseCsv(text) {
  const lines = text.trim().split(/\r?\n/);
  if (lines.length < 2) return null;

  const rawHeaders = lines[0].split(",").map((h) => h.trim());
  const headers = rawHeaders.map(normalizeHeader);

  const hips = {};
  for (let i = 1; i < lines.length; i++) {
    const vals = lines[i].split(",").map((v) => v.trim());
    if (!vals.length) continue;

    const record = {};
    for (let j = 0; j < headers.length; j++) {
      record[headers[j]] = parseValue(vals[j]);
    }

    const hipNum = record.hip_number;
    if (hipNum == null) continue;
    const key = String(typeof hipNum === "number" && hipNum % 1 === 0 ? hipNum : hipNum);
    hips[key] = record;
  }

  return {
    sale_key: null,
    generated_at: null,
    count: Object.keys(hips).length,
    columns: headers,
    hips,
  };
}

function normalizeHeader(header) {
  const h = header.toLowerCase().replace(/#/g, "").replace(/\s+/g, "_").replace(/[^a-z0-9_]/g, "");
  const aliases = {
    hip: "hip_number",
    hip_number: "hip_number",
    hipnumber: "hip_number",
    hipno: "hip_number",
    hip_no: "hip_number",
  };
  return aliases[h] || h;
}

function parseValue(val) {
  if (!val || val === "-" || val === "—" || val === "") return null;
  if (!/^-?\d/.test(val)) return val;
  const n = Number(val);
  return isNaN(n) ? val : n;
}

/**
 * Fetch detailed live sale times data for a given sale.
 * Tries S3 JSON first, then static JSON, then static CSV.
 *
 * Data shape:
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

      // Fallback to static JSON
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

      // Fallback to static CSV (committed to repo)
      try {
        const res = await fetch(`/data/live-sale-times/${saleKey}.csv`);
        if (res.ok) {
          const text = await res.text();
          const data = parseCsv(text);
          if (data && !cancelled) {
            data.sale_key = saleKey;
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
