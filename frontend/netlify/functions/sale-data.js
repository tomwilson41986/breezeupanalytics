/**
 * Netlify serverless function — S3 Sale Data (with auto-populate)
 *
 * Reads pre-processed sale JSON from S3. If not found, fetches from OBS API,
 * processes the data, uploads to S3, and returns it. Self-healing — no manual
 * sync needed for the first request.
 *
 * Usage:
 *   Full sale:  /.netlify/functions/sale-data?sale=obs_march_2025
 *   Stats only: /.netlify/functions/sale-data?sale=obs_march_2025&type=stats
 *   Catalog:    /.netlify/functions/sale-data?catalog=true
 *   Force sync: /.netlify/functions/sale-data?sale=obs_march_2025&sync=true
 */

import { createHmac, createHash } from "node:crypto";

const BUCKET = "breezeup";
const REGION = "eu-north-1";
const HOST = `${BUCKET}.s3.${REGION}.amazonaws.com`;
const OBS_API = "https://obssales.com/wp-json/obs-catalog-wp-plugin/v1";

/* ── AWS SigV4 helpers ──────────────────────────────────────── */

function hmac(key, data) {
  return createHmac("sha256", key).update(data).digest();
}

function sha256hex(data) {
  return createHash("sha256").update(data).digest("hex");
}

function getSigningKey(secretKey, dateStamp) {
  const kDate = hmac(`AWS4${secretKey}`, dateStamp);
  const kRegion = hmac(kDate, REGION);
  const kService = hmac(kRegion, "s3");
  return hmac(kService, "aws4_request");
}

