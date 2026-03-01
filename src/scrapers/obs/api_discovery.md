# OBS Catalog API Discovery

**Discovered: 2026-03-01**
**Source:** WordPress REST API at `obssales.com/wp-json/obs-catalog-wp-plugin/v1/`

## Key Finding

The OBS catalog SPA (`obssales.com/catalog/#/{sale_id}`) is an Angular app that fetches
**all sale data in a single JSON API call**. No headless browser (Playwright) is needed
for data extraction — a simple HTTP GET to the REST endpoint returns complete structured
JSON including every hip with pedigree, results, under tack times, and media URLs.

## API Endpoints

### Public (no auth required)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/horse-sales/{sale_id}` | GET | **Primary endpoint.** Returns complete sale data including all hips, metadata, and settings. ~1.7MB per sale. |
| `/horse-upcoming-sales` | GET | Returns array of upcoming/current sales with full sale metadata. |
| `/pdf-proxy?url={url}` | GET | Proxies PDF downloads (pedigree pages, Equineline PPs). |

### Restricted (401 without auth)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/horse-sales` | GET | List all sales (requires auth). |
| `/horse-previous-sales` | GET | List past sales (requires auth). |
| `/horse-sale-last-jc-update/{sale_id}` | GET | Jockey Club data update timestamp. |

### Admin-only (POST/PUT)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/equineline-download` | POST | Download Equineline data. |
| `/equineline-upload` | POST | Upload Equineline data. |
| `/horse-sales-media-files` | POST | Manage media files. |
| `/sale-meta` | POST | Update sale metadata. |
| `/sale-settings` | GET/POST/DELETE | Manage sale display settings. |
| `/seller-description` | PUT | Update seller descriptions. |
| `/jockey-club` | GET/PUT | Jockey Club integration. |
| `/roberts-stream` | PUT | Roberts stream integration. |

## Sale Object Structure

```json
{
  "sale_id": "142",
  "sale_code": "O625",
  "equineline_sale_id": "10039",
  "sale_name": "2025 March 2YO in Training Sale",
  "sale_short_name": "25 Mar",
  "previous_year_sale_id": "137",
  "is_digital": "0",
  "sale_category": "2yo",
  "sale_starts": "2025-03-11 04:00:00",
  "sale_ends": "2025-03-13 04:00:00",
  "display_to_public_date": "...",
  "results_display_to_public_date": "...",
  "next_sale_id": "...",
  "previous_sale_id": "...",
  "sale_meta": [...],
  "sale_hip": [...],
  "sales_settings": {...},
  "roberts_stream_data": [...]
}
```

## Hip Object Structure (sale_hip array)

```json
{
  "sale_id": "142",
  "in_out_status": "I",
  "horse_type": "2",
  "foaling_year": "2023",
  "hip_number": "2",
  "horse_name": "",
  "color": "B",
  "sex": "C",
  "foaling_date": "02/13/2023",
  "sire_name": "Basin",
  "dam_name": "Callie's Candy",
  "dam_sire": "Declaration of War",
  "property_line_1": "Triple C Sales, Agent",
  "consignor_sort": "Triple C Sales",
  "consignor_name": "Triple C Sales, Agent",
  "foaling_area": "KY",
  "barn_number": "15",
  "session_number": "1",

  // Sale results
  "buyer_name": "RM 18 Stables",
  "hammer_price": "55000.00",
  "rna_summary_indicator": "N",
  "post_sale_indicator": "N",

  // Under tack
  "ut_time": "10.2",
  "ut_expected_date": "03/06/2025",
  "ut_actual_date": "03/06/2025",
  "ut_set": "171",
  "ut_distance": " 1/8",
  "ut_group": "3",

  // Media flags
  "has_photo": "1",
  "has_video": "1",
  "has_walk_video": "1",

  // Media URLs (present when has_* = "1")
  "photo_link": "https://obscatalog.com/{year}/{sale_id}/{hip}p.jpg?v={timestamp}",
  "video_link": "https://obscatalog.com/{year}/{sale_id}/{hip}.mp4?v={timestamp}",
  "walk_video_link": "https://obscatalog.com/{year}/{sale_id}/{hip}w.mp4?v={timestamp}",
  "pedigree_pdf_link": "https://obscatalog.com/{year}/{sale_id}/{hip}.pdf?v={timestamp}",

  // Display state
  "display_props": {
    "is_hip_out": false,
    "is_hip_not_through_ring_yet": false,
    "is_hip_sold": true,
    "is_rna": false,
    "is_bt": false,
    "has_walk_video": true,
    "hammer_price": "$55,000"
  }
}
```

## Known Sale IDs

| sale_id | Sale | Year | Hips |
|---------|------|------|------|
| 142 | March 2YO in Training | 2025 | 814 |
| 144 | Spring 2YO in Training | 2025 | ~1200 |
| 145 | June 2YO & HRA | 2025 | ~1000 |
| 149 | March 2YOs in Training | 2026 | 816 |

New sale IDs can be discovered via `/horse-upcoming-sales` or by following
`next_sale_id` / `previous_sale_id` chains from known sales.

## Media URL Patterns

Pattern: `https://obscatalog.com/{year}/{sale_id}/{hip}{suffix}?v={cache_buster}`

| Suffix | Asset Type |
|--------|-----------|
| `.mp4` | Breeze (under tack) video |
| `w.mp4` | Walking video |
| `p.jpg` | Conformation photo |
| `.pdf` | Pedigree PDF |

## Field Mapping to Our Schema

| API Field | Our Model Field | Notes |
|-----------|----------------|-------|
| `hip_number` | `lot.hip_number` | |
| `horse_name` | `lot.horse_name` | Often empty (unnamed 2YOs) |
| `sex` | `lot.sex` | "C"=Colt, "F"=Filly, "G"=Gelding |
| `color` | `lot.colour` | e.g. "B", "DB/BR", "CH" |
| `foaling_year` | `lot.year_of_birth` | |
| `sire_name` | `lot.sire` | |
| `dam_name` | `lot.dam` | |
| `dam_sire` | `lot.dam_sire` | |
| `property_line_1` | `lot.consignor` | Full consignor line |
| `foaling_area` | `lot.state_bred` | State abbreviation |
| `ut_distance` | `lot.under_tack_distance` | " 1/8" or " 1/4" (note leading space) |
| `ut_time` | `lot.under_tack_time` | Seconds as string e.g. "10.2" |
| `ut_actual_date` | `lot.under_tack_date` | MM/DD/YYYY format |
| `hammer_price` | `lot.sale_price` | String "55000.00", negative = RNA amount |
| `buyer_name` | `lot.buyer` | "RNA" if not sold |
| `display_props.is_hip_sold` | → `sale_status="sold"` | |
| `display_props.is_rna` | → `sale_status="RNA"` | |
| `display_props.is_hip_out` | → `sale_status="out"` | |
| `rna_summary_indicator` | | "Y" = RNA, "N" = sold |

## Important Notes

1. **No Playwright needed** — The REST API returns JSON directly. Only media downloads
   require separate HTTP calls.
2. **RNA encoding** — RNA hips have `hammer_price` as a negative number (the reserve).
3. **Breeder field** — Not directly in the API. May be in the pedigree PDF or a
   separate Equineline data source.
4. **Sale navigation** — Use `previous_sale_id` / `next_sale_id` to crawl sale history.
5. **Rate limiting** — Be respectful; the full sale payload is ~1.7MB, cache locally.
