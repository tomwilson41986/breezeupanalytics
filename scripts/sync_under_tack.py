#!/usr/bin/env python3
"""Fetch Under Tack data from the OBS REST API and save locally + upload to S3.

This script pulls the latest Under Tack times, horse data, and video URLs
for horses breezing each day during the Under Tack show period.

Output:
    data/under-tack/{sale_key}/daily/{date}.json   — hips that breezed on that date
    data/under-tack/{sale_key}/latest.json          — all hips with UT data so far
    data/under-tack/{sale_key}/videos.json          — under tack video links & PDFs

S3 layout:
    data/{sale_key}/under-tack/daily/{date}.json
    data/{sale_key}/under-tack/latest.json
    data/{sale_key}/under-tack/videos.json

Usage:
    python scripts/sync_under_tack.py                        # sync current active sale
    python scripts/sync_under_tack.py obs_march_2026         # sync specific sale
    python scripts/sync_under_tack.py --sale-id 149          # sync by catalog ID
"""

import json
import logging
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config import OBS_CATALOG_IDS
from src.scrapers.obs.catalog import fetch_sale

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)
logger = logging.getLogger("sync_under_tack")

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "under-tack"


class DecimalEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, Decimal):
            return float(o)
        return super().default(o)


def _parse_ut_time(raw) -> float | None:
    """Parse a ut_time value, returning None for non-numeric entries (e.g. 'G')."""
    if not raw:
        return None
    try:
        return float(raw)
    except (ValueError, TypeError):
        return None


def _parse_ut_hip(hip_data: dict) -> dict:
    """Extract under-tack-relevant fields from a raw API hip record."""
    return {
        "hip_number": int(hip_data.get("hip_number", 0)),
        "horse_name": hip_data.get("horse_name") or None,
        "sex": hip_data.get("sex") or None,
        "color": hip_data.get("color") or None,
        "sire": hip_data.get("sire_name") or None,
        "dam": hip_data.get("dam_name") or None,
        "dam_sire": hip_data.get("dam_sire") or None,
        "consignor": hip_data.get("consignor_name") or None,
        "session_number": hip_data.get("session_number") or None,
        "barn_number": hip_data.get("barn_number") or None,
        "state_bred": hip_data.get("foaling_area") or None,
        # Under tack fields
        "ut_time": _parse_ut_time(hip_data.get("ut_time")),
        "ut_distance": (hip_data.get("ut_distance") or "").strip() or None,
        "ut_set": hip_data.get("ut_set") or None,
        "ut_group": hip_data.get("ut_group") or None,
        "ut_expected_date": hip_data.get("ut_expected_date") or None,
        "ut_actual_date": hip_data.get("ut_actual_date") or None,
        # Video URLs
        "video_url": hip_data.get("video_link") or None,
        "walk_video_url": hip_data.get("walk_video_link") or None,
        "pedigree_pdf_url": hip_data.get("pedigree_pdf_link") or None,
        "updates_url": hip_data.get("updates_link") or None,
        # Status flags
        "has_video": hip_data.get("has_video") == "1" or hip_data.get("has_video") == 1,
        "has_walk_video": hip_data.get("has_walk_video") == "1" or hip_data.get("has_walk_video") == 1,
        "in_out_status": hip_data.get("in_out_status") or "I",
    }


def _extract_ut_meta(sale_meta: list[dict]) -> dict:
    """Extract under tack videos and links from sale metadata."""
    videos = []
    links = []
    sessions_info = None

    for m in sale_meta:
        key = m.get("meta_key", "")
        value = m.get("meta_value", "")
        if key == "under_tack_videos_json" and value:
            try:
                videos = json.loads(value)
            except (json.JSONDecodeError, TypeError):
                pass
        elif key == "under_tack_links_json" and value:
            try:
                links = json.loads(value)
            except (json.JSONDecodeError, TypeError):
                pass
        elif key == "sale_sessions" and value:
            try:
                sessions_info = json.loads(value)
            except (json.JSONDecodeError, TypeError):
                pass

    return {
        "videos": videos,
        "links": links,
        "sessions": sessions_info,
    }


