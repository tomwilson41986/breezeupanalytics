"""Configuration: sale definitions, URL patterns, and environment settings."""

import os

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/breezeup",
)

# For local development / testing without Postgres, fall back to SQLite
SQLITE_URL = "sqlite:///breezeup.db"

# ---------------------------------------------------------------------------
# OBS catalog
# ---------------------------------------------------------------------------
OBS_CATALOG_BASE = "https://obssales.com/catalog/#"
OBS_VIDEO_BASE = "https://obscatalog.com"

# sale_code -> (sale_name, typical_month)
OBS_SALES: dict[str, dict] = {
    "mar": {"name": "March 2YO in Training", "month": 3},
    "apr": {"name": "Spring 2YO in Training", "month": 4},
    "jun": {"name": "June 2YO & HRA", "month": 6},
}

# Known OBS SPA sale IDs (catalog/#/{sale_id})
# These change each year - discovered via catalog inspection
OBS_CATALOG_IDS: dict[str, int] = {
    # 2025
    "obs_march_2025": 142,
    "obs_spring_2025": 144,
    "obs_june_2025": 145,
    # 2026 - will need to be discovered
}

# ---------------------------------------------------------------------------
# Fasig-Tipton catalog
# ---------------------------------------------------------------------------
FT_BASE = "https://fasigtipton.com"

FT_SALES: dict[str, dict] = {
    "gulfstream": {"name": "The Gulfstream Sale", "slug": "The-Gulfstream-Sale"},
    "midlantic": {"name": "Midlantic 2YO Sale", "slug": "Midlantic-2YO-Sale"},
}

# ---------------------------------------------------------------------------
# Video URL templates
# ---------------------------------------------------------------------------
OBS_VIDEO_URL_TEMPLATE = "{base}/{sale_code}/{year}/{hip}.mp4"
OBS_VIDEO_PLAYER_TEMPLATE = (
    "{base}/vp/?slide=/{sale_code}results/{year}/&startAt="
    "{base}/{sale_code}/{year}/{hip}.mp4"
)

# ---------------------------------------------------------------------------
# Scraping behaviour
# ---------------------------------------------------------------------------
REQUEST_DELAY_SECONDS = 2.5  # Polite delay between requests
MAX_RETRIES = 3
RETRY_BACKOFF_FACTOR = 2  # Exponential backoff multiplier
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)
