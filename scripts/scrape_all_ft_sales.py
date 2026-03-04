#!/usr/bin/env python3
"""Scrape all Fasig-Tipton 2YO breeze-up sale results and store as JSON.

Uses the Fasig-Tipton Django REST API at:
    https://www.fasigtipton.com/django/api

Output: data/sales/{sale_key}.json  (one file per sale)

Each JSON file contains:
  {
    "sale_id": "ft_midlantic_2025",
    "sale_name": "Fasig-Tipton Midlantic May 2YO 2025",
    "year": 2025,
    "source": "ft_api",
    "source_url": "https://www.fasigtipton.com/2025/Midlantic-2YO-Sale",
    "hip_count": 586,
    "hips": [ { hip_number, sire, dam, dam_sire, sex, colour, ... }, ... ]
  }

Usage:
    python scripts/scrape_all_ft_sales.py                    # scrape all configured FT sales
    python scripts/scrape_all_ft_sales.py ft_midlantic_2025  # scrape one sale
"""

import json
import logging
import sys
import time
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path

# Allow running from project root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import FT_CATALOG_IDS, REQUEST_DELAY_SECONDS
from src.scrapers.fasig_tipton.catalog import FTHip, FTSale, fetch_sale

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "sales"


class DecimalEncoder(json.JSONEncoder):
    """JSON encoder that handles Decimal values."""
    def default(self, o):
        if isinstance(o, Decimal):
            return float(o)
        return super().default(o)


def hip_to_dict(hip: FTHip) -> dict:
    """Convert an FTHip to a JSON-serializable dict."""
    d = asdict(hip)
    if d.get("under_tack_time") is not None:
        d["under_tack_time"] = float(d["under_tack_time"])
    return d


def scrape_ft_sale(sale_key: str, meta: dict) -> dict:
    """Scrape a sale using the Fasig-Tipton Django API."""
    logger.info("Scraping FT sale: %s (%s)", sale_key, meta["sale_identifier"])
    sale = fetch_sale(
        sale_identifier=meta["sale_identifier"],
        sale_key=sale_key,
    )

    return {
        "sale_id": sale_key,
        "sale_name": meta["display_name"],
        "sale_code": meta["sale_identifier"],
        "year": meta["year"],
        "source": "ft_api",
        "source_url": meta["source_url"],
        "start_date": sale.start_date,
        "end_date": None,
        "location": meta.get("location"),
        "hip_count": len(sale.hips),
        "hips": [hip_to_dict(h) for h in sale.hips],
    }


def save_sale(sale_data: dict, output_dir: Path) -> Path:
    """Write sale data to a JSON file."""
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{sale_data['sale_id']}.json"
    with open(path, "w") as f:
        json.dump(sale_data, f, indent=2, cls=DecimalEncoder)
    logger.info("Saved %s (%d hips) -> %s", sale_data["sale_id"], sale_data["hip_count"], path)
    return path


def main():
    """Scrape all configured Fasig-Tipton sales and save to data/sales/."""
    output_dir = DATA_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    # Determine which sales to scrape
    args = sys.argv[1:]
    if args:
        # Scrape specific sales
        sales_to_scrape = {k: v for k, v in FT_CATALOG_IDS.items() if k in args}
        unknown = [k for k in args if k not in FT_CATALOG_IDS]
        if unknown:
            logger.error("Unknown sale key(s): %s", unknown)
            logger.info("Available: %s", list(FT_CATALOG_IDS.keys()))
    else:
        sales_to_scrape = FT_CATALOG_IDS

    total = len(sales_to_scrape)
    logger.info("Will scrape %d Fasig-Tipton sale(s)", total)

    results = []
    errors = []

    for sale_key, meta in sorted(sales_to_scrape.items()):
        try:
            sale_data = scrape_ft_sale(sale_key, meta)
            save_sale(sale_data, output_dir)
            results.append((sale_key, sale_data["hip_count"]))
        except Exception as e:
            logger.error("Failed to scrape %s: %s", sale_key, e, exc_info=True)
            errors.append((sale_key, str(e)))
        time.sleep(REQUEST_DELAY_SECONDS)

    # Summary
    print("\n" + "=" * 60)
    print("FASIG-TIPTON SCRAPE SUMMARY")
    print("=" * 60)
    for sale_key, hip_count in sorted(results):
        print(f"  + {sale_key}: {hip_count} hips")
    if errors:
        print(f"\n  ERRORS ({len(errors)}):")
        for sale_key, err in errors:
            print(f"  x {sale_key}: {err}")
    print(f"\nTotal: {len(results)} succeeded, {len(errors)} failed")
    print(f"Output: {output_dir}/")

    return len(errors) == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
