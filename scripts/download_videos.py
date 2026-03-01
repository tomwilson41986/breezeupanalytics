#!/usr/bin/env python3
"""Download breeze videos for a sale that's already been ingested.

Usage:
    python scripts/download_videos.py obs_march_2025
    python scripts/download_videos.py obs_march_2025 --delay 0.3
    python scripts/download_videos.py obs_march_2025 --force   # re-download all
"""

import argparse
import logging
import sys

sys.path.insert(0, ".")

from src.db import get_engine, get_session_factory
from src.scrapers.obs.download import download_sale_assets


def main():
    parser = argparse.ArgumentParser(description="Download breeze videos for an ingested sale")
    parser.add_argument("sale_id", help="Internal sale ID (e.g. obs_march_2025)")
    parser.add_argument("--delay", type=float, default=0.5,
                        help="Seconds between downloads (default: 0.5)")
    parser.add_argument("--force", action="store_true",
                        help="Re-download even if already present")
    parser.add_argument("--all-media", action="store_true",
                        help="Download all media types, not just breeze videos")
    parser.add_argument("--db-url", default=None)
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-8s %(message)s",
    )
    if not args.verbose:
        logging.getLogger("sqlalchemy").setLevel(logging.WARNING)

    engine = get_engine(url=args.db_url)
    SessionFactory = get_session_factory(engine)

    asset_types = None if args.all_media else ["breeze_video"]
    label = "all media" if args.all_media else "breeze videos"

    print(f"Downloading {label} for {args.sale_id}...")

    with SessionFactory() as db:
        stats = download_sale_assets(
            args.sale_id, db,
            asset_types=asset_types,
            delay=args.delay,
            force=args.force,
        )

    mb = stats.get("bytes", 0) / 1024 / 1024
    print(f"\nComplete: {stats['downloaded']} downloaded ({mb:.0f} MB), "
          f"{stats['failed']} failed, {stats['skipped']} skipped")


if __name__ == "__main__":
    main()
