# Breeze Up Sales Analytics Platform

## Project Overview

Ingest, store, and analyse data from US 2-year-old breeze-up (under tack) sales — linking sale-day assets (videos, images, pedigree, consignor info, breeze times) to downstream racing performance outcomes.

---

## Target Sales (2YO only)

### OBS (Ocala Breeders' Sales)
| Sale | Typical Schedule | Approx Hips |
|------|-----------------|-------------|
| March 2YO in Training | March | ~850 |
| Spring 2YO in Training | April | ~1,200 |
| June 2YO & HRA | June | ~1,000 |

### Fasig-Tipton
| Sale | Typical Schedule | Approx Hips |
|------|-----------------|-------------|
| Gulfstream (Selected 2YO) | March/April | ~200 |
| Midlantic May 2YO | May | ~550 |

**Total annual throughput: ~3,800 lots across 5 sales**

---

## Site Architecture Research

### OBS (obssales.com / obscatalog.com)

**Catalog System:** Single-page app at `obssales.com/catalog/#/{sale_id}/results` — JavaScript-rendered, requires headless browser to scrape the SPA.

**Key data per hip:**
- Pedigree (sire, dam, dam sire, breeder, colour, sex)
- Consignor name
- Under tack time + distance (1/8 or 1/4 mile)
- Sale result (price, buyer, RNA status)
- Conformation photo
- Walking video
- Under tack (breeze) video

**Video URL pattern (legacy/direct):**
```
https://obscatalog.com/{sale_code}/{year}/{hip_number}.mp4
```
Sale codes: `mar`, `apr`, `jun` (under tack videos)

**Video player:**
```
https://www.obscatalog.com/vp/?slide=/marresults/{year}/&startAt=https://obscatalog.com/mar/{year}/{hip}.mp4
```

**Supplementary data:**
- Under tack schedule PDFs at `obscatalog.com/OBSPAGES/`
- Excel-format results available for some sales
- Pedigree PDFs available via catalog

**New catalog system (2024+):** Uses sale IDs (e.g., `142` = 2025 March, `144` = 2025 Spring, `145` = 2025 June). The SPA likely fetches data from an internal API — needs headless browser inspection to discover JSON endpoints.

### Fasig-Tipton (fasigtipton.com)

**Catalog System:** Server-rendered pages at `fasigtipton.com/{year}/{sale-slug}` with tabs for Catalogue, Under Tack Show, Results, Sale Info.

**Key data per hip:**
- Full pedigree page (typically PDF or rendered HTML)
- Consignor
- Under tack time + distance
- Sale result (price, buyer, RNA)
- Under tack video (linked from hip page)
- Walking video
- Conformation photos

**URL patterns:**
```
Catalogue: fasigtipton.com/{year}/{sale-slug}  (tab: Catalogue)
Results:   fasigtipton.com/{year}/{sale-slug}  (tab: Results)
Hip page:  fasigtipton.com/2025/Midlantic-2YO-Sale#hip-{number}
```

**Sale slugs (2YO only):**
- `The-Gulfstream-Sale` (when held)
- `Midlantic-2YO-Sale` or `Midlantic-May-2YO-Sale`

---

## Performance Outcome Data Sources

| Source | Data Available | Access Method |
|--------|---------------|---------------|
| **Equibase** | Official charts, results, speed figures, earnings, graded stakes | Web scraping (no public API; restrictive ToS) |
| **DRF / Formulator** | Past performances, speed figures | Paid subscription |
| **Bloodhorse / Stallion Register** | Graded graduates, stakes records | Web scraping |
| **Arion Pedigrees** (AU/NZ proxy) | Already have scraper — adapt pattern for US data | API/scraping |
| **The Jockey Club** | Foal registration, name lookup, pedigree verification | Limited web access |
| **Racing Post** (for any exported horses) | International form | Web scraping |

**Recommended approach:** Build a lightweight Equibase scraper for horse profiles (results, earnings, best race class) keyed by horse name + year of birth. Supplement with manual graded stakes tracking from Bloodhorse/TDN graded graduates lists.

**Ability level classification system:**
| Level | Definition |
|-------|-----------|
| G1 | Won or placed in a Grade 1 |
| Graded | Won or placed in any graded stakes |
| Stakes | Won or placed in a stakes race |
| Winner | Won at least one race |
| Placed | Placed (2nd/3rd) but never won |
| Unplaced | Raced but never placed |
| Unraced | Never raced |

---

## Data Model

