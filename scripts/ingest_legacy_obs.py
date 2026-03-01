#!/usr/bin/env python3
"""Batch-ingest all legacy OBS sales (2018-2023) from obscatalog.com.

Fetches arrData from each results page, parses into OBSSale/OBSHip, and
ingests into the database using the standard pipeline.

Usage:
    python scripts/ingest_legacy_obs.py                     # All 18 sales
    python scripts/ingest_legacy_obs.py obs_march_2022      # Single sale
    python scripts/ingest_legacy_obs.py --year 2022         # All 2022 sales
    python scripts/ingest_legacy_obs.py --dry-run           # Preview only
"""

import argparse
import logging
import sys
import time

sys.path.insert(0, ".")

from src.db import create_tables, get_engine, get_session_factory
from src.scrapers.obs.ingest import ingest_sale
from src.scrapers.obs.legacy_catalog import LEGACY_SALES, fetch_legacy_sale


def main():
    parser = argparse.ArgumentParser(description="Ingest legacy OBS sales (2018-2023)")
    parser.add_argument("sale_keys", nargs="*", help="Specific sale keys to ingest")
    parser.add_argument("--year", type=int, help="Only ingest sales from this year")
    parser.add_argument("--dry-run", action="store_true", help="Preview only")
    parser.add_argument("--db-url", default=None)
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-8s %(message)s",
    )
    if not args.verbose:
        logging.getLogger("sqlalchemy").setLevel(logging.WARNING)

    # Determine which sales to process
    if args.sale_keys:
        sale_keys = args.sale_keys
    elif args.year:
        sale_keys = [k for k, v in LEGACY_SALES.items() if v["year"] == args.year]
    else:
        sale_keys = sorted(LEGACY_SALES.keys())

    print(f"Will ingest {len(sale_keys)} legacy sales\n")

    if not args.dry_run:
        engine = get_engine(url=args.db_url)
        create_tables(engine)
        SessionFactory = get_session_factory(engine)

    total_lots = 0
    total_sold = 0
    total_gross = 0

    for sale_key in sale_keys:
        if sale_key not in LEGACY_SALES:
            print(f"  SKIP: unknown key '{sale_key}'")
            continue

        meta = LEGACY_SALES[sale_key]
        print(f"--- {sale_key} ({meta['sale_name']}) ---")

        try:
            obs_sale = fetch_legacy_sale(sale_key)
        except Exception as e:
            print(f"  FAILED to fetch: {e}")
            continue

        sold = sum(1 for h in obs_sale.hips if h.sale_status == "sold")
        with_ut = sum(1 for h in obs_sale.hips if h.under_tack_time is not None)
        prices = [h.sale_price for h in obs_sale.hips if h.sale_price]
        gross = sum(prices)

        print(f"  {len(obs_sale.hips)} hips, {sold} sold, {with_ut} with UT, gross ${gross:,}")
        total_lots += len(obs_sale.hips)
        total_sold += sold
        total_gross += gross

        if not args.dry_run:
            with SessionFactory() as db:
                sale = ingest_sale(obs_sale, db)
                print(f"  -> Ingested as {sale.sale_id}")

        time.sleep(2)

    print(f"\n{'='*50}")
    print(f"Total: {total_lots} lots, {total_sold} sold, gross ${total_gross:,}")


if __name__ == "__main__":
    main()