def fetch_under_tack_data(catalog_id: int) -> dict:
    """Fetch sale from API and extract under tack data."""
    logger.info("Fetching sale %d from OBS API", catalog_id)
    sale = fetch_sale(catalog_id)

    # Parse all hips from the raw API response
    # We need the raw data, so re-fetch
    from src.scrapers.obs.catalog import _get_session, _request_with_retry, API_BASE

    session = _get_session()
    url = f"{API_BASE}/horse-sales/{catalog_id}"
    raw_data = _request_with_retry(session, url)

    # Extract under tack metadata
    ut_meta = _extract_ut_meta(raw_data.get("sale_meta", []))

    # Parse all hips
    all_hips = []
    hips_with_ut = []
    for hip_data in raw_data.get("sale_hip", []):
        parsed = _parse_ut_hip(hip_data)
        all_hips.append(parsed)
        if parsed["ut_time"] is not None:
            hips_with_ut.append(parsed)

    # Group hips by actual breeze date
    by_date = defaultdict(list)
    for h in hips_with_ut:
        date = h.get("ut_actual_date")
        if date:
            by_date[date].append(h)

    return {
        "sale_id": str(raw_data.get("sale_id", "")),
        "sale_name": raw_data.get("sale_name", ""),
        "sale_code": raw_data.get("sale_code", ""),
        "total_hips": len(all_hips),
        "hips_with_ut": len(hips_with_ut),
        "ut_dates": sorted(by_date.keys()),
        "hips_by_date": dict(by_date),
        "all_ut_hips": hips_with_ut,
        "ut_meta": ut_meta,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }


def save_under_tack_data(sale_key: str, ut_data: dict) -> list[Path]:
    """Save under tack data to local files."""
    sale_dir = DATA_DIR / sale_key
    daily_dir = sale_dir / "daily"
    daily_dir.mkdir(parents=True, exist_ok=True)

    saved = []

    # Save daily files (one per breeze date)
    for date, hips in ut_data["hips_by_date"].items():
        # Normalize date for filename (MM/DD/YYYY -> YYYY-MM-DD)
        try:
            dt = datetime.strptime(date, "%m/%d/%Y")
            date_str = dt.strftime("%Y-%m-%d")
        except ValueError:
            date_str = date.replace("/", "-")

        daily_path = daily_dir / f"{date_str}.json"
        daily_data = {
            "sale_key": sale_key,
            "sale_name": ut_data["sale_name"],
            "date": date,
            "date_iso": date_str,
            "hip_count": len(hips),
            "hips": sorted(hips, key=lambda h: h["hip_number"]),
            "fetched_at": ut_data["fetched_at"],
        }
        with open(daily_path, "w") as f:
            json.dump(daily_data, f, indent=2, cls=DecimalEncoder)
        saved.append(daily_path)
        logger.info("Saved daily: %s (%d hips)", daily_path, len(hips))

    # Save latest.json (all hips with UT times)
    latest_path = sale_dir / "latest.json"
    latest_data = {
        "sale_key": sale_key,
        "sale_name": ut_data["sale_name"],
        "sale_code": ut_data["sale_code"],
        "total_cataloged": ut_data["total_hips"],
        "total_breezed": ut_data["hips_with_ut"],
        "ut_dates": ut_data["ut_dates"],
        "hips": sorted(ut_data["all_ut_hips"], key=lambda h: h["hip_number"]),
        "fetched_at": ut_data["fetched_at"],
    }
    with open(latest_path, "w") as f:
        json.dump(latest_data, f, indent=2, cls=DecimalEncoder)
    saved.append(latest_path)
    logger.info("Saved latest: %s (%d hips)", latest_path, ut_data["hips_with_ut"])

    # Save videos.json (UT show videos and PDF links)
    videos_path = sale_dir / "videos.json"
    videos_data = {
        "sale_key": sale_key,
        "sale_name": ut_data["sale_name"],
        "videos": ut_data["ut_meta"]["videos"],
        "links": ut_data["ut_meta"]["links"],
        "sessions": ut_data["ut_meta"]["sessions"],
        "fetched_at": ut_data["fetched_at"],
    }
    with open(videos_path, "w") as f:
        json.dump(videos_data, f, indent=2, cls=DecimalEncoder)
    saved.append(videos_path)
    logger.info("Saved videos: %s", videos_path)

    return saved


