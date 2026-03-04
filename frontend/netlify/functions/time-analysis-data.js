/**
 * Netlify serverless function — Aggregated Time Analysis Data
 *
 * Replaces 25+ individual sale-data calls with a single request.
 * Fetches all requested sales from S3 server-side in parallel and returns
 * only the fields needed for the Time Analysis page charts.
 *
 * Usage:
 *   /.netlify/functions/time-analysis-data?sales=obs_march_2024,obs_march_2025
 */

import { createHmac, createHash } from "node:crypto";

const BUCKET = "breezeup";
const REGION = "eu-north-1";
const HOST = `${BUCKET}.s3.${REGION}.amazonaws.com`;

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

async function s3Get(key, accessKeyId, secretAccessKey) {
  const now = new Date();
  const amzDate = now
    .toISOString()
    .replace(/[-:]/g, "")
    .replace(/\.\d+Z$/, "Z");
  const dateStamp = now.toISOString().slice(0, 10).replace(/-/g, "");
  const encodedKey = key
    .split("/")
    .map(encodeURIComponent)
    .join("/");

  const payloadHash = sha256hex("");
  const canonicalHeaders = `host:${HOST}\nx-amz-content-sha256:${payloadHash}\nx-amz-date:${amzDate}\n`;
  const signedHeaders = "host;x-amz-content-sha256;x-amz-date";

  const canonicalRequest = [
    "GET",
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
  const signature = createHmac("sha256", signingKey)
    .update(stringToSign)
    .digest("hex");

  const authorization = `AWS4-HMAC-SHA256 Credential=${accessKeyId}/${scope}, SignedHeaders=${signedHeaders}, Signature=${signature}`;

  return fetch(`https://${HOST}/${encodedKey}`, {
    headers: {
      Host: HOST,
      "x-amz-date": amzDate,
      "x-amz-content-sha256": payloadHash,
      Authorization: authorization,
    },
  });
}

/* ── Validate sale key format ──────────────────────────────── */

const SALE_KEY_PATTERN = /^[a-z][a-z0-9_]*_20\d{2}$/;

/* ── Response helpers ───────────────────────────────────────── */

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type",
};

function jsonResponse(body, status = 200, cacheSeconds = 3600) {
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
  const salesParam = url.searchParams.get("sales");

  if (!salesParam) {
    return jsonResponse(
      { error: "sales query parameter required (comma-separated sale keys)" },
      400
    );
  }

  const saleKeys = salesParam
    .split(",")
    .map((k) => k.trim())
    .filter((k) => SALE_KEY_PATTERN.test(k));

  if (saleKeys.length === 0) {
    return jsonResponse({ error: "No valid sale keys provided" }, 400);
  }

  if (saleKeys.length > 30) {
    return jsonResponse({ error: "Too many sales requested (max 30)" }, 400);
  }

  const accessKeyId = process.env.BREEZEUP_AWS_ACCESS_KEY_ID;
  const secretAccessKey = process.env.BREEZEUP_AWS_SECRET_ACCESS_KEY;

  if (!accessKeyId || !secretAccessKey) {
    return jsonResponse({ error: "AWS credentials not configured" }, 500);
  }

  try {
    const results = await Promise.all(
      saleKeys.map(async (saleKey) => {
        try {
          const res = await s3Get(
            `data/${saleKey}/sale.json`,
            accessKeyId,
            secretAccessKey
          );
          if (!res.ok) return null;
          const data = await res.json();
          if (!data?.hips) return null;

          // Extract only fields needed for Time Analysis,
          // pre-filter to hips with breeze times
          const hips = [];
          for (const h of data.hips) {
            if (!h.under_tack_time || !h.under_tack_distance) continue;
            hips.push({
              hip_number: h.hip_number,
              under_tack_time: h.under_tack_time,
              under_tack_distance: h.under_tack_distance.trim(),
              sale_price: h.sale_price || null,
              sale_status: h.sale_status || "pending",
              sire: h.sire || null,
              dam: h.dam || null,
              horse_name: h.horse_name || null,
              consignor: h.consignor || null,
              sex: h.sex || null,
            });
          }
          return [saleKey, hips];
        } catch {
          return null;
        }
      })
    );

    const sales = {};
    for (const entry of results) {
      if (entry) sales[entry[0]] = entry[1];
    }

    return jsonResponse({ sales }, 200, 3600);
  } catch (err) {
    return jsonResponse(
      { error: "Failed to aggregate time analysis data", detail: err.message },
      502
    );
  }
};
