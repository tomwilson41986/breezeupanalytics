"""OBS catalog scraper using the WordPress REST API.

Discovery (2026-03-01): The OBS catalog SPA at obssales.com/catalog/# is an
Angular app backed by a WordPress REST API. A single GET to
`/wp-json/obs-catalog-wp-plugin/v1/horse-sales/{sale_id}` returns the entire
sale including all hips with pedigree, results, under tack times, and media URLs.
No headless browser required.
"""

import logging
import time
from dataclasses import dataclass, field
from decimal import Decimal

import requests

from src.config import REQUEST_DELAY_SECONDS, MAX_RETRIES, RETRY_BACKOFF_FACTOR, USER_AGENT

logger = logging.getLogger(__name__)

API_BASE = "https://obssales.com/wp-json/obs-catalog-wp-plugin/v1"


@dataclass
class OBSHip:
    """Parsed hip record from the OBS API."""

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
    consignor_sort: str | None
    state_bred: str | None
    barn_number: str | None
    session_number: str | None

    # Under tack
    under_tack_distance: str | None
    under_tack_time: Decimal | None
    under_tack_date: str | None
    under_tack_set: str | None
    under_tack_group: str | None

    # Sale result
    sale_price: int | None
    sale_status: str  # "sold" | "RNA" | "out" | "withdrawn" | "pending"
    buyer: str | None
    hammer_price_raw: str | None

    # Media URLs
    photo_url: str | None = None
    video_url: str | None = None
    walk_video_url: str | None = None
    pedigree_pdf_url: str | None = None

    # Raw flags
    has_photo: bool = False
    has_video: bool = False
    has_walk_video: bool = False


@dataclass
class OBSSale:
    """Parsed sale record from the OBS API."""

    sale_id: str
    sale_code: str
    sale_name: str
    sale_short_name: str
    year: int
    sale_category: str
    start_date: str | None
    end_date: str | None
    previous_year_sale_id: str | None
    next_sale_id: str | None
    previous_sale_id: str | None
    hips: list[OBSHip] = field(default_factory=list)
    raw_meta: list[dict] = field(default_factory=list)


def _get_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    return session


def _request_with_retry(session: requests.Session, url: str) -> dict:
    """GET with exponential backoff retry."""
    for attempt in range(MAX_RETRIES + 1):
        try:
            resp = session.get(url, timeout=30)
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


def _parse_sale_status(hip_data: dict) -> str:
    """Determine sale status from API display_props and fields."""
    dp = hip_data.get("display_props", {})
    if dp.get("is_hip_out"):
        return "out"
    if dp.get("is_hip_sold"):
        return "sold"
    if dp.get("is_rna"):
        return "RNA"
    if hip_data.get("in_out_status") == "O":
        return "out"
    if dp.get("is_hip_not_through_ring_yet"):
        return "pending"
    return "pending"


def _parse_sale_price(hip_data: dict) -> int | None:
    """Extract sale price in whole dollars. Returns None for RNA/out/pending."""
    raw = hip_data.get("hammer_price")
    if raw is None:
        return None
    try:
        price = float(raw)
    except (ValueError, TypeError):
        return None
    if price <= 0:
        return None  # Negative = RNA reserve amount
    return int(price)


def _parse_ut_time(raw: str | None) -> Decimal | None:
    if not raw or not raw.strip():
        return None
    try:
        return Decimal(raw.strip())
    except Exception:
        return None


