/**
 * Mapping table between historic sales data and S3 assets.
 *
 * This file defines the authoritative link between:
 *   1. Historic sales records (from the Excel / vendor-data.json)
 *   2. S3 asset paths (videos/{s3Key}/{hip}.mp4 etc.)
 *   3. OBS catalog IDs (for live API access, where known)
 *
 * Each entry maps a (saleEntity, year) pair from the historic data
 * to the S3 key used for asset storage and retrieval.
 *
 * Usage:
 *   import { SALE_ASSET_MAP, lookupS3Key } from './sale-asset-map';
 *   const s3Key = lookupS3Key('OBS March Sale', 2023);
 *   // => 'obs_march_2023'
 */

// ── OBS Sales ────────────────────────────────────────────────────
// S3 key pattern: obs_{season}_{year}
// S3 asset path:  videos/obs_{season}_{year}/{hip}.mp4
//
// Historic data "sale" (SaleEntity) values:
//   "OBS March Sale"  → obs_march_{year}
//   "OBS Spring Sale" → obs_spring_{year}
//   "OBS June Sale"   → obs_june_{year}
//
// Special cases:
//   "July 2yo Sale" (2020 only) → obs_june_2020
//     The June sale was held in July 2020 due to COVID-19 delays.
//     The Excel labels it separately but it is the same sale series.

// ── Fasig-Tipton Sales ───────────────────────────────────────────
// S3 key pattern: ft_{sale}_{year}
// S3 asset path:  videos/ft_{sale}_{year}/{hip}.mp4
//
// Historic data "sale" (SaleEntity) values:
//   "Fasig Tipton Midlantic Sale" → ft_midlantic_{year}
//   "Gulfstream Sale"             → ft_gulfstream_{year}

// ── Other Sales ──────────────────────────────────────────────────
// S3 key pattern: {company}_{sale}_{year}
//   "Santa Anita 2yo Sale"  → ft_santaanita_{year}
//   "Texas 2yo Sale"        → texas_2yo_{year}

/**
 * Complete mapping of every (saleEntity, year) combination found in the
 * historic data to its corresponding S3 key, display name, hip range,
 * record count, and OBS catalog ID (where known).
 */