```
sale
├── sale_id (e.g., "obs_march_2025")
├── company ("OBS" | "Fasig-Tipton")
├── sale_name
├── year
├── dates
└── location

lot
├── lot_id (sale_id + hip_number)
├── hip_number
├── sale_id (FK)
├── horse_name (if named at sale)
├── sex
├── colour
├── year_of_birth
├── sire
├── dam
├── dam_sire
├── breeder
├── consignor
├── state_bred (if applicable)
├── under_tack_distance ("1/8" | "1/4")
├── under_tack_time (seconds, e.g., 10.1)
├── under_tack_date
├── sale_price (USD, null if RNA/out/withdrawn)
├── sale_status ("sold" | "RNA" | "out" | "withdrawn")
├── buyer
└── created_at / updated_at

asset
├── asset_id
├── lot_id (FK)
├── asset_type ("breeze_video" | "walk_video" | "photo" | "pedigree_page")
├── source_url
├── local_path
├── file_size
├── downloaded_at
└── checksum (md5)

performance
├── performance_id
├── lot_id (FK)
├── horse_name (as raced)
├── country
├── starts
├── wins
├── places
├── earnings (USD)
├── best_class ("G1" | "Graded" | "Stakes" | "Winner" | ... )
├── best_race_name
├── best_equibase_speed_figure
├── last_updated
└── notes
```

---

## Agent Architecture

Six concurrent agents, each independently deployable, coordinated via a shared task queue and database.

### Agent 1: Catalog Discovery Agent
**Purpose:** Discover available sales and enumerate all hips.

**Workflow:**
1. Monitor OBS and Fasig-Tipton sales calendar pages
2. Detect new 2YO sales (filter out yearling, mixed, HRA-only sales)
3. For each sale, enumerate all hip numbers
4. Create `sale` and `lot` skeleton records in the database
5. Queue tasks for Agents 2-4

**Tech:** Playwright (headless browser for OBS SPA), requests + BeautifulSoup for Fasig-Tipton. Scheduled cron job (daily during sale season, weekly otherwise).

---

### Agent 2: Pedigree & Sale Data Agent
**Purpose:** Scrape structured data for each lot.

**Workflow:**
1. Pull lot tasks from queue
2. Navigate to hip page (headless browser for OBS, HTTP for F-T)
3. Extract: sire, dam, dam sire, breeder, consignor, sex, colour, state-bred
4. Extract under tack time and distance
5. Extract sale result (price, buyer, RNA status)
6. Update `lot` record in database
7. Save pedigree page as PDF asset

**Tech:** Playwright for OBS, requests/BS4 for Fasig-Tipton. Rate-limited (2-3 sec between requests). Retry logic with exponential backoff.

**Concurrency:** 2-3 parallel workers per sale company, processing different hip ranges.

---

### Agent 3: Video & Media Agent
**Purpose:** Download all video and image assets.

**Workflow:**
1. Pull lot tasks from queue (after Agent 2 has populated URLs)
2. Attempt direct download via known URL patterns:
   - OBS: `https://obscatalog.com/{sale_code}/{year}/{hip}.mp4`
   - Fasig-Tipton: Extract video URLs from hip page
3. Download breeze video, walking video, conformation photos
4. Verify file integrity (minimum file size, video duration check)
5. Create `asset` records with checksums
6. Store locally with structured path: `data/{sale_id}/videos/{hip}_{type}.mp4`

**Tech:** `yt-dlp` or direct HTTP downloads. `ffprobe` for video validation. Parallel downloads (5-10 concurrent, bandwidth-aware).

**Storage estimate:** ~50-100MB per video × 3,800 lots × 2 videos = **~400-750 GB/year**

---

### Agent 4: Performance Tracking Agent
**Purpose:** Link sale graduates to racing outcomes.

**Workflow:**
1. For each lot with status "sold", resolve horse's racing name
   - May differ from catalog name
   - Cross-reference via sire + dam + year of birth on Equibase
2. Periodically scrape racing results (monthly for 1st year, quarterly after)
3. Classify ability level achieved
4. Update `performance` record

**Tech:** Equibase profile scraper (Playwright), name-matching heuristics. Scheduled: weekly during first racing season, monthly thereafter.

**Key challenge:** Name resolution — many 2YOs are unnamed at sale time. Use pedigree matching (sire × dam × YOB) as the primary key.

---

### Agent 5: Data Quality & Reconciliation Agent
**Purpose:** Ensure data completeness and correctness.

**Workflow:**
1. Scan for lots missing data (no video, no price, no pedigree)
2. Cross-reference sale totals against published summaries
3. Flag anomalies (unusually fast/slow times, missing videos)
4. Retry failed downloads
5. Generate data completeness reports

**Tech:** SQL queries against database, automated reporting. Runs daily.

---

### Agent 6: Export & Analytics Agent
**Purpose:** Generate analysis-ready datasets and reports.

**Workflow:**
1. Export combined CSV/Parquet files linking sale data → performance
2. Generate summary statistics (by sire, consignor, price range, breeze time)
3. Build ROI calculations (price paid vs earnings)
4. Produce visualisations for the analytics frontend
5. Feed data into the existing Ultra Analytics platform

**Tech:** pandas, polars for data processing. Scheduled after performance updates.

---

## Technology Stack

