#!/usr/bin/env python3
"""Batch-ingest all known OBS sales into the database.

Usage:
    python scripts/ingest_all_obs.py              # Ingest 2yo sales only
    python scripts/ingest_all_obs.py --all         # Ingest all sale categories
    python scripts/ingest_all_obs.py --dry-run     # Preview only
"""

import argparse
import logging
import sys
import time

sys.path.insert(0, ".")

from src.db import create_tables, get_engine, get_session_factory
from src.scrapers.obs.catalog import fetch_sale
from src.scrapers.obs.ingest import ingest_sale

# All known OBS sale IDs discovered via API probing (2026-03-01)
ALL_SALES = [
    # 2023
    {"id": 130, "name": "2023 March 2YO", "cat": "2yo"},
    {"id": 131, "name": "2023 Spring 2YO", "cat": "2yo"},
    {"id": 132, "name": "2023 June 2YO & HRA", "cat": "2yo"},
    {"id": 133, "name": "2023 October Yearling", "cat": "yearling"},
    {"id": 129, "name": "2023 Winter Mixed", "cat": "mixed"},
    # 2024
    {"id": 134, "name": "2024 Winter Mixed", "cat": "mixed"},
    {"id": 135, "name": "2024 March 2YO", "cat": "2yo"},
    {"id": 136, "name": "2024 Spring 2YO", "cat": "2yo"},
    {"id": 137, "name": "2024 June 2YO & HRA", "cat": "2yo"},
    {"id": 138, "name": "2024 October Yearling", "cat": "yearling"},
    # 2025
    {"id": 140, "name": "2025 Winter Mixed", "cat": "mixed"},
    {"id": 142, "name": "2025 March 2YO", "cat": "2yo"},
    {"id": 144, "name": "2025 Spring 2YO", "cat": "2yo"},
    {"id": 145, "name": "2025 June 2YO & HRA", "cat": "2yo"},
    {"id": 146, "name": "2025 October Yearling", "cat": "yearling"},
    # 2026
    {"id": 147, "name": "2026 Winter Mixed", "cat": "mixed"},
    {"id": 149, "name": "2026 March 2YO", "cat": "2yo"},
]


def main():
    parser = argparse.ArgumentParser(description="Batch-ingest OBS sales")
    parser.add_argument("--all", action="store_true",
                        help="Include mixed/yearling sales (default: 2yo only)")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--db-url", default=None)
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-8s %(message)s",
    )
    # Quiet down SQLAlchemy unless verbose
    if not args.verbose:
        logging.getLogger("sqlalchemy").setLevel(logging.WARNING)

    sales_to_ingest = ALL_SALES if args.all else [s for s in ALL_SALES if s["cat"] == "2yo"]
    print(f"Will ingest {len(sales_to_ingest)} sales\n")

    if not args.dry_run:
        engine = get_engine(url=args.db_url)
        create_tables(engine)
        SessionFactory = get_session_factory(engine)

    total_lots = 0
    total_sold = 0
    total_gross = 0

    for entry in sales_to_ingest:
        sid = entry["id"]
        print(f"--- {entry['name']} (ID {sid}) ---")

        try:
            obs_sale = fetch_sale(sid)
        except Exception as e:
            print(f"  FAILED to fetch: {e}")
            continue

        sold = sum(1 for h in obs_sale.hips if h.sale_status == "sold")
        prices = [h.sale_price for h in obs_sale.hips if h.sale_price]
        gross = sum(prices)

        print(f"  {obs_sale.sale_name}: {len(obs_sale.hips)} hips, {sold} sold, gross ${gross:,}")
        total_lots += len(obs_sale.hips)
        total_sold += sold
        total_gross += gross

        if not args.dry_run:
            with SessionFactory() as db:
                sale = ingest_sale(obs_sale, db)
                print(f"  -> Ingested as {sale.sale_id}")

        time.sleep(2)  # Be polite between sales

    print(f"\n{'='*50}")
    print(f"Total: {total_lots} lots, {total_sold} sold, gross ${total_gross:,}")


if __name__ == "__main__":
    main()
