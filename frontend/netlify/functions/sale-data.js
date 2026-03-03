/**
 * Netlify serverless function — S3 Sale Data Reader
 *
 * Reads pre-processed sale JSON from S3. Data is populated by
 * scripts/sync_to_s3.py or manually uploaded.
 *
 * Usage:
 *   Full sale:  /.netlify/functions/sale-data?sale=obs_march_2025
 *   Stats only: /.netlify/functions/sale-data?sale=obs_march_2025&type=stats
 *   Catalog:    /.netlify/functions/sale-data?catalog=true
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
  const amzDate = now.toISOString().replace(/[-:]/g, "").replace(/\.\d+Z$/, "Z");
  const dateStamp = now.toISOString().slice(0, 10).replace(/-/g, "");
  const encodedKey = key.split("/").map(encodeURIComponent).join("/");

  const payloadHash = sha256hex("");
  const canonicalHeaders = `host:${HOST}\nx-amz-content-sha256:${payloadHash}\nx-amz-date:${amzDate}\n`;
  const signedHeaders = "host;x-amz-content-sha256;x-amz-date";

  const canonicalRequest = [
    "GET", `/${encodedKey}`, "",
    canonicalHeaders, signedHeaders, payloadHash,
  ].join("\n");

  const scope = `${dateStamp}/${REGION}/s3/aws4_request`;
  const stringToSign = [
    "AWS4-HMAC-SHA256", amzDate, scope, sha256hex(canonicalRequest),
  ].join("\n");

  const signingKey = getSigningKey(secretAccessKey, dateStamp);
  const signature = createHmac("sha256", signingKey).update(stringToSign).digest("hex");

  return fetch(`https://${HOST}/${encodedKey}`, {
    headers: {
      Host: HOST,
      "x-amz-date": amzDate,
      "x-amz-content-sha256": payloadHash,
      Authorization:
        `AWS4-HMAC-SHA256 Credential=${accessKeyId}/${scope}, ` +
        `SignedHeaders=${signedHeaders}, Signature=${signature}`,
    },
  });
}

/* ── Known sales catalog ────────────────────────────────────── */

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
  const s3Key = `data/${saleKey}/${dataType === "stats" ? "stats" : "sale"}.json`;

  try {
    const res = await s3Get(s3Key, accessKeyId, secretAccessKey);

    if (res.status === 404 || res.status === 403) {
      return jsonResponse(
        { error: `No data found for ${saleKey} in S3`, s3Key },
        404
      );
    }

    if (!res.ok) {
      const text = await res.text();
      return jsonResponse(
        { error: "S3 read failed", status: res.status, detail: text.slice(0, 200) },
        502
      );
    }

    const data = await res.json();
    const cacheSec = dataType === "stats" ? 600 : 300;
    return jsonResponse(data, 200, cacheSec);
  } catch (err) {
    return jsonResponse(
      { error: "Failed to read sale data from S3", detail: err.message },
      502
    );
  }
};
