"""Scraper for the old OBS catalog site (obscatalog.com) used for 2018-2023 sales.

The old site embeds sale data in a JavaScript array `arrData` in the page HTML.
This scraper extracts that array and parses it into OBSHip/OBSSale dataclasses
compatible with the existing ingest pipeline.

Column layouts differ by sale:
  - "no_walk_no_state" (11 data cols): 2018 March only
  - "no_walk_with_state" (12 data cols): most March sales 2019+, all 2018-2020 non-March
  - "walk_with_state" (13 data cols): Spring/June from 2021 onwards
"""

import logging
import re
from decimal import Decimal

import requests

from src.config import USER_AGENT
from src.scrapers.obs.catalog import OBSHip, OBSSale

logger = logging.getLogger(__name__)

# Base URL for results pages and direct media files
RESULTS_BASE = "https://www.obscatalog.com"
MEDIA_BASE = "https://obscatalog.com"

# Layout constants
NO_WALK_NO_STATE = "no_walk_no_state"
NO_WALK_WITH_STATE = "no_walk_with_state"
WALK_WITH_STATE = "walk_with_state"

# Map sale keys to URLs and metadata
LEGACY_SALES = {
    # ── 2018 ──────────────────────────────────────────────
    "obs_march_2018": {
        "url": f"{RESULTS_BASE}/marresults/2018/",
        "sale_code": "mar",
        "sale_name": "March 2018 Two-Year-Olds In Training Sale",
        "year": 2018,
        "layout": NO_WALK_NO_STATE,
    },
    "obs_spring_2018": {
        "url": f"{RESULTS_BASE}/aprresults/2018/",
        "sale_code": "apr",
        "sale_name": "2018 Spring Sale of Two-Year-Olds in Training",
        "year": 2018,
        "layout": NO_WALK_WITH_STATE,
    },
    "obs_june_2018": {
        "url": f"{RESULTS_BASE}/junresults/2018/",
        "sale_code": "jun",
        "sale_name": "2018 June Two-Year-Olds & Horses of Racing Age",
        "year": 2018,
        "layout": NO_WALK_WITH_STATE,
    },
    # ── 2019 ──────────────────────────────────────────────
    "obs_march_2019": {
        "url": f"{RESULTS_BASE}/marresults/2019/",
        "sale_code": "mar",
        "sale_name": "March 2019 Two-Year-Olds In Training Sale",
        "year": 2019,
        "layout": NO_WALK_WITH_STATE,
    },
    "obs_spring_2019": {
        "url": f"{RESULTS_BASE}/aprresults/2019/",
        "sale_code": "apr",
        "sale_name": "2019 Spring Sale of Two-Year-Olds in Training",
        "year": 2019,
        "layout": NO_WALK_WITH_STATE,
    },
    "obs_june_2019": {
        "url": f"{RESULTS_BASE}/junresults/2019/",
        "sale_code": "jun",
        "sale_name": "2019 June Two-Year-Olds & Horses of Racing Age",
        "year": 2019,
        "layout": NO_WALK_WITH_STATE,
    },
    # ── 2020 ──────────────────────────────────────────────
    "obs_march_2020": {
        "url": f"{RESULTS_BASE}/marresults/2020/",
        "sale_code": "mar",
        "sale_name": "March 2020 Two-Year-Olds In Training Sale",
        "year": 2020,
        "layout": NO_WALK_WITH_STATE,
    },
    "obs_spring_2020": {
        "url": f"{RESULTS_BASE}/aprresults/2020/",
        "sale_code": "apr",
        "sale_name": "2020 Spring Sale of Two-Year-Olds in Training",
        "year": 2020,
        "layout": NO_WALK_WITH_STATE,
    },
    "obs_june_2020": {
        "url": f"{RESULTS_BASE}/julresults/2020/",
        "sale_code": "jul",
        "sale_name": "2020 July Two-Year-Olds & Horses of Racing Age",
        "year": 2020,
        "layout": NO_WALK_WITH_STATE,
    },
    # ── 2021 ──────────────────────────────────────────────
    "obs_march_2021": {
        "url": f"{RESULTS_BASE}/marresults/2021/",
        "sale_code": "mar",
        "sale_name": "March 2021 Two-Year-Olds In Training Sale",
        "year": 2021,
        "layout": NO_WALK_WITH_STATE,
    },
    "obs_spring_2021": {
        "url": f"{RESULTS_BASE}/aprresults/2021/",
        "sale_code": "apr",
        "sale_name": "2021 Spring Sale of Two-Year-Olds in Training",
        "year": 2021,
        "layout": WALK_WITH_STATE,
    },
    "obs_june_2021": {
        "url": f"{RESULTS_BASE}/junresults/2021/",
        "sale_code": "jun",
        "sale_name": "2021 June Two-Year-Olds & Horses of Racing Age",
        "year": 2021,
        "layout": WALK_WITH_STATE,
    },
    # ── 2022 ──────────────────────────────────────────────
    "obs_march_2022": {
        "url": f"{RESULTS_BASE}/marresults/2022/",
        "sale_code": "mar",
        "sale_name": "March 2022 Two-Year-Olds In Training Sale",
        "year": 2022,
        "layout": NO_WALK_WITH_STATE,
    },
    "obs_spring_2022": {
        "url": f"{RESULTS_BASE}/aprresults/2022/",
        "sale_code": "apr",
        "sale_name": "2022 Spring Sale of Two-Year-Olds in Training",
        "year": 2022,
        "layout": WALK_WITH_STATE,
    },
    "obs_june_2022": {
        "url": f"{RESULTS_BASE}/junresults/2022/",
        "sale_code": "jun",
        "sale_name": "2022 June Two-Year-Olds & Horses of Racing Age",
        "year": 2022,
        "layout": WALK_WITH_STATE,
    },
    # ── 2023 ──────────────────────────────────────────────
    "obs_march_2023": {
        "url": f"{RESULTS_BASE}/marresults/2023/",
        "sale_code": "mar",
        "sale_name": "2023 March 2YO in Training Sale",
        "year": 2023,
        "layout": NO_WALK_WITH_STATE,
    },
    "obs_spring_2023": {
        "url": f"{RESULTS_BASE}/aprresults/2023/",
        "sale_code": "apr",
        "sale_name": "2023 Spring 2YOs In Training Sale",
        "year": 2023,
        "layout": WALK_WITH_STATE,
    },
    "obs_june_2023": {
        "url": f"{RESULTS_BASE}/junresults/2023/",
        "sale_code": "jun",
        "sale_name": "2023 June 2YO and Horses of Racing Age Sale",
        "year": 2023,
        "layout": WALK_WITH_STATE,
    },
}


