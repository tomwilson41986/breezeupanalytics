"""Scraper for legacy OBS results pages at obscatalog.com.

These pages (2018-2023) store sale results in a JavaScript `arrData` array
embedded in the HTML. The array format varies by year:

  Format A (2018): No state, no walk video
    [checkbox, hip_link, video, ut_time, sex, sire, dam,
     consignor, buyer, price, ps, ...sort_fields]

  Format B (2019-2020): Has state, no walk video
    [checkbox, hip_link, video, ut_time, sex, sire, dam, state,
     consignor, buyer, price, ps, ...sort_fields]

  Format C (2021-2023): Has state and walk video
    [checkbox, hip_link, walk_link, video_link, ut_time, sex, sire, dam,
     state, consignor, buyer, price, ps, ...sort_fields]

The format is auto-detected by parsing the <thead> column headers.
"""

import json
import logging
import re
import time
from dataclasses import asdict
from decimal import Decimal

import requests
from bs4 import BeautifulSoup

from src.config import REQUEST_DELAY_SECONDS, MAX_RETRIES, RETRY_BACKOFF_FACTOR, USER_AGENT
from src.scrapers.obs.catalog import OBSHip

logger = logging.getLogger(__name__)

# Column header patterns to detect format
_WALK_HEADERS = {"walk"}
_STATE_HEADERS = {"state", "st"}


def _get_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    return session


def _fetch_with_retry(session: requests.Session, url: str) -> str:
    """GET with exponential backoff, returns HTML text."""
    for attempt in range(MAX_RETRIES + 1):
        try:
            resp = session.get(url, timeout=30)
            resp.raise_for_status()
            return resp.text
        except requests.RequestException as e:
            if attempt == MAX_RETRIES:
                raise
            wait = REQUEST_DELAY_SECONDS * (RETRY_BACKOFF_FACTOR ** attempt)
            logger.warning("Request failed (attempt %d/%d): %s. Retrying in %.1fs",
                           attempt + 1, MAX_RETRIES, e, wait)
            time.sleep(wait)
    raise RuntimeError("unreachable")


def _extract_arr_data(html: str) -> list[list[str]]:
    """Extract the arrData JavaScript array from the HTML source.

    Uses bracket-counting rather than regex to handle nested arrays
    with HTML content that contains brackets and quotes.
    """
    marker = re.search(r'var\s+arrData\s*=\s*\[', html)
    if not marker:
        raise ValueError("Could not find arrData in page source")

    start = marker.end() - 1  # position of opening [
    depth = 0
    i = start
    end = len(html)
    while i < end:
        c = html[i]
        if c == '[':
            depth += 1
        elif c == ']':
            depth -= 1
            if depth == 0:
                raw = html[start:i + 1]
                return json.loads(raw)
        elif c == '"':
            # Skip double-quoted string
            i += 1
            while i < end and html[i] != '"':
                if html[i] == '\\':
                    i += 1  # skip escaped char
                i += 1
        elif c == "'":
            # Skip single-quoted string
            i += 1
            while i < end and html[i] != "'":
                if html[i] == '\\':
                    i += 1
                i += 1
        i += 1

    raise ValueError("Could not find closing bracket for arrData")


def _detect_columns(html: str) -> dict[str, int]:
    """Detect column layout from the HTML thead.

    Returns a mapping of canonical field name -> column index.
    """
    soup = BeautifulSoup(html, "html.parser")
    thead = soup.find("thead")
    if not thead:
        # Fallback: look for the DataTable header row
        thead = soup.find("tr", class_="header") or soup.find("tr")

    headers = []
    if thead:
        for th in thead.find_all(["th", "td"]):
            text = th.get_text(strip=True).lower()
            headers.append(text)

    # Build column mapping based on detected headers
    col_map: dict[str, int] = {}

    # Always present
    col_map["checkbox"] = 0
    col_map["hip_link"] = 1

    has_walk = any(h in _WALK_HEADERS for h in headers)
    has_state = any(h in _STATE_HEADERS for h in headers)

    if has_walk:
        # Format C: walk, video, ut_time, sex, sire, dam, state, consignor, buyer, price, ps
        col_map["walk_link"] = 2
        col_map["video_link"] = 3
        col_map["ut_time"] = 4
        col_map["sex"] = 5
        col_map["sire"] = 6
        col_map["dam"] = 7
        col_map["state"] = 8
        col_map["consignor"] = 9
        col_map["buyer"] = 10
        col_map["price"] = 11
        col_map["ps"] = 12
    elif has_state:
        # Format B: video, ut_time, sex, sire, dam, state, consignor, buyer, price, ps
        col_map["video_link"] = 2
        col_map["ut_time"] = 3
        col_map["sex"] = 4
        col_map["sire"] = 5
        col_map["dam"] = 6
        col_map["state"] = 7
        col_map["consignor"] = 8
        col_map["buyer"] = 9
        col_map["price"] = 10
        col_map["ps"] = 11
    else:
        # Format A: video, ut_time, sex, sire, dam, consignor, buyer, price, ps
        col_map["video_link"] = 2
        col_map["ut_time"] = 3
        col_map["sex"] = 4
        col_map["sire"] = 5
        col_map["dam"] = 6
        col_map["consignor"] = 7
        col_map["buyer"] = 8
        col_map["price"] = 9
        col_map["ps"] = 10

    logger.info("Detected columns: walk=%s, state=%s → %s",
                has_walk, has_state,
                "Format C" if has_walk else "Format B" if has_state else "Format A")

    return col_map


