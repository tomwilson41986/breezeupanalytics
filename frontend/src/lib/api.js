/**
 * BreezeVision API layer
 * Fetches sale data from OBS via Netlify serverless function proxy
 */

const API_BASE = "/.netlify/functions";

// Known OBS catalog sale IDs — s3Key matches the S3 folder name
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

/**
 * Fetch all hip data for a sale
 */
export async function fetchSale(catalogId) {
  const res = await fetch(`${API_BASE}/obs-proxy?saleId=${catalogId}`);
  if (!res.ok) throw new Error(`Failed to fetch sale: ${res.status}`);
  return res.json();
}

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
 * Parse a full sale response
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
