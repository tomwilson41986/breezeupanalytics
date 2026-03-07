/**
 * Publish ratings, times, and stride data to the frontend for Netlify.
 *
 * This script runs during `netlify build` to ensure the latest data
 * from source CSVs and under-tack JSON files are available as static
 * assets in frontend/public/data/.
 *
 * Steps:
 *  1. Convert rated CSV(s) → ratings JSON  (frontend/public/data/live-sale-times/{sale}_ratings.json)
 *  2. Convert times CSV(s) → times JSON    (frontend/public/data/live-sale-times/{sale}.json)
 *  3. Copy under-tack JSON data            (frontend/public/data/under-tack/)
 *
 * Usage:
 *   node scripts/publish-data.mjs
 */

import { readFileSync, writeFileSync, readdirSync, mkdirSync, cpSync, existsSync } from "fs";
import { join, dirname } from "path";
import { fileURLToPath } from "url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = join(__dirname, "..");
const FRONTEND_PUBLIC = join(ROOT, "frontend/public/data");

/* ── Sale key mapping ─────────────────────────────────────────
 * Maps rated CSV filenames (without _rated.csv) to sale keys.
 * Add new entries as new sales are processed.
 */
const RATINGS_FILE_MAP = {
  "obsMarch stride": "obs_march_2026",
};

/* ── CSV Helpers ──────────────────────────────────────────── */

function splitCsvRow(line) {
  const fields = [];
  let current = "";
  let inQuotes = false;
  for (let i = 0; i < line.length; i++) {
    const ch = line[i];
    if (inQuotes) {
      if (ch === '"' && line[i + 1] === '"') {
        current += '"';
        i++;
      } else if (ch === '"') {
        inQuotes = false;
      } else {
        current += ch;
      }
    } else {
      if (ch === '"') {
        inQuotes = true;
      } else if (ch === ",") {
        fields.push(current.trim());
        current = "";
      } else {
        current += ch;
      }
    }
  }
  fields.push(current.trim());
  return fields;
}

function parseNumber(val) {
  if (!val || val === "-" || val === "—" || val === "") return null;
  const n = Number(val);
  return isNaN(n) ? val : n;
}

/* ── 1. Convert Rated CSV → Ratings JSON ──────────────────── */

function convertRatedCsvToJson(csvPath) {
  const text = readFileSync(csvPath, "utf-8");
  const lines = text.trim().split(/\r?\n/);
  if (lines.length < 2) return {};

  const headers = splitCsvRow(lines[0]).map((h) => h.trim());
  const ratings = {};

  for (let i = 1; i < lines.length; i++) {
    const vals = splitCsvRow(lines[i]);
    if (!vals.length || vals.every((v) => !v)) continue;

    const row = {};
    for (let j = 0; j < headers.length; j++) {
      row[headers[j]] = vals[j]?.trim() || "";
    }

    const hip = parseNumber(row["Hip"]);
    if (hip == null || typeof hip !== "number") continue;
    const hipKey = String(Math.floor(hip));

    const entry = {};

    // Core rating
    const rating = parseNumber(row["Rating"]);
    if (rating != null && typeof rating === "number") entry.rating = Math.round(rating * 10) / 10;

    const meanRank = parseNumber(row["Mean Rank"]);
    if (meanRank != null && typeof meanRank === "number") entry.meanRank = Math.round(meanRank * 100) / 100;

    // Distance group
    const distUT = row["Distance UT"];
    if (distUT) entry.distanceUT = distUT;

    // Stride lengths (feet)
    const slUT = parseNumber(row["Stride Length UT (ft)"]);
    if (slUT != null && typeof slUT === "number") entry.strideLengthUT = Math.round(slUT * 100) / 100;

    const slGO = parseNumber(row["Stride Length GO (ft)"]);
    if (slGO != null && typeof slGO === "number") entry.strideLengthGO = Math.round(slGO * 100) / 100;

    // Stride frequencies (Hz)
    const sfUT = parseNumber(row["Stride Frequency UT"]);
    if (sfUT != null && typeof sfUT === "number") entry.strideFreqUT = Math.round(sfUT * 100) / 100;

    const sfGO = parseNumber(row["Stride Frequency GO"]);
    if (sfGO != null && typeof sfGO === "number") entry.strideFreqGO = Math.round(sfGO * 100) / 100;

    // Times
    const timeUT = parseNumber(row["Time UT"]);
    if (timeUT != null && typeof timeUT === "number") entry.timeUT = Math.round(timeUT * 100) / 100;

    const timeGO = parseNumber(row["Time GO"]);
    if (timeGO != null && typeof timeGO === "number") entry.timeGO = Math.round(timeGO * 100) / 100;

    // Diff
    const diff = parseNumber(row["diff"]);
    if (diff != null && typeof diff === "number") entry.diff = Math.round(diff * 100) / 100;

    // Individual ranks
    const rankMap = {
      "Rank Time UT": "rankTimeUt",
      "Rank Time GO": "rankTimeGo",
      "Rank Stride Length UT (ft)": "rankStrideLengthUt",
      "Rank Stride Length GO (ft)": "rankStrideLengthGo",
      "Rank diff": "rankDiff",
    };
    for (const [csvCol, jsonKey] of Object.entries(rankMap)) {
      const v = parseNumber(row[csvCol]);
      if (v != null && typeof v === "number") entry[jsonKey] = Math.floor(v);
    }

    if (Object.keys(entry).length > 0) {
      ratings[hipKey] = entry;
    }
  }

  return ratings;
}

