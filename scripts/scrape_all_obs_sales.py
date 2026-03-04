#!/usr/bin/env python3
"""Scrape all OBS 2YO breeze-up sale results and store as JSON.

Covers:
  - 2024 sales via the WordPress REST API (obssales.com catalog IDs 135-137)
  - 2018-2023 sales via legacy HTML pages (obscatalog.com)

Output: data/sales/{sale_key}.json  (one file per sale)

Each JSON file contains:
  {
    "sale_id": "obs_march_2023",
    "sale_name": "OBS March 2YO in Training 2023",
    "year": 2023,
    "source": "api" | "legacy",
    "source_url": "...",
    "hip_count": 833,
    "hips": [ { hip_number, sire, dam, dam_sire, sex, colour, ... }, ... ]
  }
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

from src.config import (
    OBS_CATALOG_IDS,
    OBS_LEGACY_RESULTS,
    REQUEST_DELAY_SECONDS,
)
from src.scrapers.obs.catalog import OBSHip, OBSSale, fetch_sale
from src.scrapers.obs.legacy_results import fetch_legacy_sale, hip_to_dict

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


def _api_hip_to_dict(hip: OBSHip) -> dict:
    """Convert an API OBSHip to a JSON-serializable dict."""
    d = asdict(hip)
    if d.get("under_tack_time") is not None:
        d["under_tack_time"] = float(d["under_tack_time"])
    return d


def scrape_api_sale(sale_key: str, catalog_id: int) -> dict:
    """Scrape a sale using the OBS WordPress REST API."""
    logger.info("Scraping API sale: %s (catalog ID %d)", sale_key, catalog_id)
    sale = fetch_sale(catalog_id)

    return {
        "sale_id": sale_key,
        "sale_name": sale.sale_name,
        "sale_code": sale.sale_code,
        "year": sale.year,
        "source": "api",
        "source_url": f"https://obssales.com/catalog/#/{catalog_id}/results",
        "start_date": sale.start_date,
        "end_date": sale.end_date,
        "hip_count": len(sale.hips),
        "hips": [_api_hip_to_dict(h) for h in sale.hips],
    }


def scrape_legacy_sale(sale_key: str, meta: dict) -> dict:
    """Scrape a sale from legacy obscatalog.com results page."""
    logger.info("Scraping legacy sale: %s (%s)", sale_key, meta["url"])
    result = fetch_legacy_sale(
        sale_key=sale_key,
        url=meta["url"],
        sale_code=meta["sale_code"],
        year=meta["year"],
    )

    return {
        "sale_id": result["sale_id"],
        "sale_name": result["sale_name"],
        "sale_code": result["sale_code"],
        "year": result["year"],
        "source": "legacy",
        "source_url": result["source_url"],
        "start_date": None,
        "end_date": None,
        "hip_count": len(result["hips"]),
        "hips": [hip_to_dict(h) for h in result["hips"]],
    }


def save_sale(sale_data: dict, output_dir: Path) -> Path:
    """Write sale data to a JSON file."""
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{sale_data['sale_id']}.json"
    with open(path, "w") as f:
        json.dump(sale_data, f, indent=2, cls=DecimalEncoder)
    logger.info("Saved %s (%d hips) → %s", sale_data["sale_id"], sale_data["hip_count"], path)
    return path


def main():
    """Scrape all configured OBS sales and save to data/sales/."""
    output_dir = DATA_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    # Determine which sales to scrape
    # Only scrape 2024 API sales (2025/2026 already handled by the live system)
    api_sales = {k: v for k, v in OBS_CATALOG_IDS.items() if "2024" in k}
    legacy_sales = OBS_LEGACY_RESULTS

    total = len(api_sales) + len(legacy_sales)
    logger.info("Will scrape %d sales (%d API, %d legacy)", total, len(api_sales), len(legacy_sales))

    results = []
    errors = []

    # 1. Scrape 2024 API sales
    for sale_key, catalog_id in sorted(api_sales.items()):
        try:
            sale_data = scrape_api_sale(sale_key, catalog_id)
            save_sale(sale_data, output_dir)
            results.append((sale_key, sale_data["hip_count"]))
        except Exception as e:
            logger.error("Failed to scrape %s: %s", sale_key, e)
            errors.append((sale_key, str(e)))
        time.sleep(REQUEST_DELAY_SECONDS)

    # 2. Scrape 2018-2023 legacy sales
    for sale_key, meta in sorted(legacy_sales.items()):
        try:
            sale_data = scrape_legacy_sale(sale_key, meta)
            save_sale(sale_data, output_dir)
            results.append((sale_key, sale_data["hip_count"]))
        except Exception as e:
            logger.error("Failed to scrape %s: %s", sale_key, e)
            errors.append((sale_key, str(e)))
        time.sleep(REQUEST_DELAY_SECONDS)

    # Summary
    print("\n" + "=" * 60)
    print("SCRAPE SUMMARY")
    print("=" * 60)
    for sale_key, hip_count in sorted(results):
        print(f"  ✓ {sale_key}: {hip_count} hips")
    if errors:
        print(f"\n  ERRORS ({len(errors)}):")
        for sale_key, err in errors:
            print(f"  ✗ {sale_key}: {err}")
    print(f"\nTotal: {len(results)} succeeded, {len(errors)} failed")
    print(f"Output: {output_dir}/")

    return len(errors) == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
