/**
 * BreezeVision API layer
 *
 * Data sources (in priority order):
 *   1. S3 — pre-processed JSON (via sale-data Netlify function)
 *   2. Static JSON — bundled in /data/ at build time (GitHub)
 *
 * No live OBS API calls.
 */

const API_BASE = "/.netlify/functions";

// Known sale catalog — s3Key matches S3 folder and static /data/ folder
export const SALE_CATALOG = {
  obs_march_2025: {
    id: 142,
    name: "OBS March 2YO in Training 2025",
    company: "OBS",
    month: 3,
    year: 2025,
    location: "Ocala, FL",
    s3Key: "obs_march_2025",
  },
  obs_spring_2025: {
    id: 144,
    name: "OBS Spring 2YO in Training 2025",
    company: "OBS",
    month: 4,
    year: 2025,
    location: "Ocala, FL",
    s3Key: "obs_spring_2025",
  },
  obs_june_2025: {
    id: 145,
    name: "OBS June 2YO & HRA 2025",
    company: "OBS",
    month: 6,
    year: 2025,
    location: "Ocala, FL",
    s3Key: "obs_june_2025",
  },
};

/* ── S3-backed data (primary) ───────────────────────────────── */

/**
 * Fetch pre-processed sale data from S3 via sale-data function
 */
export async function fetchSaleFromS3(s3Key) {
  const res = await fetch(`${API_BASE}/sale-data?sale=${encodeURIComponent(s3Key)}`);
  if (!res.ok) return null;
  return res.json();
}

/**
 * Fetch pre-computed stats from S3
 */
export async function fetchStatsFromS3(s3Key) {
  const res = await fetch(
    `${API_BASE}/sale-data?sale=${encodeURIComponent(s3Key)}&type=stats`
  );
  if (!res.ok) return null;
  return res.json();
}

/* ── Static data fallback (bundled in repo) ───────────────── */

/**
 * Fetch sale data from static JSON bundled at build time
 */