export const SALE_ASSET_MAP = [
  // ── OBS March Sales ──────────────────────────────────────────
  { saleEntity: "OBS March Sale", year: 2017, s3Key: "obs_march_2017", displayName: "OBS March 2YO in Training 2017", company: "OBS", month: 3, location: "Ocala, FL", hipRange: [1, 677], recordCount: 674, obsId: null },
  { saleEntity: "OBS March Sale", year: 2018, s3Key: "obs_march_2018", displayName: "OBS March 2YO in Training 2018", company: "OBS", month: 3, location: "Ocala, FL", hipRange: [1, 375], recordCount: 375, obsId: null },
  { saleEntity: "OBS March Sale", year: 2019, s3Key: "obs_march_2019", displayName: "OBS March 2YO in Training 2019", company: "OBS", month: 3, location: "Ocala, FL", hipRange: [1, 577], recordCount: 575, obsId: null },
  { saleEntity: "OBS March Sale", year: 2020, s3Key: "obs_march_2020", displayName: "OBS March 2YO in Training 2020", company: "OBS", month: 3, location: "Ocala, FL", hipRange: [1, 681], recordCount: 677, obsId: null },
  { saleEntity: "OBS March Sale", year: 2021, s3Key: "obs_march_2021", displayName: "OBS March 2YO in Training 2021", company: "OBS", month: 3, location: "Ocala, FL", hipRange: [1, 563], recordCount: 561, obsId: null },
  { saleEntity: "OBS March Sale", year: 2022, s3Key: "obs_march_2022", displayName: "OBS March 2YO in Training 2022", company: "OBS", month: 3, location: "Ocala, FL", hipRange: [1, 635], recordCount: 635, obsId: null },
  { saleEntity: "OBS March Sale", year: 2023, s3Key: "obs_march_2023", displayName: "OBS March 2YO in Training 2023", company: "OBS", month: 3, location: "Ocala, FL", hipRange: [1, 833], recordCount: 833, obsId: null },
  { saleEntity: "OBS March Sale", year: 2024, s3Key: "obs_march_2024", displayName: "OBS March 2YO in Training 2024", company: "OBS", month: 3, location: "Ocala, FL", hipRange: [1, 853], recordCount: 853, obsId: 135 },
  { saleEntity: "OBS March Sale", year: 2025, s3Key: "obs_march_2025", displayName: "OBS March 2YO in Training 2025", company: "OBS", month: 3, location: "Ocala, FL", hipRange: [1, 814], recordCount: 814, obsId: 142 },

  // ── OBS Spring Sales ─────────────────────────────────────────
  { saleEntity: "OBS Spring Sale", year: 2017, s3Key: "obs_spring_2017", displayName: "OBS Spring 2YO in Training 2017", company: "OBS", month: 4, location: "Ocala, FL", hipRange: [1, 1208], recordCount: 1205, obsId: null },
  { saleEntity: "OBS Spring Sale", year: 2018, s3Key: "obs_spring_2018", displayName: "OBS Spring 2YO in Training 2018", company: "OBS", month: 4, location: "Ocala, FL", hipRange: [1, 1222], recordCount: 1220, obsId: null },
  { saleEntity: "OBS Spring Sale", year: 2019, s3Key: "obs_spring_2019", displayName: "OBS Spring 2YO in Training 2019", company: "OBS", month: 4, location: "Ocala, FL", hipRange: [1, 1221], recordCount: 1219, obsId: null },
  { saleEntity: "OBS Spring Sale", year: 2020, s3Key: "obs_spring_2020", displayName: "OBS Spring 2YO in Training 2020", company: "OBS", month: 4, location: "Ocala, FL", hipRange: [1, 1315], recordCount: 1312, obsId: null },
  { saleEntity: "OBS Spring Sale", year: 2021, s3Key: "obs_spring_2021", displayName: "OBS Spring 2YO in Training 2021", company: "OBS", month: 4, location: "Ocala, FL", hipRange: [1, 1217], recordCount: 1214, obsId: null },
  { saleEntity: "OBS Spring Sale", year: 2022, s3Key: "obs_spring_2022", displayName: "OBS Spring 2YO in Training 2022", company: "OBS", month: 4, location: "Ocala, FL", hipRange: [1, 1231], recordCount: 1230, obsId: null },
  { saleEntity: "OBS Spring Sale", year: 2023, s3Key: "obs_spring_2023", displayName: "OBS Spring 2YO in Training 2023", company: "OBS", month: 4, location: "Ocala, FL", hipRange: [1, 1222], recordCount: 1221, obsId: null },
  { saleEntity: "OBS Spring Sale", year: 2024, s3Key: "obs_spring_2024", displayName: "OBS Spring 2YO in Training 2024", company: "OBS", month: 4, location: "Ocala, FL", hipRange: [1, 1208], recordCount: 1208, obsId: 136 },
  { saleEntity: "OBS Spring Sale", year: 2025, s3Key: "obs_spring_2025", displayName: "OBS Spring 2YO in Training 2025", company: "OBS", month: 4, location: "Ocala, FL", hipRange: [1, 1207], recordCount: 1207, obsId: 144 },

  // ── OBS June Sales ───────────────────────────────────────────
  { saleEntity: "OBS June Sale", year: 2017, s3Key: "obs_june_2017", displayName: "OBS June 2YO & HRA 2017", company: "OBS", month: 6, location: "Ocala, FL", hipRange: [1, 769], recordCount: 767, obsId: null },
  { saleEntity: "OBS June Sale", year: 2018, s3Key: "obs_june_2018", displayName: "OBS June 2YO & HRA 2018", company: "OBS", month: 6, location: "Ocala, FL", hipRange: [1, 936], recordCount: 934, obsId: null },
  { saleEntity: "OBS June Sale", year: 2019, s3Key: "obs_june_2019", displayName: "OBS June 2YO & HRA 2019", company: "OBS", month: 6, location: "Ocala, FL", hipRange: [1, 1059], recordCount: 1058, obsId: null },
  { saleEntity: "July 2yo Sale",  year: 2020, s3Key: "obs_june_2020", displayName: "OBS June/July 2YO & HRA 2020", company: "OBS", month: 7, location: "Ocala, FL", hipRange: [1, 1114], recordCount: 1110, obsId: null },
  { saleEntity: "OBS June Sale", year: 2021, s3Key: "obs_june_2021", displayName: "OBS June 2YO & HRA 2021", company: "OBS", month: 6, location: "Ocala, FL", hipRange: [1, 927], recordCount: 926, obsId: null },
  { saleEntity: "OBS June Sale", year: 2022, s3Key: "obs_june_2022", displayName: "OBS June 2YO & HRA 2022", company: "OBS", month: 6, location: "Ocala, FL", hipRange: [1, 1167], recordCount: 1130, obsId: null },
  { saleEntity: "OBS June Sale", year: 2023, s3Key: "obs_june_2023", displayName: "OBS June 2YO & HRA 2023", company: "OBS", month: 6, location: "Ocala, FL", hipRange: [1, 1088], recordCount: 1186, obsId: null },
  { saleEntity: "OBS June Sale", year: 2024, s3Key: "obs_june_2024", displayName: "OBS June 2YO & HRA 2024", company: "OBS", month: 6, location: "Ocala, FL", hipRange: [1, 1115], recordCount: 1042, obsId: 137 },
  { saleEntity: "OBS June Sale", year: 2025, s3Key: "obs_june_2025", displayName: "OBS June 2YO & HRA 2025", company: "OBS", month: 6, location: "Ocala, FL", hipRange: [1, 903], recordCount: 856, obsId: 145 },

  // ── Fasig-Tipton Midlantic Sales ─────────────────────────────
  { saleEntity: "Fasig Tipton Midlantic Sale", year: 2015, s3Key: "ft_midlantic_2015", displayName: "Fasig-Tipton Midlantic 2YO 2015", company: "Fasig-Tipton", month: 5, location: "Timonium, MD", hipRange: [1, 490], recordCount: 485, obsId: null },
  { saleEntity: "Fasig Tipton Midlantic Sale", year: 2016, s3Key: "ft_midlantic_2016", displayName: "Fasig-Tipton Midlantic 2YO 2016", company: "Fasig-Tipton", month: 5, location: "Timonium, MD", hipRange: [1, 598], recordCount: 588, obsId: null },
  { saleEntity: "Fasig Tipton Midlantic Sale", year: 2017, s3Key: "ft_midlantic_2017", displayName: "Fasig-Tipton Midlantic 2YO 2017", company: "Fasig-Tipton", month: 5, location: "Timonium, MD", hipRange: [1, 575], recordCount: 572, obsId: null },
  { saleEntity: "Fasig Tipton Midlantic Sale", year: 2018, s3Key: "ft_midlantic_2018", displayName: "Fasig-Tipton Midlantic 2YO 2018", company: "Fasig-Tipton", month: 5, location: "Timonium, MD", hipRange: [1, 600], recordCount: 597, obsId: null },
  { saleEntity: "Fasig Tipton Midlantic Sale", year: 2019, s3Key: "ft_midlantic_2019", displayName: "Fasig-Tipton Midlantic 2YO 2019", company: "Fasig-Tipton", month: 5, location: "Timonium, MD", hipRange: [1, 600], recordCount: 596, obsId: null },
  { saleEntity: "Fasig Tipton Midlantic Sale", year: 2020, s3Key: "ft_midlantic_2020", displayName: "Fasig-Tipton Midlantic 2YO 2020", company: "Fasig-Tipton", month: 5, location: "Timonium, MD", hipRange: [1, 563], recordCount: 559, obsId: null },
  { saleEntity: "Fasig Tipton Midlantic Sale", year: 2021, s3Key: "ft_midlantic_2021", displayName: "Fasig-Tipton Midlantic 2YO 2021", company: "Fasig-Tipton", month: 5, location: "Timonium, MD", hipRange: [1, 587], recordCount: 584, obsId: null },
  { saleEntity: "Fasig Tipton Midlantic Sale", year: 2022, s3Key: "ft_midlantic_2022", displayName: "Fasig-Tipton Midlantic 2YO 2022", company: "Fasig-Tipton", month: 5, location: "Timonium, MD", hipRange: [1, 636], recordCount: 636, obsId: null },
  { saleEntity: "Fasig Tipton Midlantic Sale", year: 2023, s3Key: "ft_midlantic_2023", displayName: "Fasig-Tipton Midlantic 2YO 2023", company: "Fasig-Tipton", month: 5, location: "Timonium, MD", hipRange: [1, 603], recordCount: 598, obsId: null },
  { saleEntity: "Fasig Tipton Midlantic Sale", year: 2024, s3Key: "ft_midlantic_2024", displayName: "Fasig-Tipton Midlantic 2YO 2024", company: "Fasig-Tipton", month: 5, location: "Timonium, MD", hipRange: [1, 585], recordCount: 580, obsId: null },
  { saleEntity: "Fasig Tipton Midlantic Sale", year: 2025, s3Key: "ft_midlantic_2025", displayName: "Fasig-Tipton Midlantic 2YO 2025", company: "Fasig-Tipton", month: 5, location: "Timonium, MD", hipRange: [1, 586], recordCount: 583, obsId: null },

  // ── Fasig-Tipton Midlantic June Sales ────────────────────────
  { saleEntity: "Fasig Tipton Midlantic June Sale", year: 2023, s3Key: "ft_midlantic_june_2023", displayName: "Fasig-Tipton Midlantic June 2YO 2023", company: "Fasig-Tipton", month: 6, location: "Timonium, MD", hipRange: [1, 99], recordCount: 99, obsId: null },
  { saleEntity: "Fasig Tipton Midlantic June Sale", year: 2024, s3Key: "ft_midlantic_june_2024", displayName: "Fasig-Tipton Midlantic June 2YO 2024", company: "Fasig-Tipton", month: 6, location: "Timonium, MD", hipRange: [1, 80], recordCount: 79, obsId: null },

  // ── Fasig-Tipton Gulfstream Sales ────────────────────────────
  { saleEntity: "Gulfstream Sale", year: 2018, s3Key: "ft_gulfstream_2018", displayName: "Fasig-Tipton Gulfstream 2018", company: "Fasig-Tipton", month: 3, location: "Gulfstream Park, FL", hipRange: [1, 166], recordCount: 162, obsId: null },
  { saleEntity: "Gulfstream Sale", year: 2019, s3Key: "ft_gulfstream_2019", displayName: "Fasig-Tipton Gulfstream 2019", company: "Fasig-Tipton", month: 3, location: "Gulfstream Park, FL", hipRange: [1, 188], recordCount: 186, obsId: null },
  { saleEntity: "Gulfstream Sale", year: 2020, s3Key: "ft_gulfstream_2020", displayName: "Fasig-Tipton Gulfstream 2020", company: "Fasig-Tipton", month: 3, location: "Gulfstream Park, FL", hipRange: [1, 182], recordCount: 179, obsId: null },
  { saleEntity: "Gulfstream Sale", year: 2021, s3Key: "ft_gulfstream_2021", displayName: "Fasig-Tipton Gulfstream 2021", company: "Fasig-Tipton", month: 3, location: "Gulfstream Park, FL", hipRange: [1, 186], recordCount: 182, obsId: null },
  { saleEntity: "Gulfstream Sale", year: 2022, s3Key: "ft_gulfstream_2022", displayName: "Fasig-Tipton Gulfstream 2022", company: "Fasig-Tipton", month: 3, location: "Gulfstream Park, FL", hipRange: [2, 103], recordCount: 100, obsId: null },

  // ── Fasig-Tipton Santa Anita Sales ───────────────────────────
  { saleEntity: "Santa Anita 2yo Sale", year: 2019, s3Key: "ft_santaanita_2019", displayName: "Fasig-Tipton Santa Anita 2YO 2019", company: "Fasig-Tipton", month: 6, location: "Santa Anita, CA", hipRange: [1, 169], recordCount: 168, obsId: null },
  { saleEntity: "Santa Anita 2yo Sale", year: 2021, s3Key: "ft_santaanita_2021", displayName: "Fasig-Tipton Santa Anita 2YO 2021", company: "Fasig-Tipton", month: 6, location: "Santa Anita, CA", hipRange: [1, 115], recordCount: 112, obsId: null },

  // ── Texas 2YO Sale ───────────────────────────────────────────
  { saleEntity: "Texas 2yo Sale", year: 2015, s3Key: "texas_2yo_2015", displayName: "Texas 2YO in Training 2015", company: "Texas", month: 3, location: "Lone Star Park, TX", hipRange: [1, 123], recordCount: 122, obsId: null },

  // ── OBS 2026 (Live / Upcoming) ───────────────────────────────
  { saleEntity: null, year: 2026, s3Key: "obs_march_2026", displayName: "OBS March 2YO in Training 2026", company: "OBS", month: 3, location: "Ocala, FL", hipRange: null, recordCount: null, obsId: 149 },
  { saleEntity: null, year: 2026, s3Key: "obs_spring_2026", displayName: "OBS Spring 2YO in Training 2026", company: "OBS", month: 4, location: "Ocala, FL", hipRange: [1, 1224], recordCount: 1224, obsId: 150 },
  { saleEntity: null, year: 2026, s3Key: "obs_june_2026", displayName: "OBS June 2YO & HRA 2026", company: "OBS", month: 6, location: "Ocala, FL", hipRange: null, recordCount: null, obsId: null },
];

