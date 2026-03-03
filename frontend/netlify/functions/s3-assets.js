/**
 * Netlify serverless function — S3 Asset URL Generator
 *
 * Zero external dependencies — uses Node.js built-in crypto for AWS SigV4 signing.
 *
 * Usage:
 *   Single hip:  /.netlify/functions/s3-assets?sale=obs_march_2025&hip=101
 *   List assets:  /.netlify/functions/s3-assets?sale=obs_march_2025&list=true
 *
 * Environment variables required:
 *   BREEZEUP_AWS_ACCESS_KEY_ID
 *   BREEZEUP_AWS_SECRET_ACCESS_KEY
 */

import { createHmac, createHash } from "node:crypto";

const BUCKET = "breezeup";
const REGION = "eu-north-1";
const SERVICE = "s3";
const HOST = `${BUCKET}.s3.${REGION}.amazonaws.com`;
const SIGNED_URL_EXPIRY = 3600;

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
  const kService = hmac(kRegion, SERVICE);
  return hmac(kService, "aws4_request");
}

function toAmzDate(date) {
  return date.toISOString().replace(/[-:]/g, "").replace(/\.\d+Z$/, "Z");
}

function toDateStamp(date) {
  return date.toISOString().slice(0, 10).replace(/-/g, "");
}

/**
 * Generate a pre-signed GET URL for an S3 object
 */
function presignUrl(key, accessKeyId, secretAccessKey) {
  const now = new Date();
  const amzDate = toAmzDate(now);
  const dateStamp = toDateStamp(now);
  const credential = `${accessKeyId}/${dateStamp}/${REGION}/${SERVICE}/aws4_request`;
  const encodedKey = key.split("/").map(encodeURIComponent).join("/");

  const queryParams = new URLSearchParams({
    "X-Amz-Algorithm": "AWS4-HMAC-SHA256",
    "X-Amz-Credential": credential,
    "X-Amz-Date": amzDate,
    "X-Amz-Expires": String(SIGNED_URL_EXPIRY),
    "X-Amz-SignedHeaders": "host",
  });
  queryParams.sort();

  const canonicalRequest = [
    "GET",
    `/${encodedKey}`,
    queryParams.toString(),
    `host:${HOST}\n`,
    "host",
    "UNSIGNED-PAYLOAD",
  ].join("\n");

  const stringToSign = [
    "AWS4-HMAC-SHA256",
    amzDate,
    `${dateStamp}/${REGION}/${SERVICE}/aws4_request`,
    sha256hex(canonicalRequest),
  ].join("\n");

  const signingKey = getSigningKey(secretAccessKey, dateStamp);
  const signature = createHmac("sha256", signingKey)
    .update(stringToSign)
    .digest("hex");

  return `https://${HOST}/${encodedKey}?${queryParams.toString()}&X-Amz-Signature=${signature}`;
}

/* ── S3 REST API helpers ────────────────────────────────────── */

/**
 * Make a signed GET request to S3 REST API (for ListObjectsV2)
 */
async function s3Request(path, queryParams, accessKeyId, secretAccessKey) {
  const now = new Date();
  const amzDate = toAmzDate(now);
  const dateStamp = toDateStamp(now);

  const qs = new URLSearchParams(queryParams);
  qs.sort();

  const payloadHash = sha256hex("");
  const canonicalHeaders = `host:${HOST}\nx-amz-content-sha256:${payloadHash}\nx-amz-date:${amzDate}\n`;
  const signedHeaders = "host;x-amz-content-sha256;x-amz-date";

  const canonicalRequest = [
    "GET",
    path,
    qs.toString(),
    canonicalHeaders,
    signedHeaders,
    payloadHash,
  ].join("\n");

  const scope = `${dateStamp}/${REGION}/${SERVICE}/aws4_request`;
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

  const url = `https://${HOST}${path}?${qs.toString()}`;
  const res = await fetch(url, {
    headers: {
      Host: HOST,
      "x-amz-date": amzDate,
      "x-amz-content-sha256": payloadHash,
      Authorization: authorization,
    },
  });

  if (!res.ok) {
    throw new Error(`S3 API error: ${res.status} ${await res.text()}`);
  }

  return res.text();
}

/**
 * Check if an S3 object exists using HEAD request
 */
async function s3HeadObject(key, accessKeyId, secretAccessKey) {
  const now = new Date();
  const amzDate = toAmzDate(now);
  const dateStamp = toDateStamp(now);
  const encodedKey = key.split("/").map(encodeURIComponent).join("/");

  const payloadHash = sha256hex("");
  const canonicalHeaders = `host:${HOST}\nx-amz-content-sha256:${payloadHash}\nx-amz-date:${amzDate}\n`;
  const signedHeaders = "host;x-amz-content-sha256;x-amz-date";

  const canonicalRequest = [
    "HEAD",
    `/${encodedKey}`,
    "",
    canonicalHeaders,
    signedHeaders,
    payloadHash,
  ].join("\n");

  const scope = `${dateStamp}/${REGION}/${SERVICE}/aws4_request`;
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

  try {
    const res = await fetch(`https://${HOST}/${encodedKey}`, {
      method: "HEAD",
      headers: {
        Host: HOST,
        "x-amz-date": amzDate,
        "x-amz-content-sha256": payloadHash,
        Authorization: authorization,
      },
    });
    return res.ok;
  } catch {
    return false;
  }
}

