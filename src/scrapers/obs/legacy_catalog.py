"""Scraper for the old OBS catalog site (obscatalog.com) used for 2023 sales.

The old site embeds sale data in a JavaScript array `arrData` in the page HTML.
This scraper extracts that array and parses it into OBSHip/OBSSale dataclasses
compatible with the existing ingest pipeline.

Column layouts differ by sale:
  - March 2023 (12 cols): no walk video column
  - Spring/June 2023 (13 cols): includes walk video column
"""

import logging
import re
from decimal import Decimal

import requests

from src.config import USER_AGENT
from src.scrapers.obs.catalog import OBSHip, OBSSale

logger = logging.getLogger(__name__)

# Map sale codes to URLs and metadata
LEGACY_SALES = {
    "obs_march_2023": {
        "url": "https://www.obscatalog.com/marresults/2023/",
        "sale_code": "mar",
        "sale_name": "2023 March 2YO in Training Sale",
        "year": 2023,
        "catalog_id": "130",
        "has_walk": False,
    },
    "obs_spring_2023": {
        "url": "https://www.obscatalog.com/aprresults/2023/",
        "sale_code": "apr",
        "sale_name": "2023 Spring 2YOs In Training Sale",
        "year": 2023,
        "catalog_id": "131",
        "has_walk": True,
    },
    "obs_june_2023": {
        "url": "https://www.obscatalog.com/junresults/2023/",
        "sale_code": "jun",
        "sale_name": "2023 June 2YO in Training and Horses of Racing Age Sale",
        "year": 2023,
        "catalog_id": "132",
        "has_walk": True,
    },
}

# Base URL for direct media files
MEDIA_BASE = "https://obscatalog.com"


def _extract_arr_data(html: str) -> list[list[str]]:
    """Extract the arrData JavaScript array from page source."""
    # The array is defined as: var arrData = [ [...], [...], ... ];
    match = re.search(r"var\s+arrData\s*=\s*(\[.*?\])\s*;", html, re.DOTALL)
    if not match:
        raise ValueError("Could not find arrData in page source")

    raw = match.group(1)

    # The data uses single-quoted strings with HTML inside.
    # We need to parse this carefully. It's essentially a JS array literal.
    # Strategy: use a simple state-machine parser since json.loads won't work
    # with single quotes and unescaped HTML.
    rows = []
    current_row = []
    current_str = []
    in_string = False
    quote_char = None
    i = 0

    while i < len(raw):
        ch = raw[i]

        if not in_string:
            if ch in ('"', "'"):
                in_string = True
                quote_char = ch
                current_str = []
            elif ch == ']' and not current_row and not rows:
                # Empty array
                break
            elif ch == ']' and current_row:
                # End of inner array
                rows.append(current_row)
                current_row = []
        else:
            if ch == '\\' and i + 1 < len(raw):
                # Escaped character
                current_str.append(raw[i + 1])
                i += 2
                continue
            elif ch == quote_char:
                # End of string
                in_string = False
                current_row.append("".join(current_str))
            else:
                current_str.append(ch)

        i += 1

    return rows


def _extract_href(html_fragment: str) -> str | None:
    """Extract first href from an HTML fragment."""
    if not html_fragment or html_fragment.strip() == "":
        return None
    match = re.search(r'href=["\']([^"\']+)["\']', html_fragment)
    if match:
        url = match.group(1)
        # Normalize to https
        return url.replace("http://", "https://")
    return None


def _extract_hip_number(html_fragment: str) -> int | None:
    """Extract hip number from the PDF link column."""
    # The hip column contains: <a href='...'>123</a>
    match = re.search(r'>(\d+)</a>', html_fragment)
    if match:
        return int(match.group(1))
    # Fallback: try plain number
    match = re.search(r'(\d+)', html_fragment)
    if match:
        return int(match.group(1))
    return None


def _parse_ut_time(raw: str) -> Decimal | None:
    """Parse under-tack time. Returns None for 'out', empty, etc."""
    if not raw or not raw.strip():
        return None
    cleaned = raw.strip().lower()
    if cleaned in ("out", "o", ""):
        return None
    try:
        return Decimal(cleaned)
    except Exception:
        return None


def _parse_price(raw: str) -> int | None:
    """Parse price string like '37,000' to int."""
    if not raw or not raw.strip():
        return None
    cleaned = raw.strip().replace(",", "").replace("$", "")
    if cleaned.lower() in ("out", "withdrawn", "not sold", ""):
        return None
    try:
        return int(cleaned)
    except ValueError:
        return None