def _parse_hip(hip_data: dict) -> OBSHip:
    """Parse a single hip record from the API response."""
    return OBSHip(
        sale_id=str(hip_data.get("sale_id", "")),
        hip_number=int(hip_data.get("hip_number", 0)),
        horse_name=hip_data.get("horse_name") or None,
        sex=hip_data.get("sex") or None,
        colour=hip_data.get("color") or None,
        year_of_birth=int(hip_data["foaling_year"]) if hip_data.get("foaling_year") else None,
        foaling_date=hip_data.get("foaling_date") or None,
        sire=hip_data.get("sire_name") or None,
        dam=hip_data.get("dam_name") or None,
        dam_sire=hip_data.get("dam_sire") or None,
        consignor=hip_data.get("consignor_name") or None,
        consignor_sort=hip_data.get("consignor_sort") or None,
        state_bred=hip_data.get("foaling_area") or None,
        barn_number=hip_data.get("barn_number") or None,
        session_number=hip_data.get("session_number") or None,
        under_tack_distance=(hip_data.get("ut_distance") or "").strip() or None,
        under_tack_time=_parse_ut_time(hip_data.get("ut_time")),
        under_tack_date=hip_data.get("ut_actual_date") or None,
        under_tack_set=hip_data.get("ut_set") or None,
        under_tack_group=hip_data.get("ut_group") or None,
        sale_price=_parse_sale_price(hip_data),
        sale_status=_parse_sale_status(hip_data),
        buyer=hip_data.get("buyer_name") or None,
        hammer_price_raw=str(hip_data.get("hammer_price")) if hip_data.get("hammer_price") else None,
        photo_url=hip_data.get("photo_link") or None,
        video_url=hip_data.get("video_link") or None,
        walk_video_url=hip_data.get("walk_video_link") or None,
        pedigree_pdf_url=hip_data.get("pedigree_pdf_link") or None,
        has_photo=hip_data.get("has_photo") == "1",
        has_video=hip_data.get("has_video") == "1",
        has_walk_video=hip_data.get("has_walk_video") == "1",
    )


def fetch_sale(sale_id: int | str, session: requests.Session | None = None) -> OBSSale:
    """Fetch complete sale data from the OBS REST API.

    Args:
        sale_id: The OBS catalog sale ID (e.g. 142 for 2025 March).
        session: Optional requests session (will create one if not provided).

    Returns:
        OBSSale with all parsed hip data.
    """
    if session is None:
        session = _get_session()

    url = f"{API_BASE}/horse-sales/{sale_id}"
    logger.info("Fetching sale %s from %s", sale_id, url)

    data = _request_with_retry(session, url)

    # Parse year from sale_starts or sale_name
    year = None
    if data.get("sale_starts"):
        year = int(data["sale_starts"][:4])
    elif data.get("sale_name"):
        import re
        m = re.search(r"20\d{2}", data["sale_name"])
        if m:
            year = int(m.group())

    sale = OBSSale(
        sale_id=str(data["sale_id"]),
        sale_code=data.get("sale_code", ""),
        sale_name=data.get("sale_name", ""),
        sale_short_name=data.get("sale_short_name", ""),
        year=year or 0,
        sale_category=data.get("sale_category", ""),
        start_date=data.get("sale_starts"),
        end_date=data.get("sale_ends"),
        previous_year_sale_id=data.get("previous_year_sale_id"),
        next_sale_id=data.get("next_sale_id"),
        previous_sale_id=data.get("previous_sale_id"),
        raw_meta=data.get("sale_meta", []),
    )

    for hip_data in data.get("sale_hip", []):
        sale.hips.append(_parse_hip(hip_data))

    logger.info("Parsed sale %s: %s (%d hips)", sale.sale_id, sale.sale_name, len(sale.hips))
    return sale


def fetch_upcoming_sales(session: requests.Session | None = None) -> list[dict]:
    """Fetch the list of upcoming/current sales."""
    if session is None:
        session = _get_session()
    url = f"{API_BASE}/horse-upcoming-sales"
    return _request_with_retry(session, url)


def discover_sale_ids(session: requests.Session | None = None) -> list[dict]:
    """Discover sale IDs by fetching upcoming sales and following the chain."""
    if session is None:
        session = _get_session()

    upcoming = fetch_upcoming_sales(session)
    sales = []

    for sale_data in upcoming:
        sales.append({
            "sale_id": sale_data["sale_id"],
            "sale_name": sale_data["sale_name"],
            "sale_category": sale_data.get("sale_category"),
            "sale_starts": sale_data.get("sale_starts"),
        })

    return sales