def _extract_hip_number(cell: str) -> int:
    """Extract hip number from the link HTML: <a href='...'>123</a> -> 123."""
    m = re.search(r'>(\d+)<', cell)
    if m:
        return int(m.group(1))
    # Fallback: try plain number
    m = re.search(r'(\d+)', cell)
    return int(m.group(1)) if m else 0


def _extract_video_url(cell: str) -> str | None:
    """Extract video URL from HTML link."""
    m = re.search(r'href=["\']([^"\']+\.mp4)["\']', cell)
    return m.group(1) if m else None


def _parse_price(raw: str) -> int | None:
    """Parse price string like '105,000' to int. Returns None for non-numeric."""
    if not raw or not raw.strip():
        return None
    cleaned = raw.strip().replace(",", "").replace("$", "")
    try:
        val = int(float(cleaned))
        return val if val > 0 else None
    except (ValueError, TypeError):
        return None


def _parse_ut_time(raw: str) -> Decimal | None:
    """Parse under-tack time like '10.2' to Decimal."""
    if not raw or not raw.strip():
        return None
    cleaned = raw.strip()
    # Skip non-numeric values like "out"
    try:
        return Decimal(cleaned)
    except Exception:
        return None


def _derive_ut_distance(time_val: Decimal | None) -> str | None:
    """Derive under-tack distance from the breeze time.

    OBS legacy pages (2018-2023) record the time but not the distance.
    The distance is unambiguous from the time value — the ranges have
    zero overlap:
      ≤ 15 s  → 1/8 mile  (typical 9–12 s)
      ≤ 27 s  → 1/4 mile  (typical 20–24 s)
      > 27 s  → 3/8 mile  (typical 31–36 s)
    """
    if time_val is None:
        return None
    t = float(time_val)
    if t <= 15:
        return "1/8"
    if t <= 27:
        return "1/4"
    return "3/8"


def _determine_sale_status(buyer: str, price: str, ps: str, ut_time: str) -> str:
    """Determine sale status from buyer/price/PS fields."""
    buyer_lower = (buyer or "").strip().lower()
    price_lower = (price or "").strip().lower()
    ps_lower = (ps or "").strip().lower()
    ut_lower = (ut_time or "").strip().lower()

    if ut_lower == "out" or buyer_lower == "withdrawn" or ps_lower == "out":
        return "out"
    if "not sold" in buyer_lower or "not sold" in price_lower or "rna" in buyer_lower:
        return "RNA"
    if ps_lower == "ps":
        return "sold"  # PS = post-sale (still sold)
    if _parse_price(price) is not None:
        return "sold"
    return "out"


def _parse_sale_name(sale_key: str, sale_code: str, year: int) -> str:
    """Generate a sale name from the key."""
    name_map = {
        "mar": "March 2YO in Training",
        "apr": "Spring 2YO in Training",
        "jun": "June 2YO & HRA",
        "jul": "June/July 2YO & HRA",  # 2020 COVID delay
    }
    season = name_map.get(sale_code, sale_code.title())
    return f"OBS {season} {year}"


