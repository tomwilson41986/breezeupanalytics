/**
 * Netlify serverless function — S3 Sale Data Reader
 *
 * Reads pre-processed sale JSON from S3 (uploaded by scripts/sync_to_s3.py).
 * Zero external dependencies — uses Node.js built-in crypto for AWS SigV4.
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

/**
 * GET an object from S3 with SigV4 authentication
 */
async function s3Get(key, accessKeyId, secretAccessKey) {
  const now = new Date();
  const amzDate = now.toISOString().replace(/[-:]/g, "").replace(/\.\d+Z$/, "Z");
  const dateStamp = now.toISOString().slice(0, 10).replace(/-/g, "");
  const encodedKey = key.split("/").map(encodeURIComponent).join("/");

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

  const res = await fetch(`https://${HOST}/${encodedKey}`, {
    headers: {
      Host: HOST,
      "x-amz-date": amzDate,
      "x-amz-content-sha256": payloadHash,
      Authorization: authorization,
    },
  });

  return res;
}

/* ── Validate sale key format ──────────────────────────────── */

const SALE_KEY_PATTERN = /^[a-z][a-z0-9_]*_20\d{2}$/;

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

  const saleKey = url.searchParams.get("sale");
  if (!saleKey) {
    return jsonResponse(
      { error: "sale query parameter required (e.g. obs_march_2025)" },
      400
    );
  }

  if (!SALE_KEY_PATTERN.test(saleKey)) {
    return jsonResponse(
      { error: `Invalid sale key format: ${saleKey}` },
      400
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

    if (res.status === 404) {
      return jsonResponse(
        {
          error: `No data found for ${saleKey}. Run sync_to_s3.py to populate.`,
          s3Key,
        },
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
    // Cache sale data longer (5 min), stats even longer (10 min)
    const cacheSec = dataType === "stats" ? 600 : 300;
    return jsonResponse(data, 200, cacheSec);
  } catch (err) {
    return jsonResponse(
      { error: "Failed to read sale data from S3", detail: err.message },
      502
    );
  }
};