/**
 * Index by s3Key for O(1) lookup.
 */
export const SALE_MAP_BY_S3KEY = Object.fromEntries(
  SALE_ASSET_MAP.map((entry) => [entry.s3Key, entry])
);

/**
 * Index by (saleEntity, year) for mapping historic data → S3 key.
 */
export const SALE_MAP_BY_ENTITY = Object.fromEntries(
  SALE_ASSET_MAP
    .filter((e) => e.saleEntity)
    .map((entry) => [`${entry.saleEntity}|${entry.year}`, entry])
);

/**
 * Look up the S3 key for a given historic sale entity and year.
 *
 * @param {string} saleEntity - The "sale" field from vendor-data.json (e.g. "OBS March Sale")
 * @param {number} year - The sale year
 * @returns {string|null} The S3 key (e.g. "obs_march_2023") or null if not found
 */
export function lookupS3Key(saleEntity, year) {
  const entry = SALE_MAP_BY_ENTITY[`${saleEntity}|${year}`];
  return entry ? entry.s3Key : null;
}

/**
 * Look up the sale metadata by S3 key.
 *
 * @param {string} s3Key - The S3 key (e.g. "obs_march_2023")
 * @returns {object|null} The mapping entry or null
 */
export function lookupByS3Key(s3Key) {
  return SALE_MAP_BY_S3KEY[s3Key] || null;
}

/**
 * Get all sale entries for a given company.
 *
 * @param {string} company - "OBS", "Fasig-Tipton", or "Texas"
 * @returns {object[]} Array of matching entries
 */
export function getSalesByCompany(company) {
  return SALE_ASSET_MAP.filter((e) => e.company === company);
}

/**
 * Get all sale entries for a given year.
 *
 * @param {number} year
 * @returns {object[]} Array of matching entries
 */
export function getSalesByYear(year) {
  return SALE_ASSET_MAP.filter((e) => e.year === year);
}

/**
 * Mapping from historic SaleEntity names to the S3 key prefix pattern.
 * This describes the convention used for all years.
 */
export const ENTITY_TO_S3_PREFIX = {
  "OBS March Sale": "obs_march",
  "OBS Spring Sale": "obs_spring",
  "OBS June Sale": "obs_june",
  "July 2yo Sale": "obs_june",  // 2020 COVID-delayed June sale
  "Fasig Tipton Midlantic Sale": "ft_midlantic",
  "Fasig Tipton Midlantic June Sale": "ft_midlantic_june",
  "Gulfstream Sale": "ft_gulfstream",
  "Santa Anita 2yo Sale": "ft_santaanita",
  "Texas 2yo Sale": "texas_2yo",
};