```
Language:       Python 3.12+
Scraping:       Playwright (headless Chromium), requests, BeautifulSoup4
Task Queue:     Redis + RQ (or Celery for more complex orchestration)
Database:       PostgreSQL (structured data) + S3/local filesystem (assets)
Video Tools:    yt-dlp, ffmpeg, ffprobe
Data Export:    pandas, polars, pyarrow
Scheduling:     APScheduler or cron
CI/CD:          GitHub Actions (daily scrape runs)
Monitoring:     Simple logging + Slack/Discord notifications
```

---

## GitHub Repository Structure

```
breeze-up-analytics/
├── README.md
├── pyproject.toml
├── .github/
│   └── workflows/
│       ├── daily_scrape.yml        # Catalog + data scraping
│       ├── weekly_performance.yml  # Performance tracking
│       └── monthly_export.yml      # Data export + analytics
├── src/
│   ├── __init__.py
│   ├── config.py                   # Sale definitions, URL patterns
│   ├── models.py                   # SQLAlchemy/Pydantic models
│   ├── db.py                       # Database connection + migrations
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── catalog_discovery.py    # Agent 1
│   │   ├── pedigree_scraper.py     # Agent 2
│   │   ├── media_downloader.py     # Agent 3
│   │   ├── performance_tracker.py  # Agent 4
│   │   ├── data_quality.py         # Agent 5
│   │   └── export_analytics.py     # Agent 6
│   ├── scrapers/
│   │   ├── __init__.py
│   │   ├── obs/
│   │   │   ├── catalog.py          # OBS SPA navigation
│   │   │   ├── video.py            # OBS video URL resolution
│   │   │   └── parser.py           # OBS data extraction
│   │   ├── fasig_tipton/
│   │   │   ├── catalog.py          # F-T page scraping
│   │   │   ├── video.py            # F-T video URL extraction
│   │   │   └── parser.py           # F-T data extraction
│   │   └── equibase/
│   │       ├── profile.py          # Horse profile scraping
│   │       └── name_resolver.py    # Pedigree-based name matching
│   └── utils/
│       ├── rate_limiter.py
│       ├── video_validator.py
│       └── notifications.py
├── data/
│   ├── sales/                      # Sale metadata (JSON configs)
│   └── exports/                    # Generated CSVs/Parquet files
├── tests/
│   ├── test_obs_parser.py
│   ├── test_ft_parser.py
│   └── test_name_resolver.py
├── scripts/
│   ├── init_db.py
│   ├── backfill_sale.py            # One-off: scrape a past sale
│   └── export_dataset.py
└── docker-compose.yml              # Postgres + Redis
```

---

## Implementation Priority

### Phase 1: Foundation (Week 1-2)
- [ ] Init GitHub repo with structure above
- [ ] Set up PostgreSQL schema + migrations
- [ ] Build OBS catalog scraper (Agent 1 + Agent 2 for OBS)
- [ ] Test with 2025 OBS March sale (single sale, ~850 hips)

### Phase 2: Video Ingestion (Week 3)
- [ ] Build OBS video downloader (Agent 3)
- [ ] Discover and document video URL patterns for new OBS catalog system
- [ ] Download breeze videos for test sale
- [ ] Validate video files

### Phase 3: Fasig-Tipton (Week 4)
- [ ] Build Fasig-Tipton scrapers (Agents 1-3 for F-T)
- [ ] Test with 2025 Midlantic May sale
- [ ] Unify data model across both companies

### Phase 4: Performance Linking (Week 5-6)
- [ ] Build Equibase profile scraper
- [ ] Implement name resolution (pedigree matching)
- [ ] Backfill performance data for 2024 sales
- [ ] Classify ability levels

### Phase 5: Analytics & Export (Week 7-8)
- [ ] Build export pipeline
- [ ] Generate ROI analysis
- [ ] Connect to Ultra Analytics frontend
- [ ] Set up scheduled GitHub Actions

---

## Key Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| OBS SPA changes structure | Breaks catalog scraper | Version-pin selectors, add integration tests, monitor for failures |
| Video URLs change pattern | Can't download breeze videos | Headless browser fallback to extract URLs from player page |
| Equibase blocks scraping | No performance data | Rate limit aggressively; fall back to manual graded stakes data from TDN/Bloodhorse |
| Name resolution failures | Can't link sale → race record | Use pedigree matching (sire × dam × YOB) as primary; manual review queue for ambiguous cases |
| Storage costs for video | Budget overrun | Compress with ffmpeg (H.265), consider cloud storage tiering |
| Rate limiting / IP blocking | Scraping interruption | Rotating delays, respectful crawling, headless browser fingerprint management |

---

## Notes

- **Respect robots.txt and ToS:** Both OBS and Fasig-Tipton publish sale data publicly for buyer information — scraping for analytical purposes should be done respectfully with appropriate rate limiting.
- **Equibase explicitly prohibits scraping** in their ToS — consider whether Equibase data is essential or if alternatives (manual graded stakes tracking, DRF data subscription) are sufficient.
- **Video storage** is the biggest infrastructure cost — plan for S3 or similar object storage with lifecycle policies.
- **This project pairs naturally with your existing computer vision work** — breeze videos can feed directly into gallop motion tracking models for biomechanical analysis.