export async function fetchSaleStatic(s3Key) {
  try {
    const res = await fetch(`/data/${s3Key}/sale.json`);
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}

/**
 * Fetch stats from static JSON bundled at build time
 */
export async function fetchStatsStatic(s3Key) {
  try {
    const res = await fetch(`/data/${s3Key}/stats.json`);
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}

/* ── S3 Asset functions ─────────────────────────────────────── */

/**
 * Fetch S3 asset URLs for a single hip
 * Returns { video?, walkVideo?, photo?, pedigree? }
 */
export async function fetchHipAssets(s3Key, hipNumber) {
  const res = await fetch(
    `${API_BASE}/s3-assets?sale=${encodeURIComponent(s3Key)}&hip=${encodeURIComponent(hipNumber)}`
  );
  if (!res.ok) return {};
  const data = await res.json();
  return data.assets || {};
}

/**
 * Fetch the list of all hips that have S3 assets for a sale
 * Returns { [hipNumber]: { video?, walkVideo?, photo?, pedigree? } }
 */
export async function fetchSaleAssetIndex(s3Key) {
  const res = await fetch(
    `${API_BASE}/s3-assets?sale=${encodeURIComponent(s3Key)}&list=true`
  );
  if (!res.ok) return {};
  const data = await res.json();
  return data.assets || {};
}

/* ── Parsing (S3 / static JSON format) ───────────────────────── */

/**
 * Convert S3/static hip format to frontend format
 */
export function parseS3Hip(h) {
  return {
    hipNumber: h.hip_number,
    horseName: h.horse_name || null,
    sex: h.sex || "—",
    color: h.colour || "—",
    yearOfBirth: h.year_of_birth || null,
    sire: h.sire || "Unknown",
    dam: h.dam || "Unknown",
    damSire: h.dam_sire || "Unknown",
    consignor: h.consignor || "—",
    stateBred: h.state_bred || null,

    // Under-tack
    breezeTime: h.under_tack_time || null,
    breezeDistance: h.under_tack_distance || null,
    breezeDate: h.under_tack_date || null,

    // Sale result
    status: (h.sale_status || "pending").toLowerCase(),
    price: h.sale_price || null,
    buyer: h.buyer || null,
    displayPrice: h.sale_price ? `$${h.sale_price.toLocaleString()}` : null,

    // Media URLs (S3 assets overlay these via assetIndex)
    photoUrl: h.photo_url || null,
    videoUrl: h.video_url || null,
    walkVideoUrl: h.walk_video_url || null,
    pedigreeUrl: h.pedigree_pdf_url || null,
  };
}

/**
 * Parse an S3/static sale response
 */
export function parseS3SaleResponse(data) {
  const hips = (data.hips || []).map(parseS3Hip);
  return {
    saleId: data.sale_id,
    saleCode: data.sale_code,
    saleName: data.sale_name,
    year: data.year,
    startDate: data.start_date,
    endDate: data.end_date,
    syncedAt: data.synced_at,
    hips,
  };
}

/**
 * Compute aggregate stats for a sale (used when pre-computed stats unavailable)
 */
export function computeSaleStats(hips) {
  const sold = hips.filter((h) => h.status === "sold" && h.price);
  const rna = hips.filter((h) => h.status === "rna");
  const out = hips.filter((h) => h.status === "out");
  const prices = sold.map((h) => h.price);
  const totalRevenue = prices.reduce((sum, p) => sum + p, 0);
  const avgPrice = prices.length ? totalRevenue / prices.length : 0;
  const medianPrice = prices.length
    ? [...prices].sort((a, b) => a - b)[Math.floor(prices.length / 2)]
    : 0;
  const maxPrice = prices.length ? Math.max(...prices) : 0;

  // Sire stats
  const sireMap = {};
  for (const h of sold) {
    if (!sireMap[h.sire]) sireMap[h.sire] = { count: 0, total: 0, prices: [] };
    sireMap[h.sire].count++;
    sireMap[h.sire].total += h.price;
    sireMap[h.sire].prices.push(h.price);
  }
  const topSires = Object.entries(sireMap)
    .map(([name, s]) => ({
      name,
      count: s.count,
      avgPrice: s.total / s.count,
      totalRevenue: s.total,
      medianPrice: [...s.prices].sort((a, b) => a - b)[
        Math.floor(s.prices.length / 2)
      ],
    }))
    .sort((a, b) => b.avgPrice - a.avgPrice);

  // Breeze time distribution
  const withTimes = hips.filter((h) => h.breezeTime && h.breezeDistance);
  const breezeByDistance = {};
  for (const h of withTimes) {
    const key = h.breezeDistance;
    if (!breezeByDistance[key]) breezeByDistance[key] = [];
    breezeByDistance[key].push({
      time: h.breezeTime,
      price: h.price,
      hip: h.hipNumber,
      sire: h.sire,
    });
  }

  // Price distribution buckets
  const buckets = [
    { label: "< $10K", min: 0, max: 10000 },
    { label: "$10K-$25K", min: 10000, max: 25000 },
    { label: "$25K-$50K", min: 25000, max: 50000 },
    { label: "$50K-$100K", min: 50000, max: 100000 },
    { label: "$100K-$250K", min: 100000, max: 250000 },
    { label: "$250K-$500K", min: 250000, max: 500000 },
    { label: "$500K-$1M", min: 500000, max: 1000000 },
    { label: "$1M+", min: 1000000, max: Infinity },
  ];
  const priceDistribution = buckets.map((b) => ({
    ...b,
    count: prices.filter((p) => p >= b.min && p < b.max).length,
  }));

  // Consignor stats
  const consignorMap = {};
  for (const h of sold) {
    if (!consignorMap[h.consignor])
      consignorMap[h.consignor] = { count: 0, total: 0 };
    consignorMap[h.consignor].count++;
    consignorMap[h.consignor].total += h.price;
  }
  const topConsignors = Object.entries(consignorMap)
    .map(([name, c]) => ({
      name,
      count: c.count,
      avgPrice: c.total / c.count,
      totalRevenue: c.total,
    }))
    .sort((a, b) => b.totalRevenue - a.totalRevenue);

  return {
    totalHips: hips.length,
    soldCount: sold.length,
    rnaCount: rna.length,
    outCount: out.length,
    totalRevenue,
    avgPrice,
    medianPrice,
    maxPrice,
    buybackRate: hips.length ? (rna.length / (sold.length + rna.length)) * 100 : 0,
    topSires,
    breezeByDistance,
    priceDistribution,
    topConsignors,
  };
}