/* ── 2. Convert Times CSV → Times JSON ────────────────────── */

function normalizeHeader(header) {
  const h = header.toLowerCase().replace(/#/g, "").replace(/\s+/g, "_").replace(/[^a-z0-9_]/g, "");
  const aliases = {
    hip: "hip_number",
    hip_number: "hip_number",
    hipnumber: "hip_number",
    hipno: "hip_number",
    hip_no: "hip_number",
  };
  return aliases[h] || h;
}

function convertTimesCsvToJson(csvPath, saleKey) {
  const text = readFileSync(csvPath, "utf-8");
  const lines = text.trim().split(/\r?\n/);
  if (lines.length < 2) return null;

  const rawHeaders = splitCsvRow(lines[0]);
  const headers = rawHeaders.map(normalizeHeader);

  // Build column label mapping
  const columnLabels = {};
  for (let i = 0; i < rawHeaders.length; i++) {
    const norm = normalizeHeader(rawHeaders[i]);
    if (norm) columnLabels[norm] = rawHeaders[i].trim();
  }

  const hips = {};
  for (let i = 1; i < lines.length; i++) {
    const vals = splitCsvRow(lines[i]);
    if (!vals.length || vals.every((v) => !v)) continue;

    const record = {};
    for (let j = 0; j < headers.length; j++) {
      record[headers[j]] = parseNumber(vals[j]);
    }

    const hipNum = record.hip_number;
    if (hipNum == null) continue;
    const key = String(typeof hipNum === "number" && hipNum % 1 === 0 ? hipNum : hipNum);
    hips[key] = record;
  }

  return {
    sale_key: saleKey,
    generated_at: new Date().toISOString(),
    count: Object.keys(hips).length,
    columns: headers,
    column_labels: columnLabels,
    hips,
  };
}

/* ── Main ─────────────────────────────────────────────────── */

function main() {
  const ratingsDir = join(ROOT, "data/ratings");
  const underTackDir = join(ROOT, "data/under-tack");
  const liveSaleTimesDir = join(FRONTEND_PUBLIC, "live-sale-times");
  const publicUnderTackDir = join(FRONTEND_PUBLIC, "under-tack");

  mkdirSync(liveSaleTimesDir, { recursive: true });
  mkdirSync(publicUnderTackDir, { recursive: true });

  let totalRatings = 0;
  let totalTimes = 0;

  // 1. Convert rated CSVs → ratings JSON
  if (existsSync(ratingsDir)) {
    const ratedFiles = readdirSync(ratingsDir).filter((f) => f.endsWith("_rated.csv"));
    for (const file of ratedFiles) {
      const baseName = file.replace("_rated.csv", "");
      const saleKey = RATINGS_FILE_MAP[baseName];
      if (!saleKey) {
        console.log(`  [skip] No sale key mapping for: ${file}`);
        continue;
      }

      const csvPath = join(ratingsDir, file);
      const ratings = convertRatedCsvToJson(csvPath);
      const count = Object.keys(ratings).length;

      const outPath = join(liveSaleTimesDir, `${saleKey}_ratings.json`);
      writeFileSync(outPath, JSON.stringify(ratings, null, 2));
      console.log(`  [ratings] ${file} → ${saleKey}_ratings.json (${count} hips)`);
      totalRatings += count;
    }
  }

  // 2. Convert times CSVs → times JSON (if CSV exists in live-sale-times)
  if (existsSync(liveSaleTimesDir)) {
    const csvFiles = readdirSync(liveSaleTimesDir).filter(
      (f) => f.endsWith(".csv") && !f.endsWith("_rated.csv")
    );
    for (const file of csvFiles) {
      const saleKey = file.replace(".csv", "");
      const csvPath = join(liveSaleTimesDir, file);
      const data = convertTimesCsvToJson(csvPath, saleKey);
      if (data) {
        const outPath = join(liveSaleTimesDir, `${saleKey}.json`);
        writeFileSync(outPath, JSON.stringify(data, null, 2));
        console.log(`  [times] ${file} → ${saleKey}.json (${data.count} hips)`);
        totalTimes += data.count;
      }
    }
  }

  // 3. Copy under-tack data to frontend public
  if (existsSync(underTackDir)) {
    const saleDirs = readdirSync(underTackDir).filter(
      (d) => !d.startsWith(".")
    );
    for (const saleDir of saleDirs) {
      const src = join(underTackDir, saleDir);
      const dest = join(publicUnderTackDir, saleDir);
      cpSync(src, dest, { recursive: true });
      console.log(`  [under-tack] ${saleDir} → public/data/under-tack/${saleDir}/`);
    }
  }

  console.log(
    `\nPublish complete: ${totalRatings} ratings, ${totalTimes} times records, under-tack synced.`
  );
}

console.log("Publishing ratings, times & stride data to frontend...\n");
main();