/* ── Business logic ─────────────────────────────────────────── */

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type",
};

function jsonResponse(body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      "Content-Type": "application/json",
      "Cache-Control": "public, max-age=1800, s-maxage=3600",
      ...corsHeaders,
    },
  });
}

/**
 * Get pre-signed URLs for a single hip's assets.
 * Only includes assets that actually exist in S3.
 */
async function getHipAssets(saleKey, hipNumber, accessKeyId, secretAccessKey) {
  const prefix = `videos/${saleKey}/`;
  const assetDefs = [
    { type: "video", key: `${prefix}${hipNumber}.mp4` },
    { type: "walkVideo", key: `${prefix}${hipNumber}w.mp4` },
    { type: "photo", key: `${prefix}${hipNumber}p.jpg` },
    { type: "pedigree", key: `${prefix}${hipNumber}.pdf` },
  ];

  const existChecks = await Promise.all(
    assetDefs.map((d) => s3HeadObject(d.key, accessKeyId, secretAccessKey))
  );

  const results = {};
  for (let i = 0; i < assetDefs.length; i++) {
    if (existChecks[i]) {
      results[assetDefs[i].type] = presignUrl(assetDefs[i].key, accessKeyId, secretAccessKey);
    }
  }

  return results;
}

/**
 * List all hip numbers that have assets for a sale using S3 ListObjectsV2.
 */
async function listSaleAssets(saleKey, accessKeyId, secretAccessKey) {
  const prefix = `videos/${saleKey}/`;
  const hipMap = {};

  let continuationToken;
  do {
    const params = {
      "list-type": "2",
      prefix,
    };
    if (continuationToken) params["continuation-token"] = continuationToken;

    const xml = await s3Request("/", params, accessKeyId, secretAccessKey);

    // Parse XML response (simple regex — no XML parser needed)
    const keys = [...xml.matchAll(/<Key>([^<]+)<\/Key>/g)].map((m) => m[1]);
    const isTruncated = xml.includes("<IsTruncated>true</IsTruncated>");
    const tokenMatch = xml.match(/<NextContinuationToken>([^<]+)<\/NextContinuationToken>/);

    for (const key of keys) {
      const filename = key.replace(prefix, "");
      const match = filename.match(/^(\d+)(w|p)?\.(mp4|jpg|pdf)$/);
      if (!match) continue;

      const hip = match[1];
      const suffix = match[2] || "";
      const ext = match[3];

      if (!hipMap[hip]) hipMap[hip] = {};

      if (ext === "mp4" && suffix === "") hipMap[hip].video = true;
      else if (ext === "mp4" && suffix === "w") hipMap[hip].walkVideo = true;
      else if (ext === "jpg" && suffix === "p") hipMap[hip].photo = true;
      else if (ext === "pdf") hipMap[hip].pedigree = true;
    }

    continuationToken = isTruncated && tokenMatch ? tokenMatch[1] : undefined;
  } while (continuationToken);

  return hipMap;
}

/* ── Handler ────────────────────────────────────────────────── */

export default async (req) => {
  if (req.method === "OPTIONS") {
    return new Response(null, { status: 204, headers: corsHeaders });
  }

  const url = new URL(req.url);
  const saleKey = url.searchParams.get("sale");
  const hipNumber = url.searchParams.get("hip");
  const listMode = url.searchParams.get("list") === "true";

  if (!saleKey) {
    return jsonResponse({ error: "sale query parameter is required (e.g. obs_march_2025)" }, 400);
  }

  const accessKeyId = process.env.BREEZEUP_AWS_ACCESS_KEY_ID;
  const secretAccessKey = process.env.BREEZEUP_AWS_SECRET_ACCESS_KEY;

  if (!accessKeyId || !secretAccessKey) {
    return jsonResponse({ error: "AWS credentials not configured" }, 500);
  }

  try {
    if (listMode) {
      const assets = await listSaleAssets(saleKey, accessKeyId, secretAccessKey);
      return jsonResponse({ sale: saleKey, assets });
    }

    if (!hipNumber) {
      return jsonResponse({ error: "hip query parameter is required (e.g. 101)" }, 400);
    }

    const assets = await getHipAssets(saleKey, hipNumber, accessKeyId, secretAccessKey);
    return jsonResponse({ sale: saleKey, hip: hipNumber, assets });
  } catch (err) {
    return jsonResponse({ error: "Failed to fetch S3 assets", detail: err.message }, 502);
  }
};