def _parse_sale_status(buyer: str, price_str: str) -> str:
    """Determine sale status from buyer/price columns."""
    buyer_lower = (buyer or "").strip().lower()
    price_lower = (price_str or "").strip().lower()

    if buyer_lower == "withdrawn" or price_lower == "out":
        return "out"
    if buyer_lower == "not sold":
        return "RNA"
    if buyer and buyer_lower not in ("", "withdrawn", "not sold"):
        return "sold"
    return "out"


def _expand_sex(code: str | None) -> str | None:
    if not code:
        return None
    return {"C": "C", "F": "F", "G": "G", "R": "R"}.get(code.strip().upper(), code)


def fetch_legacy_sale(sale_key: str) -> OBSSale:
    """Fetch and parse a 2023 sale from the old obscatalog.com site.

    Args:
        sale_key: One of 'obs_march_2023', 'obs_spring_2023', 'obs_june_2023'

    Returns:
        OBSSale with parsed hip data.
    """
    if sale_key not in LEGACY_SALES:
        raise ValueError(f"Unknown legacy sale: {sale_key}. Valid: {list(LEGACY_SALES.keys())}")

    meta = LEGACY_SALES[sale_key]
    url = meta["url"]
    sale_code = meta["sale_code"]
    year = meta["year"]
    has_walk = meta["has_walk"]

    logger.info("Fetching legacy sale %s from %s", sale_key, url)

    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    resp = session.get(url, timeout=30)
    resp.raise_for_status()

    rows = _extract_arr_data(resp.text)
    logger.info("Extracted %d rows from arrData", len(rows))

    sale = OBSSale(
        sale_id=meta["catalog_id"],
        sale_code=sale_code,
        sale_name=meta["sale_name"],
        sale_short_name=f"{sale_code.upper()} {year}",
        year=year,
        sale_category="2yo",
        start_date=None,
        end_date=None,
        previous_year_sale_id=None,
        next_sale_id=None,
        previous_sale_id=None,
    )

    for row in rows:
        if has_walk:
            # 13-column layout: [checkbox, hip_pdf, walk_video, sale_video, ut_time, sex, sire, dam, state, consignor, buyer, price, ps]
            if len(row) < 13:
                continue
            hip_html = row[1]
            walk_html = row[2]
            video_html = row[3]
            ut_raw = row[4]
            sex = row[5]
            sire = row[6]
            dam = row[7]
            state = row[8]
            consignor = row[9]
            buyer = row[10]
            price_str = row[11]
        else:
            # 12-column layout: [checkbox, hip_pdf, sale_video, ut_time, sex, sire, dam, state, consignor, buyer, price, ps]
            if len(row) < 12:
                continue
            hip_html = row[1]
            walk_html = ""
            video_html = row[2]
            ut_raw = row[3]
            sex = row[4]
            sire = row[5]
            dam = row[6]
            state = row[7]
            consignor = row[8]
            buyer = row[9]
            price_str = row[10]

        hip_number = _extract_hip_number(hip_html)
        if hip_number is None:
            continue

        # Extract URLs
        pdf_url = _extract_href(hip_html)
        video_url = _extract_href(video_html)
        walk_video_url = _extract_href(walk_html) if has_walk else None

        ut_time = _parse_ut_time(ut_raw)
        sale_price = _parse_price(price_str)
        sale_status = _parse_sale_status(buyer, price_str)

        hip = OBSHip(
            sale_id=meta["catalog_id"],
            hip_number=hip_number,
            horse_name=None,  # Not available on old site
            sex=_expand_sex(sex),
            colour=None,
            year_of_birth=None,
            foaling_date=None,
            sire=sire.strip() if sire else None,
            dam=dam.strip() if dam else None,
            dam_sire=None,  # Not available on old site
            consignor=consignor.strip() if consignor else None,
            consignor_sort=None,
            state_bred=state.strip() if state else None,
            barn_number=None,
            session_number=None,
            under_tack_distance=None,  # Will be inferred from time
            under_tack_time=ut_time,
            under_tack_date=None,
            under_tack_set=None,
            under_tack_group=None,
            sale_price=sale_price,
            sale_status=sale_status,
            buyer=buyer.strip() if buyer and buyer.strip().lower() not in ("withdrawn", "not sold", "") else None,
            hammer_price_raw=price_str,
            photo_url=None,
            video_url=video_url,
            walk_video_url=walk_video_url,
            pedigree_pdf_url=pdf_url,
            has_photo=False,
            has_video=bool(video_url),
            has_walk_video=bool(walk_video_url),
        )
        sale.hips.append(hip)

    with_ut = sum(1 for h in sale.hips if h.under_tack_time is not None)
    with_video = sum(1 for h in sale.hips if h.video_url)
    with_walk = sum(1 for h in sale.hips if h.walk_video_url)
    logger.info("Parsed %s: %d hips, %d with UT, %d videos, %d walks",
                sale_key, len(sale.hips), with_ut, with_video, with_walk)

    return sale
