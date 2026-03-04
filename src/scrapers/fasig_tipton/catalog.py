"""Fasig-Tipton catalog scraper using the Django REST API.

Discovery (2026-03-04): The Fasig-Tipton catalog SPA at fasigtipton.com/{year}/{slug}
is a React/Redux app backed by a Django REST API at:

    https://www.fasigtipton.com/django/api

Key endpoints:
    GET /sales/?sale_identifier={id}  → sale metadata (returns list)
    GET /horses/?sale={api_id}        → all horses for a sale

No headless browser required — the API returns JSON directly.
"""

import logging
import time
from dataclasses import dataclass, field
from decimal import Decimal

import requests

from src.config import REQUEST_DELAY_SECONDS, MAX_RETRIES, RETRY_BACKOFF_FACTOR, USER_AGENT

logger = logging.getLogger(__name__)

API_BASE = "https://www.fasigtipton.com/django/api"


@dataclass
class FTHip:
    """Parsed hip record from the Fasig-Tipton API."""

    sale_id: str
    hip_number: int
    horse_name: str | None
    sex: str | None
    colour: str | None
    year_of_birth: int | None
    foaling_date: str | None
    sire: str | None
    dam: str | None
    dam_sire: str | None
    consignor: str | None
    consignor_name: str | None
    state_bred: str | None
    barn_number: str | None
    session_date: str | None

    # Under tack
    under_tack_time: Decimal | None
    under_tack_surface: str | None
    under_tack_date: str | None

    # Sale result
    sale_price: int | None
    sale_status: str  # "sold" | "RNA" | "out" | "withdrawn" | "pending"
    buyer: str | None
    hammer_price_raw: str | None

    # Media URLs
    photo_url: str | None = None
    video_url: str | None = None
    walk_video_url: str | None = None
    video_thumbnail: str | None = None

    # Flags
    has_photo: bool = False
    has_video: bool = False


@dataclass
class FTSale:
    """Parsed sale record from the Fasig-Tipton API."""

    sale_id: str
    sale_identifier: str
    api_id: int
    sale_name: str
    year: int
    start_date: str | None
    under_tack_start_date: str | None
    max_hip: int
    hips: list[FTHip] = field(default_factory=list)
    raw_sale: dict = field(default_factory=dict)


def _get_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    return session


def _request_with_retry(session: requests.Session, url: str, params: dict | None = None) -> dict | list:
    """GET with exponential backoff retry."""
    for attempt in range(MAX_RETRIES + 1):
        try:
            resp = session.get(url, params=params, timeout=30)
            resp.raise_for_status()
            return resp.json()
        except (requests.RequestException, ValueError) as e:
            if attempt == MAX_RETRIES:
                raise
            wait = REQUEST_DELAY_SECONDS * (RETRY_BACKOFF_FACTOR ** attempt)
            logger.warning("Request failed (attempt %d/%d): %s. Retrying in %.1fs",
                           attempt + 1, MAX_RETRIES, e, wait)
            time.sleep(wait)
    raise RuntimeError("unreachable")


def _parse_sale_status(horse: dict) -> str:
    """Determine sale status from API fields."""
    if horse.get("out"):
        return "out"

    purchaser = (horse.get("purchaser") or "").strip().upper()
    price_str = horse.get("price") or "0.00"

    if purchaser in ("OUT", "WITHDRAWN", ""):
        return "out"
    if purchaser == "NOT SOLD" or "NOT SOLD" in purchaser:
        return "RNA"

    try:
        price = float(price_str)
    except (ValueError, TypeError):
        price = 0.0

    if price > 0 and purchaser and purchaser != "NOT SOLD":
        return "sold"
    if price > 0:
        return "RNA"
    return "pending"


def _parse_sale_price(horse: dict) -> int | None:
    """Extract sale price in whole dollars. Returns None for RNA/out/pending."""
    status = _parse_sale_status(horse)
    raw = horse.get("price")
    if raw is None:
        return None
    try:
        price = float(raw)
    except (ValueError, TypeError):
        return None
    if price <= 0:
        return None
    if status == "sold":
        return int(price)
    return None


def _parse_year_of_birth(raw: str | None) -> int | None:
    """Extract year from date string like '05/13/2022' or '2022-05-13'."""
    if not raw or not raw.strip():
        return None
    raw = raw.strip()
    # MM/DD/YYYY format
    if "/" in raw:
        parts = raw.split("/")
        if len(parts) == 3:
            try:
                return int(parts[2])
            except (ValueError, IndexError):
                return None
    # YYYY-MM-DD format
    if "-" in raw:
        try:
            return int(raw[:4])
        except ValueError:
            return None
    return None