def fetch_legacy_sale(
    sale_key: str,
    url: str,
    sale_code: str,
    year: int,
    session: requests.Session | None = None,
) -> dict:
    """Fetch and parse a legacy OBS results page.

    Args:
        sale_key: Canonical key like 'obs_march_2023'.
        url: Full URL to the results page.
        sale_code: Sale code prefix (mar/apr/jun/jul).
        year: Sale year.
        session: Optional requests session.

    Returns:
        Dict with sale metadata and list of hip dicts (matching OBSHip schema).
    """
    if session is None:
        session = _get_session()

    logger.info("Fetching legacy sale %s from %s", sale_key, url)
    html = _fetch_with_retry(session, url)

    col_map = _detect_columns(html)
    rows = _extract_arr_data(html)

    hips: list[dict] = []
    for row in rows:
        # Safely get fields by column index
        def get(key: str) -> str:
            idx = col_map.get(key)
            if idx is None or idx >= len(row):
                return ""
            return row[idx]

        hip_number = _extract_hip_number(get("hip_link"))
        if hip_number == 0:
            continue

        ut_raw = get("ut_time")
        buyer_raw = get("buyer").strip()
        price_raw = get("price").strip()
        ps_raw = get("ps")

        status = _determine_sale_status(buyer_raw, price_raw, ps_raw, ut_raw)

        # In legacy pages, RNA hips show the bid amount in the "buyer" column
        # and "Not Sold" in the "price" column. Normalize so that:
        #   - sale_price = the actual sold price (None for RNA/out)
        #   - buyer = the actual buyer name (None for RNA/out)
        #   - hammer_price_raw = the bid/hammer amount regardless of status
        if status == "RNA":
            # The "buyer" column has the RNA bid amount, "price" has "Not Sold"
            hammer_raw = buyer_raw if _parse_price(buyer_raw) is not None else price_raw
            sale_price = None
            buyer_name = None
        elif status == "sold":
            sale_price = _parse_price(price_raw)
            # If price column is empty but buyer looks like a price, handle swap
            if sale_price is None and _parse_price(buyer_raw) is not None:
                sale_price = _parse_price(buyer_raw)
                buyer_name = None
            else:
                buyer_name = buyer_raw or None
            hammer_raw = price_raw
        else:
            sale_price = None
            buyer_name = None
            hammer_raw = price_raw

        ut_time = _parse_ut_time(ut_raw)
        ut_distance = _derive_ut_distance(ut_time)
        video_url = _extract_video_url(get("video_link"))
        walk_url = _extract_video_url(get("walk_link")) if "walk_link" in col_map else None

        # Build the pedigree PDF URL from hip number
        # Pattern: https://obscatalog.com/{sale_code}/{year}/{hip}.PDF
        pedigree_url = f"https://obscatalog.com/{sale_code}/{year}/{hip_number}.PDF"

        hip = OBSHip(
            sale_id=sale_key,
            hip_number=hip_number,
            horse_name=None,  # Not available in legacy results
            sex=get("sex").strip() or None,
            colour=None,  # Not available in legacy results
            year_of_birth=year - 2,  # 2YO sale = born 2 years prior
            foaling_date=None,
            sire=get("sire").strip() or None,
            dam=get("dam").strip() or None,
            dam_sire=None,  # Not available in legacy results
            consignor=get("consignor").strip() or None,
            consignor_sort=None,
            state_bred=get("state").strip() or None if "state" in col_map else None,
            barn_number=None,
            session_number=None,
            under_tack_distance=ut_distance,
            under_tack_time=ut_time,
            under_tack_date=None,
            under_tack_set=None,
            under_tack_group=None,
            sale_price=sale_price,
            sale_status=status,
            buyer=buyer_name,
            hammer_price_raw=hammer_raw or None,
            photo_url=None,
            video_url=video_url,
            walk_video_url=walk_url,
            pedigree_pdf_url=pedigree_url,
            has_photo=False,
            has_video=video_url is not None,
            has_walk_video=walk_url is not None,
        )
        hips.append(hip)

    sale_name = _parse_sale_name(sale_key, sale_code, year)
    logger.info("Parsed legacy sale %s: %s (%d hips)", sale_key, sale_name, len(hips))

    return {
        "sale_id": sale_key,
        "sale_code": sale_code,
        "sale_name": sale_name,
        "year": year,
        "source_url": url,
        "hips": hips,
    }


def hip_to_dict(hip: OBSHip) -> dict:
    """Convert an OBSHip dataclass to a JSON-serializable dict."""
    d = asdict(hip)
    # Convert Decimal to float for JSON serialization
    if d.get("under_tack_time") is not None:
        d["under_tack_time"] = float(d["under_tack_time"])
    return d
