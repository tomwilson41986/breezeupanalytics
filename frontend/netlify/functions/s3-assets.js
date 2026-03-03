/**
 * Netlify serverless function — S3 Asset URL Generator
 *
 * Returns pre-signed URLs for horse assets stored in the breezeup S3 bucket.
 *
 * Usage:
 *   Single hip:  /.netlify/functions/s3-assets?sale=obs_march_2025&hip=101
 *   List assets:  /.netlify/functions/s3-assets?sale=obs_march_2025&list=true
 *
 * Environment variables required:
 *   BREEZEUP_AWS_ACCESS_KEY_ID
 *   BREEZEUP_AWS_SECRET_ACCESS_KEY
 */

import { S3Client, GetObjectCommand, ListObjectsV2Command } from "@aws-sdk/client-s3";
import { getSignedUrl } from "@aws-sdk/s3-request-presigner";

const BUCKET = "breezeup";
const REGION = "eu-north-1";
const SIGNED_URL_EXPIRY = 3600; // 1 hour

function getS3Client() {
  return new S3Client({
    region: REGION,
    credentials: {
      accessKeyId: process.env.BREEZEUP_AWS_ACCESS_KEY_ID,
      secretAccessKey: process.env.BREEZEUP_AWS_SECRET_ACCESS_KEY,
    },
  });
}

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
 * Generate a pre-signed URL for a specific S3 key
 */
async function getPresignedUrl(client, key) {
  try {
    const command = new GetObjectCommand({ Bucket: BUCKET, Key: key });
    return await getSignedUrl(client, command, { expiresIn: SIGNED_URL_EXPIRY });
  } catch {
    return null;
  }
}

/**
 * Get all available assets for a single hip
 */
async function getHipAssets(client, saleKey, hipNumber) {
  const prefix = `videos/${saleKey}/`;

  // Asset naming conventions observed in the bucket:
  //   {hip}.mp4     — breeze video
  //   {hip}w.mp4    — walk video
  //   {hip}p.jpg    — conformation photo
  //   {hip}.pdf     — pedigree PDF
  const assetKeys = {
    video: `${prefix}${hipNumber}.mp4`,
    walkVideo: `${prefix}${hipNumber}w.mp4`,
    photo: `${prefix}${hipNumber}p.jpg`,
    pedigree: `${prefix}${hipNumber}.pdf`,
  };

  const results = {};
  const entries = Object.entries(assetKeys);

  const urls = await Promise.all(
    entries.map(([, key]) => getPresignedUrl(client, key))
  );

  for (let i = 0; i < entries.length; i++) {
    const [type] = entries[i];
    if (urls[i]) results[type] = urls[i];
  }

  return results;
}

/**
 * List all hip numbers that have assets for a sale
 */
async function listSaleAssets(client, saleKey) {
  const prefix = `videos/${saleKey}/`;
  const hipMap = {};

  let continuationToken;
  do {
    const command = new ListObjectsV2Command({
      Bucket: BUCKET,
      Prefix: prefix,
      ContinuationToken: continuationToken,
    });
    const response = await client.send(command);

    for (const obj of response.Contents || []) {
      const filename = obj.Key.replace(prefix, "");
      // Parse hip number from filename patterns: 101.mp4, 101w.mp4, 101p.jpg, 101.pdf
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

    continuationToken = response.IsTruncated ? response.NextContinuationToken : undefined;
  } while (continuationToken);

  return hipMap;
}

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

  if (!process.env.BREEZEUP_AWS_ACCESS_KEY_ID || !process.env.BREEZEUP_AWS_SECRET_ACCESS_KEY) {
    return jsonResponse({ error: "AWS credentials not configured" }, 500);
  }

  const client = getS3Client();

  try {
    if (listMode) {
      const assets = await listSaleAssets(client, saleKey);
      return jsonResponse({ sale: saleKey, assets });
    }

    if (!hipNumber) {
      return jsonResponse({ error: "hip query parameter is required (e.g. 101)" }, 400);
    }

    const assets = await getHipAssets(client, saleKey, hipNumber);
    return jsonResponse({ sale: saleKey, hip: hipNumber, assets });
  } catch (err) {
    return jsonResponse({ error: "Failed to fetch S3 assets", detail: err.message }, 502);
  }
};