def _extract_arr_data(html: str) -> list[list[str]]:
    """Extract the arrData JavaScript array from page source."""
    match = re.search(r"var\s+arrData\s*=\s*(\[.*?\])\s*;", html, re.DOTALL)
    if not match:
        raise ValueError("Could not find arrData in page source")

    raw = match.group(1)

    # Parse the JS array literal with single-quoted strings and unescaped HTML.
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
                break
            elif ch == ']' and current_row:
                rows.append(current_row)
                current_row = []
        else:
            if ch == '\\' and i + 1 < len(raw):
                current_str.append(raw[i + 1])
                i += 2
                continue
            elif ch == quote_char:
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
        return url.replace("http://", "https://")
    return None


def _extract_hip_number(html_fragment: str) -> int | None:
    """Extract hip number from the PDF link column."""
    match = re.search(r'>(\d+)</a>', html_fragment)
    if match:
        return int(match.group(1))
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
    """Fetch and parse a legacy sale from obscatalog.com.

    Args:
        sale_key: e.g. 'obs_march_2018', 'obs_spring_2022', 'obs_june_2023'

    Returns:
        OBSSale with parsed hip data.
    """
    if sale_key not in LEGACY_SALES:
        raise ValueError(f"Unknown legacy sale: {sale_key}. Valid: {sorted(LEGACY_SALES.keys())}")

    meta = LEGACY_SALES[sale_key]
    url = meta["url"]
    sale_code = meta["sale_code"]
    year = meta["year"]
    layout = meta["layout"]

    logger.info("Fetching legacy sale %s from %s", sale_key, url)

    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    resp = session.get(url, timeout=30)
    resp.raise_for_status()

    rows = _extract_arr_data(resp.text)
    logger.info("Extracted %d rows from arrData", len(rows))

    sale = OBSSale(
        sale_id=sale_key,
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
        hip = _parse_row(row, layout, sale_code, year, sale_key)
        if hip is not None:
            sale.hips.append(hip)

    with_ut = sum(1 for h in sale.hips if h.under_tack_time is not None)
    with_video = sum(1 for h in sale.hips if h.video_url)
    with_walk = sum(1 for h in sale.hips if h.walk_video_url)
    logger.info("Parsed %s: %d hips, %d with UT, %d videos, %d walks",
                sale_key, len(sale.hips), with_ut, with_video, with_walk)

    return sale


def _parse_row(row: list[str], layout: str, sale_code: str, year: int,
               sale_key: str) -> OBSHip | None:
    """Parse a single arrData row into an OBSHip based on the column layout."""

    if layout == WALK_WITH_STATE:
        # 13-column: checkbox, hip, walk, video, ut_time, sex, sire, dam, state, consignor, buyer, price, ps
        if len(row) < 13:
            return None
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

    elif layout == NO_WALK_WITH_STATE:
        # 12-column: checkbox, hip, video, ut_time, sex, sire, dam, state, consignor, buyer, price, ps
        if len(row) < 12:
            return None
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

    elif layout == NO_WALK_NO_STATE:
        # 11-column: checkbox, hip, video, ut_time, sex, sire, dam, consignor, buyer, price, ps
        if len(row) < 11:
            return None
        hip_html = row[1]
        walk_html = ""
        video_html = row[2]
        ut_raw = row[3]
        sex = row[4]
        sire = row[5]
        dam = row[6]
        state = None
        consignor = row[7]
        buyer = row[8]
        price_str = row[9]
    else:
        return None

    hip_number = _extract_hip_number(hip_html)
    if hip_number is None:
        return None

    # Extract URLs from HTML fragments
    pdf_url = _extract_href(hip_html)
    video_url = _extract_href(video_html)
    walk_video_url = _extract_href(walk_html) if walk_html else None

    ut_time = _parse_ut_time(ut_raw)
    sale_price = _parse_price(price_str)
    sale_status = _parse_sale_status(buyer, price_str)

    # Clean buyer field
    buyer_clean = buyer.strip() if buyer else None
    if buyer_clean and buyer_clean.lower() in ("withdrawn", "not sold", ""):
        buyer_clean = None

    return OBSHip(
        sale_id=sale_key,
        hip_number=hip_number,
        horse_name=None,
        sex=_expand_sex(sex),
        colour=None,
        year_of_birth=None,
        foaling_date=None,
        sire=sire.strip() if sire else None,
        dam=dam.strip() if dam else None,
        dam_sire=None,
        consignor=consignor.strip() if consignor else None,
        consignor_sort=None,
        state_bred=state.strip() if state else None,
        barn_number=None,
        session_number=None,
        under_tack_distance=None,
        under_tack_time=ut_time,
        under_tack_date=None,
        under_tack_set=None,
        under_tack_group=None,
        sale_price=sale_price,
        sale_status=sale_status,
        buyer=buyer_clean,
        hammer_price_raw=price_str,
        photo_url=None,
        video_url=video_url,
        walk_video_url=walk_video_url,
        pedigree_pdf_url=pdf_url,
        has_photo=False,
        has_video=bool(video_url),
        has_walk_video=bool(walk_video_url),
    )
