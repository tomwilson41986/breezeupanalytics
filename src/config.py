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
    # 2024
    "obs_march_2024": 135,
    "obs_spring_2024": 136,
    "obs_june_2024": 137,
    # 2025
    "obs_march_2025": 142,
    "obs_spring_2025": 144,
    "obs_june_2025": 145,
    # 2026
    "obs_march_2026": 149,
}

# OBS legacy results pages (obscatalog.com) for pre-2024 sales.
# Maps (sale_code_prefix, year) -> URL path segment.
OBS_LEGACY_RESULTS: dict[str, dict] = {
    # 2023
    "obs_june_2023": {"url": "https://www.obscatalog.com/junresults/2023/", "sale_code": "jun", "year": 2023},
    "obs_spring_2023": {"url": "https://www.obscatalog.com/aprresults/2023/", "sale_code": "apr", "year": 2023},
    "obs_march_2023": {"url": "https://www.obscatalog.com/marresults/2023/", "sale_code": "mar", "year": 2023},
    # 2022
    "obs_june_2022": {"url": "https://www.obscatalog.com/junresults/2022/", "sale_code": "jun", "year": 2022},
    "obs_spring_2022": {"url": "https://www.obscatalog.com/aprresults/2022/", "sale_code": "apr", "year": 2022},
    "obs_march_2022": {"url": "https://www.obscatalog.com/marresults/2022/", "sale_code": "mar", "year": 2022},
    # 2021
    "obs_june_2021": {"url": "https://www.obscatalog.com/junresults/2021/", "sale_code": "jun", "year": 2021},
    "obs_spring_2021": {"url": "https://www.obscatalog.com/aprresults/2021/", "sale_code": "apr", "year": 2021},
    "obs_march_2021": {"url": "https://www.obscatalog.com/marresults/2021/", "sale_code": "mar", "year": 2021},
    # 2020
    "obs_june_2020": {"url": "https://www.obscatalog.com/julresults/2020/", "sale_code": "jul", "year": 2020},
    "obs_spring_2020": {"url": "https://www.obscatalog.com/aprresults/2020/", "sale_code": "apr", "year": 2020},
    "obs_march_2020": {"url": "https://www.obscatalog.com/marresults/2020/", "sale_code": "mar", "year": 2020},
    # 2019
    "obs_june_2019": {"url": "https://www.obscatalog.com/junresults/2019/", "sale_code": "jun", "year": 2019},
    "obs_spring_2019": {"url": "https://www.obscatalog.com/aprresults/2019/", "sale_code": "apr", "year": 2019},
    "obs_march_2019": {"url": "https://www.obscatalog.com/marresults/2019/", "sale_code": "mar", "year": 2019},
    # 2018
    "obs_june_2018": {"url": "https://www.obscatalog.com/junresults/2018/", "sale_code": "jun", "year": 2018},
    "obs_spring_2018": {"url": "https://www.obscatalog.com/aprresults/2018/", "sale_code": "apr", "year": 2018},
    "obs_march_2018": {"url": "https://www.obscatalog.com/marresults/2018/", "sale_code": "mar", "year": 2018},
}

# ---------------------------------------------------------------------------
# Fasig-Tipton catalog
# ---------------------------------------------------------------------------
FT_BASE = "https://fasigtipton.com"
FT_API_BASE = "https://www.fasigtipton.com/django/api"

FT_SALES: dict[str, dict] = {
    "gulfstream": {"name": "The Gulfstream Sale", "slug": "The-Gulfstream-Sale"},
    "midlantic": {"name": "Midlantic 2YO Sale", "slug": "Midlantic-2YO-Sale"},
}

# Fasig-Tipton sale identifiers and their S3 keys.
# sale_key -> {sale_identifier, api_id, year, source_url, display_name, location}
FT_CATALOG_IDS: dict[str, dict] = {
    # 2025
    "ft_midlantic_2025": {
        "sale_identifier": "M25A",
        "api_id": 274,
        "year": 2025,
        "source_url": "https://www.fasigtipton.com/2025/Midlantic-2YO-Sale",
        "display_name": "Fasig-Tipton Midlantic May 2YO 2025",
        "location": "Timonium, MD",
    },
    # 2024
    "ft_midlantic_june_2024": {
        "sale_identifier": "M24J",
        "api_id": 254,
        "year": 2024,
        "source_url": "https://www.fasigtipton.com/2024/Midlantic-June-2YO-Sale",
        "display_name": "Fasig-Tipton Midlantic June 2YO 2024",
        "location": "Timonium, MD",
    },
    # 2023
    "ft_midlantic_june_2023": {
        "sale_identifier": "M23J",
        "api_id": 219,
        "year": 2023,
        "source_url": "https://www.fasigtipton.com/2023/Midlantic-June-2YO-Sale",
        "display_name": "Fasig-Tipton Midlantic June 2YO 2023",
        "location": "Timonium, MD",
    },
    # 2022
    "ft_midlantic_2022": {
        "sale_identifier": "M22A",
        "api_id": 198,
        "year": 2022,
        "source_url": "https://www.fasigtipton.com/index.php/2022/Midlantic-Two-Year-Olds-in-Training",
        "display_name": "Fasig-Tipton Midlantic 2YO 2022",
        "location": "Timonium, MD",
    },
    # 2021
    "ft_santaanita_2021": {
        "sale_identifier": "C21A",
        "api_id": 182,
        "year": 2021,
        "source_url": "https://www.fasigtipton.com/2021/Santa-Anita-Two-Year-Olds-in-Training",
        "display_name": "Fasig-Tipton Santa Anita 2YO 2021",
        "location": "Santa Anita, CA",
    },
    "ft_midlantic_2021": {
        "sale_identifier": "M21A",
        "api_id": 181,
        "year": 2021,
        "source_url": "https://www.fasigtipton.com/2021/Midlantic-Two-Year-Olds-in-Training",
        "display_name": "Fasig-Tipton Midlantic 2YO 2021",
        "location": "Timonium, MD",
    },
    # 2020
    "ft_midlantic_2020": {
        "sale_identifier": "M20A",
        "api_id": 170,
        "year": 2020,
        "source_url": "https://www.fasigtipton.com/2020/Midlantic-Two-Year-Olds-in-Training",
        "display_name": "Fasig-Tipton Midlantic 2YO 2020",
        "location": "Timonium, MD",
    },
    # 2019
    "ft_santaanita_2019": {
        "sale_identifier": "C19A",
        "api_id": 156,
        "year": 2019,
        "source_url": "https://www.fasigtipton.com/2019/Santa-Anita-Two-Year-Olds-in-Training",
        "display_name": "Fasig-Tipton Santa Anita 2YO 2019",
        "location": "Santa Anita, CA",
    },
    "ft_midlantic_2019": {
        "sale_identifier": "M19A",
        "api_id": 155,
        "year": 2019,
        "source_url": "https://www.fasigtipton.com/2019/Midlantic-Two-Year-Olds-in-Training",
        "display_name": "Fasig-Tipton Midlantic 2YO 2019",
        "location": "Timonium, MD",
    },
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
# S3 storage
# ---------------------------------------------------------------------------
S3_BUCKET_NAME = os.environ.get("S3_BUCKET_NAME", "")
S3_REGION = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
S3_KEYPOINT_PREFIX = "keypoint"  # Default prefix for pipeline output

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