def upload_to_s3(sale_key: str, ut_data: dict) -> None:
    """Upload under tack data to S3 if credentials are available."""
    access_key = os.environ.get("BREEZEUP_AWS_ACCESS_KEY_ID")
    secret_key = os.environ.get("BREEZEUP_AWS_SECRET_ACCESS_KEY")

    if not access_key or not secret_key:
        logger.info("No AWS credentials found, skipping S3 upload")
        return

    # Import S3 upload from sync_to_s3
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from sync_to_s3 import s3_put

    # Upload latest.json
    latest_data = {
        "sale_key": sale_key,
        "sale_name": ut_data["sale_name"],
        "sale_code": ut_data["sale_code"],
        "total_cataloged": ut_data["total_hips"],
        "total_breezed": ut_data["hips_with_ut"],
        "ut_dates": ut_data["ut_dates"],
        "hips": sorted(ut_data["all_ut_hips"], key=lambda h: h["hip_number"]),
        "fetched_at": ut_data["fetched_at"],
    }
    s3_put(
        f"data/{sale_key}/under-tack/latest.json",
        json.dumps(latest_data, cls=DecimalEncoder, indent=2).encode(),
    )

    # Upload daily files
    for date, hips in ut_data["hips_by_date"].items():
        try:
            dt = datetime.strptime(date, "%m/%d/%Y")
            date_str = dt.strftime("%Y-%m-%d")
        except ValueError:
            date_str = date.replace("/", "-")

        daily_data = {
            "sale_key": sale_key,
            "sale_name": ut_data["sale_name"],
            "date": date,
            "date_iso": date_str,
            "hip_count": len(hips),
            "hips": sorted(hips, key=lambda h: h["hip_number"]),
            "fetched_at": ut_data["fetched_at"],
        }
        s3_put(
            f"data/{sale_key}/under-tack/daily/{date_str}.json",
            json.dumps(daily_data, cls=DecimalEncoder, indent=2).encode(),
        )

    # Upload videos.json
    videos_data = {
        "sale_key": sale_key,
        "sale_name": ut_data["sale_name"],
        "videos": ut_data["ut_meta"]["videos"],
        "links": ut_data["ut_meta"]["links"],
        "sessions": ut_data["ut_meta"]["sessions"],
        "fetched_at": ut_data["fetched_at"],
    }
    s3_put(
        f"data/{sale_key}/under-tack/videos.json",
        json.dumps(videos_data, cls=DecimalEncoder, indent=2).encode(),
    )

    logger.info("S3 upload complete for %s", sale_key)


def find_active_sale() -> tuple[str, int] | None:
    """Find the most likely currently active sale (closest to today)."""
    from src.scrapers.obs.catalog import fetch_upcoming_sales

    try:
        upcoming = fetch_upcoming_sales()
        if upcoming:
            sale = upcoming[0]
            sale_id = int(sale["sale_id"])
            # Find the matching sale_key
            for key, cid in OBS_CATALOG_IDS.items():
                if cid == sale_id:
                    return key, sale_id
            # Not in config yet, use generic key
            return f"obs_sale_{sale_id}", sale_id
    except Exception as e:
        logger.warning("Could not fetch upcoming sales: %s", e)

    # Fallback: use the most recent configured sale
    current_year_sales = {
        k: v for k, v in OBS_CATALOG_IDS.items() if "2026" in k
    }
    if current_year_sales:
        # Pick the one with the highest catalog ID (most recent)
        key = max(current_year_sales, key=lambda k: current_year_sales[k])
        return key, current_year_sales[key]

    return None


def main():
    args = sys.argv[1:]

    sale_key = None
    catalog_id = None

    if "--sale-id" in args:
        idx = args.index("--sale-id")
        if idx + 1 < len(args):
            catalog_id = int(args[idx + 1])
            for key, cid in OBS_CATALOG_IDS.items():
                if cid == catalog_id:
                    sale_key = key
                    break
            if not sale_key:
                sale_key = f"obs_sale_{catalog_id}"
    elif args and not args[0].startswith("-"):
        sale_key = args[0]
        catalog_id = OBS_CATALOG_IDS.get(sale_key)
        if catalog_id is None:
            logger.error("Unknown sale key: %s", sale_key)
            sys.exit(1)
    else:
        result = find_active_sale()
        if result is None:
            logger.error("No active sale found")
            sys.exit(1)
        sale_key, catalog_id = result

    logger.info("Syncing Under Tack data: %s (catalog_id=%d)", sale_key, catalog_id)

    # Fetch data
    ut_data = fetch_under_tack_data(catalog_id)
    logger.info(
        "Fetched: %d/%d hips have UT times across %d dates",
        ut_data["hips_with_ut"],
        ut_data["total_hips"],
        len(ut_data["ut_dates"]),
    )

    # Save locally
    saved_files = save_under_tack_data(sale_key, ut_data)
    logger.info("Saved %d local files", len(saved_files))

    # Upload to S3
    upload_to_s3(sale_key, ut_data)

    # Also trigger the regular sale sync to update sale.json with latest UT times
    logger.info("Also syncing full sale data for %s", sale_key)
    from sync_to_s3 import sync_sale
    try:
        sync_sale(sale_key)
    except Exception as e:
        logger.warning("Full sale sync failed (non-fatal): %s", e)

    # Summary
    print(f"\nUnder Tack Sync Complete: {sale_key}")
    print(f"  Sale: {ut_data['sale_name']}")
    print(f"  Total cataloged: {ut_data['total_hips']}")
    print(f"  Breezed so far: {ut_data['hips_with_ut']}")
    print(f"  Breeze dates: {', '.join(ut_data['ut_dates'])}")
    print(f"  UT Videos: {len(ut_data['ut_meta']['videos'])}")
    print(f"  UT Links/PDFs: {len(ut_data['ut_meta']['links'])}")
    print(f"  Local files: {DATA_DIR / sale_key}/")


if __name__ == "__main__":
    main()