def _parse_ut_time(raw) -> Decimal | None:
    """Parse under-tack time to Decimal."""
    if raw is None:
        return None
    try:
        val = Decimal(str(raw))
        return val if val > 0 else None
    except Exception:
        return None


def _parse_hip(horse: dict, sale_key: str) -> FTHip:
    """Parse a single horse record from the API response."""
    status = _parse_sale_status(horse)
    buyer = (horse.get("purchaser") or "").strip() or None
    if status != "sold":
        buyer = None

    # Video URL - prefer under tack show video
    video_url = horse.get("under_tack_show_video") or horse.get("youtube_url")
    thumbnail = horse.get("under_tack_show_thumbnail")

    # Photos - check enhanced and general photo sets
    enhanced_photos = horse.get("enhancedhorsephoto_set") or []
    general_photos = horse.get("generalhorsephoto_set") or []
    photo_url = None
    if enhanced_photos:
        photo_url = enhanced_photos[0].get("photo") if isinstance(enhanced_photos[0], dict) else None
    elif general_photos:
        photo_url = general_photos[0].get("photo") if isinstance(general_photos[0], dict) else None

    name = (horse.get("name") or "").strip() or None

    return FTHip(
        sale_id=sale_key,
        hip_number=int(horse.get("hip", 0)),
        horse_name=name,
        sex=horse.get("sex") or None,
        colour=horse.get("color") or None,
        year_of_birth=_parse_year_of_birth(horse.get("year_of_birth")),
        foaling_date=horse.get("year_of_birth") or None,
        sire=horse.get("sire") or None,
        dam=horse.get("dam") or None,
        dam_sire=horse.get("sire_of_dam") or None,
        consignor=horse.get("consignor") or None,
        consignor_name=horse.get("consignor_name") or None,
        state_bred=horse.get("foaled") or None,
        barn_number=horse.get("barn") or None,
        session_date=horse.get("session") or None,
        under_tack_time=_parse_ut_time(horse.get("under_tack_show_time")),
        under_tack_surface=horse.get("under_tack_show_surface") or None,
        under_tack_date=horse.get("under_tack_show_day") or None,
        sale_price=_parse_sale_price(horse),
        sale_status=status,
        buyer=buyer,
        hammer_price_raw=horse.get("price"),
        photo_url=photo_url,
        video_url=video_url,
        walk_video_url=None,
        video_thumbnail=thumbnail,
        has_photo=photo_url is not None or bool(enhanced_photos) or bool(general_photos),
        has_video=video_url is not None,
    )


def fetch_sale(
    sale_identifier: str,
    sale_key: str,
    session: requests.Session | None = None,
) -> FTSale:
    """Fetch complete sale data from the Fasig-Tipton Django API.

    Args:
        sale_identifier: The FT sale identifier (e.g. 'M24J').
        sale_key: Canonical key for storage (e.g. 'ft_midlantic_2025').
        session: Optional requests session.

    Returns:
        FTSale with all parsed hip data.
    """
    if session is None:
        session = _get_session()

    # Step 1: Find the sale by identifier
    logger.info("Finding sale %s (key=%s)", sale_identifier, sale_key)
    sales_data = _request_with_retry(
        session, f"{API_BASE}/sales/", params={"sale_identifier": sale_identifier}
    )

    if not sales_data:
        raise ValueError(f"Sale not found: {sale_identifier}")

    sale_meta = sales_data[0]
    api_id = sale_meta["id"]

    # Extract year from start date
    start_date = sale_meta.get("sale_start_day")
    year = int(start_date[:4]) if start_date else None

    time.sleep(REQUEST_DELAY_SECONDS)

    # Step 2: Fetch all horses for this sale
    logger.info("Fetching horses for sale %s (api_id=%d)", sale_identifier, api_id)
    horses_data = _request_with_retry(
        session, f"{API_BASE}/horses/", params={"sale": api_id}
    )

    sale = FTSale(
        sale_id=sale_key,
        sale_identifier=sale_identifier,
        api_id=api_id,
        sale_name=sale_meta.get("sale_identifier", sale_identifier),
        year=year or 0,
        start_date=start_date,
        under_tack_start_date=sale_meta.get("under_tack_show_start_day"),
        max_hip=sale_meta.get("max_hip", 0),
        raw_sale=sale_meta,
    )

    for horse in horses_data:
        sale.hips.append(_parse_hip(horse, sale_key))

    logger.info("Parsed sale %s: %d hips", sale_key, len(sale.hips))
    return sale
