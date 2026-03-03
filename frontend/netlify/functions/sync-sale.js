/**
 * Netlify serverless function — Sale Data Sync
 *
 * Fetches sale data from OBS API, processes it, and uploads
 * structured JSON to S3. This is the JS equivalent of scripts/sync_to_s3.py,
 * designed to run as a Netlify function so it can use the configured env vars.
 *
 * Usage:
 *   Sync one sale:  /.netlify/functions/sync-sale?sale=obs_march_2025
 *   Sync all:       /.netlify/functions/sync-sale?all=true
 */

import { createHmac, createHash } from "node:crypto";

const BUCKET = "breezeup";
const REGION = "eu-north-1";
const HOST = `${BUCKET}.s3.${REGION}.amazonaws.com`;

const OBS_API_BASE =
  "https://obssales.com/wp-json/obs-catalog-wp-plugin/v1";

const SALE_MAP = {
  obs_march_2025: 142,
  obs_spring_2025: 144,
  obs_june_2025: 145,
};

/* ── SigV4 helpers ──────────────────────────────────────────── */

function hmacSha256(key, data) {
  return createHmac("sha256", key).update(data).digest();
}

function sha256hex(data) {
  return createHash("sha256").update(data).digest("hex");
}

function getSigningKey(secretKey, dateStamp) {
  const kDate = hmacSha256(`AWS4${secretKey}`, dateStamp);
  const kRegion = hmacSha256(kDate, REGION);
  const kService = hmacSha256(kRegion, "s3");
  return hmacSha256(kService, "aws4_request");
}

async function s3Put(key, body, accessKeyId, secretAccessKey) {
  const now = new Date();
  const amzDate = now.toISOString().replace(/[-:]/g, "").replace(/\.\d+Z$/, "Z");
  const dateStamp = now.toISOString().slice(0, 10).replace(/-/g, "");
  const encodedKey = key.split("/").map(encodeURIComponent).join("/");

  const payloadHash = sha256hex(body);
  const contentType = "application/json";

  const canonicalHeaders =
    `content-type:${contentType}\n` +
    `host:${HOST}\n` +
    `x-amz-content-sha256:${payloadHash}\n` +
    `x-amz-date:${amzDate}\n`;
  const signedHeaders = "content-type;host;x-amz-content-sha256;x-amz-date";

  const canonicalRequest = [
    "PUT",
    `/${encodedKey}`,
    "",
    canonicalHeaders,
    signedHeaders,
    payloadHash,
  ].join("\n");

  const scope = `${dateStamp}/${REGION}/s3/aws4_request`;
  const stringToSign = [
    "AWS4-HMAC-SHA256",
    amzDate,
    scope,
    sha256hex(canonicalRequest),
  ].join("\n");

  const signingKey = getSigningKey(secretAccessKey, dateStamp);
  const signature = createHmac("sha256", signingKey).update(stringToSign).digest("hex");

  const authorization =
    `AWS4-HMAC-SHA256 Credential=${accessKeyId}/${scope}, ` +
    `SignedHeaders=${signedHeaders}, Signature=${signature}`;

  const res = await fetch(`https://${HOST}/${encodedKey}`, {
    method: "PUT",
    body,
    headers: {
      "Content-Type": contentType,
      Host: HOST,
      "x-amz-date": amzDate,
      "x-amz-content-sha256": payloadHash,
      Authorization: authorization,
    },
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(`S3 PUT failed (${res.status}): ${text.slice(0, 200)}`);
  }
}

/* ── OBS API ────────────────────────────────────────────────── */

async function fetchObsSale(catalogId) {
  const res = await fetch(`${OBS_API_BASE}/horse-sales/${catalogId}`);
  if (!res.ok) throw new Error(`OBS API error: ${res.status}`);
  return res.json();
}

/* ── Processing ─────────────────────────────────────────────── */

function parseHip(raw) {
  const dp = raw.display_props || {};
  let status = "pending";
  if (dp.is_hip_out) status = "out";
  else if (dp.is_hip_sold) status = "sold";
  else if (dp.is_rna) status = "RNA";
  if (raw.in_out_status === "O" && status === "pending") status = "out";

  let price = parseFloat(raw.hammer_price);
  if (isNaN(price) || price <= 0) price = null;
  else price = Math.round(price);

  let utTime = raw.ut_time ? parseFloat(raw.ut_time) : null;
  if (isNaN(utTime)) utTime = null;

  return {
    sale_id: String(raw.sale_id || ""),
    hip_number: parseInt(raw.hip_number, 10),
    horse_name: raw.horse_name || null,
    sex: raw.sex || null,
    colour: raw.color || null,
    year_of_birth: raw.foaling_year ? parseInt(raw.foaling_year, 10) : null,
    sire: raw.sire_name || null,
    dam: raw.dam_name || null,
    dam_sire: raw.dam_sire || null,
    consignor: raw.consignor_name || null,
    state_bred: raw.foaling_area || null,
    under_tack_distance: (raw.ut_distance || "").trim() || null,
    under_tack_time: utTime,
    under_tack_date: raw.ut_actual_date || null,
    sale_price: price,
    sale_status: status,
    buyer: raw.buyer_name || null,
    photo_url: raw.photo_link || null,
    video_url: raw.video_link || null,
    walk_video_url: raw.walk_video_link || null,
    pedigree_pdf_url: raw.pedigree_pdf_link || null,
  };
}

function parseSale(data) {
  let year = null;
  if (data.sale_starts) year = parseInt(data.sale_starts.slice(0, 4), 10);

  return {
    sale_id: String(data.sale_id),
    sale_code: data.sale_code || "",
    sale_name: data.sale_name || "",
    sale_short_name: data.sale_short_name || "",
    year: year || 0,
    sale_category: data.sale_category || "",
    start_date: data.sale_starts || null,
    end_date: data.sale_ends || null,
    hips: (data.sale_hip || []).map(parseHip),
    synced_at: new Date().toISOString(),
  };
}

function computeStats(sale) {
  const hips = sale.hips;
  const sold = hips.filter((h) => h.sale_status === "sold" && h.sale_price);
  const rna = hips.filter((h) => h.sale_status === "RNA");
  const out = hips.filter((h) => h.sale_status === "out");
  const prices = sold.map((h) => h.sale_price);

  const totalRevenue = prices.reduce((s, p) => s + p, 0);
  const avgPrice = prices.length ? totalRevenue / prices.length : 0;
  const sorted = [...prices].sort((a, b) => a - b);
  const medianPrice = sorted.length ? sorted[Math.floor(sorted.length / 2)] : 0;
  const maxPrice = sorted.length ? sorted[sorted.length - 1] : 0;

  // Sire stats
  const sireMap = {};
  for (const h of sold) {
    const sire = h.sire || "Unknown";
    if (!sireMap[sire]) sireMap[sire] = { count: 0, total: 0, prices: [] };
    sireMap[sire].count++;
    sireMap[sire].total += h.sale_price;
    sireMap[sire].prices.push(h.sale_price);
  }
  const topSires = Object.entries(sireMap)
    .map(([name, s]) => ({
      name,
      count: s.count,
      avgPrice: s.total / s.count,
      totalRevenue: s.total,
      medianPrice: [...s.prices].sort((a, b) => a - b)[Math.floor(s.prices.length / 2)],
    }))
    .sort((a, b) => b.avgPrice - a.avgPrice)
    .slice(0, 30);

  // Consignor stats
  const conMap = {};
  for (const h of sold) {
    const c = h.consignor || "Unknown";
    if (!conMap[c]) conMap[c] = { count: 0, total: 0 };
    conMap[c].count++;
    conMap[c].total += h.sale_price;
  }
  const topConsignors = Object.entries(conMap)
    .map(([name, c]) => ({
      name,
      count: c.count,
      avgPrice: c.total / c.count,
      totalRevenue: c.total,
    }))
    .sort((a, b) => b.totalRevenue - a.totalRevenue)
    .slice(0, 30);

  // Breeze by distance
  const withTimes = hips.filter((h) => h.under_tack_time && h.under_tack_distance);
  const breezeByDistance = {};
  for (const h of withTimes) {
    const d = h.under_tack_distance;
    if (!breezeByDistance[d]) breezeByDistance[d] = [];
    breezeByDistance[d].push({
      time: h.under_tack_time,
      price: h.sale_price,
      hip: h.hip_number,
      sire: h.sire,
    });
  }

  // Price distribution
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

  const buybackRate = sold.length + rna.length > 0
    ? (rna.length / (sold.length + rna.length)) * 100
    : 0;

  return {
    totalHips: hips.length,
    soldCount: sold.length,
    rnaCount: rna.length,
    outCount: out.length,
    totalRevenue,
    avgPrice,
    medianPrice,
    maxPrice,
    buybackRate,
    topSires,
    breezeByDistance,
    priceDistribution,
    topConsignors,
    synced_at: new Date().toISOString(),
  };
}

/* ── Handler ────────────────────────────────────────────────── */

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type",
};