function sigV4Headers(method, key, payloadHash, accessKeyId, secretAccessKey) {
  const now = new Date();
  const amzDate = now.toISOString().replace(/[-:]/g, "").replace(/\.\d+Z$/, "Z");
  const dateStamp = now.toISOString().slice(0, 10).replace(/-/g, "");
  const encodedKey = key.split("/").map(encodeURIComponent).join("/");

  const extraHeaders = method === "PUT" ? `content-type:application/json\n` : "";
  const extraSigned = method === "PUT" ? "content-type;" : "";

  const canonicalHeaders =
    `${extraHeaders}host:${HOST}\nx-amz-content-sha256:${payloadHash}\nx-amz-date:${amzDate}\n`;
  const signedHeaders = `${extraSigned}host;x-amz-content-sha256;x-amz-date`;

  const canonicalRequest = [
    method,
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

  const headers = {
    Host: HOST,
    "x-amz-date": amzDate,
    "x-amz-content-sha256": payloadHash,
    Authorization:
      `AWS4-HMAC-SHA256 Credential=${accessKeyId}/${scope}, ` +
      `SignedHeaders=${signedHeaders}, Signature=${signature}`,
  };
  if (method === "PUT") headers["Content-Type"] = "application/json";

  return { encodedKey, headers };
}

async function s3Get(key, accessKeyId, secretAccessKey) {
  const { encodedKey, headers } = sigV4Headers(
    "GET", key, sha256hex(""), accessKeyId, secretAccessKey
  );
  return fetch(`https://${HOST}/${encodedKey}`, { headers });
}

async function s3Put(key, body, accessKeyId, secretAccessKey) {
  const { encodedKey, headers } = sigV4Headers(
    "PUT", key, sha256hex(body), accessKeyId, secretAccessKey
  );
  const res = await fetch(`https://${HOST}/${encodedKey}`, {
    method: "PUT",
    body,
    headers,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`S3 PUT ${res.status}: ${text.slice(0, 200)}`);
  }
}

/* ── Known sales ────────────────────────────────────────────── */

const SALE_CATALOG = {
  obs_march_2025: {
    id: 142, name: "OBS March 2YO in Training 2025",
    company: "OBS", month: 3, year: 2025, location: "Ocala, FL",
    s3Key: "obs_march_2025",
  },
  obs_spring_2025: {
    id: 144, name: "OBS Spring 2YO in Training 2025",
    company: "OBS", month: 4, year: 2025, location: "Ocala, FL",
    s3Key: "obs_spring_2025",
  },
  obs_june_2025: {
    id: 145, name: "OBS June 2YO & HRA 2025",
    company: "OBS", month: 6, year: 2025, location: "Ocala, FL",
    s3Key: "obs_june_2025",
  },
};

/* ── OBS → structured JSON ──────────────────────────────────── */

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

function processObs(data) {
  let year = data.sale_starts ? parseInt(data.sale_starts.slice(0, 4), 10) : 0;

  const sale = {
    sale_id: String(data.sale_id),
    sale_code: data.sale_code || "",
    sale_name: data.sale_name || "",
    sale_short_name: data.sale_short_name || "",
    year,
    sale_category: data.sale_category || "",
    start_date: data.sale_starts || null,
    end_date: data.sale_ends || null,
    hips: (data.sale_hip || []).map(parseHip),
    synced_at: new Date().toISOString(),
  };

  // Compute stats
  const hips = sale.hips;
  const sold = hips.filter((h) => h.sale_status === "sold" && h.sale_price);
  const rna = hips.filter((h) => h.sale_status === "RNA");
  const out = hips.filter((h) => h.sale_status === "out");
  const prices = sold.map((h) => h.sale_price);
  const totalRevenue = prices.reduce((s, p) => s + p, 0);
  const sorted = [...prices].sort((a, b) => a - b);

  const sireMap = {};
  for (const h of sold) {
    const sire = h.sire || "Unknown";
    if (!sireMap[sire]) sireMap[sire] = { count: 0, total: 0, prices: [] };
    sireMap[sire].count++;
    sireMap[sire].total += h.sale_price;
    sireMap[sire].prices.push(h.sale_price);
  }

  const conMap = {};
  for (const h of sold) {
    const c = h.consignor || "Unknown";
    if (!conMap[c]) conMap[c] = { count: 0, total: 0 };
    conMap[c].count++;
    conMap[c].total += h.sale_price;
  }

  const withTimes = hips.filter((h) => h.under_tack_time && h.under_tack_distance);
  const breezeByDistance = {};
  for (const h of withTimes) {
    const d = h.under_tack_distance;
    if (!breezeByDistance[d]) breezeByDistance[d] = [];
    breezeByDistance[d].push({
      time: h.under_tack_time, price: h.sale_price,
      hip: h.hip_number, sire: h.sire,
    });
  }

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

  const stats = {
    totalHips: hips.length,
    soldCount: sold.length,
    rnaCount: rna.length,
    outCount: out.length,
    totalRevenue,
    avgPrice: prices.length ? totalRevenue / prices.length : 0,
    medianPrice: sorted.length ? sorted[Math.floor(sorted.length / 2)] : 0,
    maxPrice: sorted.length ? sorted[sorted.length - 1] : 0,
    buybackRate: sold.length + rna.length > 0
      ? (rna.length / (sold.length + rna.length)) * 100 : 0,
    topSires: Object.entries(sireMap)
      .map(([name, s]) => ({
        name, count: s.count,
        avgPrice: s.total / s.count,
        totalRevenue: s.total,
        medianPrice: [...s.prices].sort((a, b) => a - b)[Math.floor(s.prices.length / 2)],
      }))
      .sort((a, b) => b.avgPrice - a.avgPrice)
      .slice(0, 30),
    breezeByDistance,
    priceDistribution: buckets.map((b) => ({
      ...b,
      count: prices.filter((p) => p >= b.min && p < b.max).length,
    })),
    topConsignors: Object.entries(conMap)
      .map(([name, c]) => ({
        name, count: c.count,
        avgPrice: c.total / c.count,
        totalRevenue: c.total,
      }))
      .sort((a, b) => b.totalRevenue - a.totalRevenue)
      .slice(0, 30),
    synced_at: new Date().toISOString(),
  };

  return { sale, stats };
}

async function fetchAndSync(saleKey, accessKeyId, secretAccessKey) {
  const catalogId = SALE_CATALOG[saleKey].id;

  // Fetch from OBS
  const res = await fetch(`${OBS_API}/horse-sales/${catalogId}`);
  if (!res.ok) throw new Error(`OBS API error: ${res.status}`);
  const raw = await res.json();

  // Process
  const { sale, stats } = processObs(raw);

  // Upload both to S3 (fire and forget for speed — but await to ensure it lands)
  const saleJson = JSON.stringify(sale);
  const statsJson = JSON.stringify(stats);

  await Promise.all([
    s3Put(`data/${saleKey}/sale.json`, saleJson, accessKeyId, secretAccessKey),
    s3Put(`data/${saleKey}/stats.json`, statsJson, accessKeyId, secretAccessKey),
  ]);

  return { sale, stats };
}

/* ── Response helpers ───────────────────────────────────────── */

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type",
};

