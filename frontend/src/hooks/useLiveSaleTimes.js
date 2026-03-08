import { useState, useEffect } from "react";

/**
 * Split a CSV row respecting quoted fields (handles commas inside quotes).
 */
function splitCsvRow(line) {
  const fields = [];
  let current = "";
  let inQuotes = false;
  for (let i = 0; i < line.length; i++) {
    const ch = line[i];
    if (inQuotes) {
      if (ch === '"' && line[i + 1] === '"') {
        current += '"';
        i++;
      } else if (ch === '"') {
        inQuotes = false;
      } else {
        current += ch;
      }
    } else {
      if (ch === '"') {
        inQuotes = true;
      } else if (ch === ",") {
        fields.push(current.trim());
        current = "";
      } else {
        current += ch;
      }
    }
  }
  fields.push(current.trim());
  return fields;
}

/**
 * Parse a CSV string into our standard times data shape.
 * Auto-detects columns and normalises header names.
 */
function parseCsv(text) {
  const lines = text.trim().split(/\r?\n/);
  if (lines.length < 2) return null;

  const rawHeaders = splitCsvRow(lines[0]);
  const headers = rawHeaders.map(normalizeHeader);

  // Build a mapping from normalized keys to original CSV header labels
  const column_labels = {};
  for (let i = 0; i < rawHeaders.length; i++) {
    const norm = normalizeHeader(rawHeaders[i]);
    if (norm) column_labels[norm] = rawHeaders[i].trim();
  }

  const hips = {};
  for (let i = 1; i < lines.length; i++) {
    const vals = splitCsvRow(lines[i]);
    if (!vals.length || vals.every((v) => !v)) continue;

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
    column_labels,
    hips,
  };
}

function normalizeHeader(header) {
  // Remove special characters, then replace spaces with underscores
  // Matches the Python normalizer in upload_live_sale_times.py
  let h = header.toLowerCase().replace(/#/g, "").replace(/[()\/]/g, "").replace(/\s+/g, "_").replace(/[^a-z0-9_]/g, "");
  // Collapse multiple underscores and strip trailing/leading underscores
  h = h.replace(/_+/g, "_").replace(/^_|_$/g, "");
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