export default async (req) => {
  if (req.method === "OPTIONS") {
    return new Response(null, { status: 204, headers: corsHeaders });
  }

  const accessKeyId = process.env.BREEZEUP_AWS_ACCESS_KEY_ID;
  const secretAccessKey = process.env.BREEZEUP_AWS_SECRET_ACCESS_KEY;

  if (!accessKeyId || !secretAccessKey) {
    return new Response(JSON.stringify({ error: "AWS credentials not configured" }), {
      status: 500,
      headers: { "Content-Type": "application/json", ...corsHeaders },
    });
  }

  const url = new URL(req.url);
  const saleKey = url.searchParams.get("sale");
  const syncAll = url.searchParams.get("all") === "true";

  const keysToSync = syncAll
    ? Object.keys(SALE_MAP)
    : saleKey
      ? [saleKey]
      : [];

  if (keysToSync.length === 0) {
    return new Response(
      JSON.stringify({
        error: "Provide ?sale=obs_march_2025 or ?all=true",
        available: Object.keys(SALE_MAP),
      }),
      { status: 400, headers: { "Content-Type": "application/json", ...corsHeaders } }
    );
  }

  const results = [];

  for (const key of keysToSync) {
    const catalogId = SALE_MAP[key];
    if (!catalogId) {
      results.push({ sale: key, error: "Unknown sale key" });
      continue;
    }

    try {
      // Fetch from OBS
      const raw = await fetchObsSale(catalogId);
      const sale = parseSale(raw);
      const stats = computeStats(sale);

      // Upload to S3
      const saleJson = JSON.stringify(sale, null, 2);
      const statsJson = JSON.stringify(stats, null, 2);

      await s3Put(`data/${key}/sale.json`, saleJson, accessKeyId, secretAccessKey);
      await s3Put(`data/${key}/stats.json`, statsJson, accessKeyId, secretAccessKey);

      results.push({
        sale: key,
        success: true,
        hips: sale.hips.length,
        sold: stats.soldCount,
        totalRevenue: stats.totalRevenue,
      });
    } catch (err) {
      results.push({ sale: key, error: err.message });
    }
  }

  return new Response(JSON.stringify({ results }, null, 2), {
    status: 200,
    headers: { "Content-Type": "application/json", ...corsHeaders },
  });
};
