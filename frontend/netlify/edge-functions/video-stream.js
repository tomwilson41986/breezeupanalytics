/**
 * Edge Function — Video Streaming Proxy
 *
 * Proxies video content from S3 (eu-north-1) through Netlify's CDN edge.
 * This eliminates transatlantic latency for US users by caching at edge POPs.
 *
 * Supports HTTP Range requests for proper video seeking.
 *
 * URL pattern: /v/{saleKey}/{filename}
 * Example:     /v/obs_march_2026/101.mp4
 */

const BUCKET = "breezeup";
const REGION = "eu-north-1";
const SERVICE = "s3";
const HOST = `${BUCKET}.s3.${REGION}.amazonaws.com`;
const SIGNED_URL_EXPIRY = 3600;

/* ── Web Crypto SigV4 helpers ─────────────────────────────── */

const encoder = new TextEncoder();

async function hmac(key, data) {
  const cryptoKey = await crypto.subtle.importKey(
    "raw",
    typeof key === "string" ? encoder.encode(key) : key,
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"]
  );
  return new Uint8Array(
    await crypto.subtle.sign("HMAC", cryptoKey, encoder.encode(data))
  );
}

async function sha256hex(data) {
  const hash = await crypto.subtle.digest("SHA-256", encoder.encode(data));
  return Array.from(new Uint8Array(hash))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

async function getSigningKey(secretKey, dateStamp) {
  const kDate = await hmac(`AWS4${secretKey}`, dateStamp);
  const kRegion = await hmac(kDate, REGION);
  const kService = await hmac(kRegion, SERVICE);
  return hmac(kService, "aws4_request");
}

function toAmzDate(date) {
  return date.toISOString().replace(/[-:]/g, "").replace(/\.\d+Z$/, "Z");
}

function toDateStamp(date) {
  return date.toISOString().slice(0, 10).replace(/-/g, "");
}

async function presignUrl(key, accessKeyId, secretAccessKey) {
  const now = new Date();
  const amzDate = toAmzDate(now);
  const dateStamp = toDateStamp(now);
  const credential = `${accessKeyId}/${dateStamp}/${REGION}/${SERVICE}/aws4_request`;
  const encodedKey = key
    .split("/")
    .map(encodeURIComponent)
    .join("/");

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
    await sha256hex(canonicalRequest),
  ].join("\n");

  const signingKey = await getSigningKey(secretAccessKey, dateStamp);
  const signatureKey = await crypto.subtle.importKey(
    "raw",
    signingKey,
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"]
  );
  const signatureBytes = new Uint8Array(
    await crypto.subtle.sign("HMAC", signatureKey, encoder.encode(stringToSign))
  );
  const signature = Array.from(signatureBytes)
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");

  return `https://${HOST}/${encodedKey}?${queryParams.toString()}&X-Amz-Signature=${signature}`;
}

/* ── Handler ──────────────────────────────────────────────── */

export default async function handler(req, context) {
  const url = new URL(req.url);

  // Parse /v/{saleKey}/{filename}
  const match = url.pathname.match(/^\/v\/([^/]+)\/(.+)$/);
  if (!match) {
    return new Response("Not found", { status: 404 });
  }

  const [, saleKey, filename] = match;

  // Validate filename to prevent path traversal
  if (!/^\d+w?\.(mp4)$/.test(filename)) {
    return new Response("Invalid filename", { status: 400 });
  }

  const accessKeyId = Netlify.env.get("BREEZEUP_AWS_ACCESS_KEY_ID");
  const secretAccessKey = Netlify.env.get("BREEZEUP_AWS_SECRET_ACCESS_KEY");

  if (!accessKeyId || !secretAccessKey) {
    return new Response("Server configuration error", { status: 500 });
  }

  const s3Key = `videos/${saleKey}/${filename}`;

  try {
    const signedUrl = await presignUrl(s3Key, accessKeyId, secretAccessKey);

    // Forward Range header for video seeking
    const fetchHeaders = {};
    const rangeHeader = req.headers.get("range");
    if (rangeHeader) {
      fetchHeaders["Range"] = rangeHeader;
    }

    const s3Res = await fetch(signedUrl, { headers: fetchHeaders });

    if (!s3Res.ok && s3Res.status !== 206) {
      return new Response("Video not found", { status: 404 });
    }

    // Build response headers
    const responseHeaders = new Headers();
    responseHeaders.set("Content-Type", "video/mp4");
    responseHeaders.set("Accept-Ranges", "bytes");

    // CDN caching: 1 day browser, 7 days CDN edge
    responseHeaders.set(
      "Cache-Control",
      "public, max-age=86400, s-maxage=604800"
    );

    // Forward content headers from S3
    const contentLength = s3Res.headers.get("content-length");
    if (contentLength) responseHeaders.set("Content-Length", contentLength);

    const contentRange = s3Res.headers.get("content-range");
    if (contentRange) responseHeaders.set("Content-Range", contentRange);

    // CORS
    responseHeaders.set("Access-Control-Allow-Origin", "*");

    return new Response(s3Res.body, {
      status: s3Res.status, // 200 or 206
      headers: responseHeaders,
    });
  } catch (err) {
    return new Response("Failed to fetch video", { status: 502 });
  }
}

export const config = {
  path: "/v/*",
};