function jsonResponse(body, status = 200, cacheSeconds = 300) {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      "Content-Type": "application/json",
      "Cache-Control": `public, max-age=${cacheSeconds}, s-maxage=${cacheSeconds * 2}`,
      ...corsHeaders,
    },
  });
}

/* ── Handler ────────────────────────────────────────────────── */

export default async (req) => {
  if (req.method === "OPTIONS") {
    return new Response(null, { status: 204, headers: corsHeaders });
  }

  const url = new URL(req.url);

  if (url.searchParams.get("catalog") === "true") {
    return jsonResponse({ catalog: SALE_CATALOG }, 200, 600);
  }

  const saleKey = url.searchParams.get("sale");
  if (!saleKey) {
    return jsonResponse({ error: "sale query parameter required" }, 400);
  }

  if (!SALE_CATALOG[saleKey]) {
    return jsonResponse(
      { error: `Unknown sale: ${saleKey}`, available: Object.keys(SALE_CATALOG) },
      404
    );
  }

  const accessKeyId = process.env.BREEZEUP_AWS_ACCESS_KEY_ID;
  const secretAccessKey = process.env.BREEZEUP_AWS_SECRET_ACCESS_KEY;
  if (!accessKeyId || !secretAccessKey) {
    return jsonResponse({ error: "AWS credentials not configured" }, 500);
  }

  const dataType = url.searchParams.get("type") || "sale";
  const forceSync = url.searchParams.get("sync") === "true";

  // Force sync: fetch from OBS, upload to S3, return data
  if (forceSync) {
    try {
      const { sale, stats } = await fetchAndSync(saleKey, accessKeyId, secretAccessKey);
      const data = dataType === "stats" ? stats : sale;
      return jsonResponse(data, 200, 300);
    } catch (err) {
      return jsonResponse({ error: "Sync failed", detail: err.message }, 502);
    }
  }

  // Try S3 first
  const s3Key = `data/${saleKey}/${dataType === "stats" ? "stats" : "sale"}.json`;

  try {
    const res = await s3Get(s3Key, accessKeyId, secretAccessKey);

    if (res.ok) {
      const data = await res.json();
      const cacheSec = dataType === "stats" ? 600 : 300;
      return jsonResponse(data, 200, cacheSec);
    }

    // S3 miss — auto-populate from OBS
    if (res.status === 404 || res.status === 403) {
      const { sale, stats } = await fetchAndSync(saleKey, accessKeyId, secretAccessKey);
      const data = dataType === "stats" ? stats : sale;
      return jsonResponse(data, 200, 300);
    }

    const text = await res.text();
    return jsonResponse(
      { error: "S3 read failed", status: res.status, detail: text.slice(0, 200) },
      502
    );
  } catch (err) {
    return jsonResponse(
      { error: "Failed to read sale data", detail: err.message },
      502
    );
  }
};
