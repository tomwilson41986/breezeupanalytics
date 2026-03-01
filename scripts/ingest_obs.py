#!/usr/bin/env python3
"""Ingest an OBS sale: fetch from API, populate DB, optionally download media.

Usage:
    python scripts/ingest_obs.py 142                  # Ingest 2025 March sale
    python scripts/ingest_obs.py 142 --download       # Also download breeze videos
    python scripts/ingest_obs.py 142 --download-all   # Download all media types
    python scripts/ingest_obs.py 142 --dry-run        # Preview without writing to DB
"""

import argparse
import logging
import sys

sys.path.insert(0, ".")

from src.db import create_tables, get_engine, get_session_factory
from src.scrapers.obs.catalog import fetch_sale
from src.scrapers.obs.download import download_sale_assets
from src.scrapers.obs.ingest import ingest_sale


def main():
    parser = argparse.ArgumentParser(description="Ingest an OBS sale into the database")
    parser.add_argument("sale_id", help="OBS catalog sale ID (e.g. 142)")
    parser.add_argument("--download", action="store_true",
                        help="Download breeze videos after ingesting")
    parser.add_argument("--download-all", action="store_true",
                        help="Download all media (videos, photos, PDFs)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Fetch and parse but don't write to DB")
    parser.add_argument("--db-url", default=None,
                        help="Database URL (default: SQLite fallback)")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    )

    # Fetch from API
    print(f"Fetching sale {args.sale_id} from OBS API...")
    obs_sale = fetch_sale(args.sale_id)
    print(f"  Sale: {obs_sale.sale_name}")
    print(f"  Year: {obs_sale.year}")
    print(f"  Hips: {len(obs_sale.hips)}")

    # Summarize
    sold = sum(1 for h in obs_sale.hips if h.sale_status == "sold")
    rna = sum(1 for h in obs_sale.hips if h.sale_status == "RNA")
    outs = sum(1 for h in obs_sale.hips if h.sale_status == "out")
    pending = sum(1 for h in obs_sale.hips if h.sale_status == "pending")
    with_video = sum(1 for h in obs_sale.hips if h.has_video)
    with_ut = sum(1 for h in obs_sale.hips if h.under_tack_time is not None)
    print(f"  Sold: {sold}, RNA: {rna}, Out: {outs}, Pending: {pending}")
    print(f"  With breeze video: {with_video}")
    print(f"  With UT time: {with_ut}")

    if sold > 0:
        prices = [h.sale_price for h in obs_sale.hips if h.sale_price]
        if prices:
            print(f"  Price range: ${min(prices):,} - ${max(prices):,}")
            print(f"  Average: ${sum(prices) // len(prices):,}")
            print(f"  Gross: ${sum(prices):,}")

    if args.dry_run:
        print("\nDry run — no database writes.")
        return

    # Init DB and ingest
    engine = get_engine(url=args.db_url)
    create_tables(engine)
    SessionFactory = get_session_factory(engine)

    with SessionFactory() as db:
        sale = ingest_sale(obs_sale, db)
        print(f"\nIngested as: {sale.sale_id}")
        print(f"  Lots in DB: {len(sale.lots)}")

        # Download media if requested
        if args.download or args.download_all:
            asset_types = None if args.download_all else ["breeze_video"]
            print(f"\nDownloading {'all media' if args.download_all else 'breeze videos'}...")
            stats = download_sale_assets(sale.sale_id, db, asset_types=asset_types)
            print(f"  Downloaded: {stats['downloaded']}")
            print(f"  Skipped: {stats['skipped']}")

    print("\nDone.")


if __name__ == "__main__":
    main()
