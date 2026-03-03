/**
 * BreezeVision API layer
 *
 * Primary data source: S3 (pre-processed JSON uploaded by scripts/sync_to_s3.py)
 * Fallback: OBS REST API via Netlify proxy (for live data or when S3 is empty)
 */

const API_BASE = "/.netlify/functions";

/**
 * Generate the full catalog of all OBS sales with S3 data.
 * OBS numeric IDs are only known for 2025 sales.
 */
function buildCatalog() {
  const catalog = {};
  const currentYear = new Date().getFullYear();
  const endYear = Math.max(currentYear + 1, 2026);
  const years = [];
  for (let y = 2018; y <= endYear; y++) years.push(y);
  const seasons = [
    { key: "march", label: "March", month: 3, fullName: (y) => `OBS March 2YO in Training ${y}` },
    { key: "spring", label: "Spring", month: 4, fullName: (y) => `OBS Spring 2YO in Training ${y}` },
    { key: "june", label: "June", month: 6, fullName: (y) => `OBS June 2YO & HRA ${y}` },
  ];

  // Known OBS API IDs (only 2025)
  const obsIds = {
    obs_march_2025: 142,
    obs_spring_2025: 144,
    obs_june_2025: 145,
    obs_march_2026: 149,
  };

  for (const year of years) {
    for (const season of seasons) {
      const s3Key = `obs_${season.key}_${year}`;
      catalog[s3Key] = {
        id: obsIds[s3Key] || null,
        name: season.fullName(year),
        company: "OBS",
        month: season.month,
        year,
        location: "Ocala, FL",
        s3Key,
        hasData: year >= 2025, // Pre-processed JSON available for 2025+
        isLive: year >= 2026, // Live/current year sales
      };
    }
  }

  return catalog;
}

// Known OBS catalog sales — s3Key is the primary identifier
export const SALE_CATALOG = buildCatalog();

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

/* ── OBS API (fallback) ─────────────────────────────────────── */

/**
 * Fetch all hip data for a sale from OBS API
 */
export async function fetchSale(catalogId) {
  const res = await fetch(`${API_BASE}/obs-proxy?saleId=${catalogId}`);
  if (!res.ok) throw new Error(`Failed to fetch sale: ${res.status}`);
  return res.json();
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

/* ── Parsing (used when falling back to OBS API) ────────────── */

/**
 * Parse raw OBS API hip data into our standardised shape
 */
export function parseHip(raw) {
  const dp = raw.display_props || {};
  let status = "pending";
  if (dp.is_hip_out) status = "out";
  else if (dp.is_rna) status = "rna";
  else if (dp.is_hip_sold) status = "sold";

  const price = parseFloat(raw.hammer_price);

  return {
    hipNumber: parseInt(raw.hip_number, 10),
    horseName: raw.horse_name || null,
    sex: raw.sex || "—",
    color: raw.color || "—",
    yearOfBirth: raw.foaling_year ? parseInt(raw.foaling_year, 10) : null,
    sire: raw.sire_name || "Unknown",
    dam: raw.dam_name || "Unknown",
    damSire: raw.dam_sire || "Unknown",
    consignor: raw.consignor_name || "—",
    stateBred: raw.foaling_area || null,

    // Under-tack
    breezeTime: raw.ut_time ? parseFloat(raw.ut_time) : null,
    breezeDistance: raw.ut_distance ? raw.ut_distance.trim() : null,
    breezeDate: raw.ut_actual_date || null,

    // Sale result
    status,
    price: !isNaN(price) && price > 0 ? price : null,
    buyer: raw.buyer_name || null,
    displayPrice: dp.hammer_price || null,

    // Media URLs
    photoUrl: raw.photo_link || null,
    videoUrl: raw.video_link || null,
    walkVideoUrl: raw.walk_video_link || null,
    pedigreeUrl: raw.pedigree_pdf_link || null,

    // Raw for debugging
    _raw: raw,
  };
}

/**
 * Convert S3 hip format (from sync_to_s3.py) to frontend format
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

    // Media URLs (from OBS, S3 assets overlay these)
    photoUrl: h.photo_url || null,
    videoUrl: h.video_url || null,
    walkVideoUrl: h.walk_video_url || null,
    pedigreeUrl: h.pedigree_pdf_url || null,
  };
}

/**
 * Parse a full sale response from OBS API
 */
export function parseSaleResponse(data) {
  const hips = (data.sale_hip || []).map(parseHip);
  return {
    saleId: data.sale_id,
    saleCode: data.sale_code,
    saleName: data.sale_name,
    year: data.year,
    startDate: data.sale_starts,
    endDate: data.sale_ends,
    hips,
  };
}

/**
 * Parse an S3 sale response (from sync_to_s3.py)
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
 * Compute aggregate stats for a sale
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
