#!/usr/bin/env python3
"""Sync OBS sale data to S3 as structured JSON.

Fetches live sale data from the OBS REST API, processes it through our
parser, and uploads the result as JSON files to the breezeup S3 bucket.

S3 layout:
    data/{sale_key}/sale.json    — full sale record with all hips
    data/{sale_key}/stats.json   — pre-computed aggregate statistics

Usage:
    python scripts/sync_to_s3.py                     # sync all known sales
    python scripts/sync_to_s3.py obs_march_2025      # sync one sale
    python scripts/sync_to_s3.py --discover           # discover new sale IDs

Environment variables:
    BREEZEUP_AWS_ACCESS_KEY_ID
    BREEZEUP_AWS_SECRET_ACCESS_KEY
"""

import json
import logging
import os
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from decimal import Decimal

import hashlib
import hmac
from urllib.parse import quote

import requests

# Allow running from repo root: `python scripts/sync_to_s3.py`
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pathlib import Path

from src.config import OBS_CATALOG_IDS, OBS_LEGACY_RESULTS, FT_CATALOG_IDS
from src.scrapers.obs.catalog import fetch_sale, discover_sale_ids

LOCAL_SALES_DIR = Path(__file__).resolve().parent.parent / "data" / "sales"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
)
logger = logging.getLogger("sync_to_s3")

BUCKET = "breezeup"
REGION = "eu-north-1"
HOST = f"{BUCKET}.s3.{REGION}.amazonaws.com"


# ── AWS SigV4 signing (no SDK needed) ──────────────────────────

def _hmac_sha256(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode(), hashlib.sha256).digest()


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _signing_key(secret: str, date_stamp: str) -> bytes:
    k_date = _hmac_sha256(f"AWS4{secret}".encode(), date_stamp)
    k_region = _hmac_sha256(k_date, REGION)
    k_service = _hmac_sha256(k_region, "s3")
    return _hmac_sha256(k_service, "aws4_request")


def s3_put(key: str, body: bytes, content_type: str = "application/json") -> None:
    """PUT an object to S3 using SigV4 signing."""
    access_key = os.environ["BREEZEUP_AWS_ACCESS_KEY_ID"]
    secret_key = os.environ["BREEZEUP_AWS_SECRET_ACCESS_KEY"]

    now = datetime.now(timezone.utc)
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    date_stamp = now.strftime("%Y%m%d")

    encoded_key = "/".join(quote(p, safe="") for p in key.split("/"))
    payload_hash = _sha256(body)

    canonical_headers = (
        f"content-type:{content_type}\n"
        f"host:{HOST}\n"
        f"x-amz-content-sha256:{payload_hash}\n"
        f"x-amz-date:{amz_date}\n"
    )
    signed_headers = "content-type;host;x-amz-content-sha256;x-amz-date"

    canonical_request = "\n".join([
        "PUT",
        f"/{encoded_key}",
        "",  # no query string
        canonical_headers,
        signed_headers,
        payload_hash,
    ])

    scope = f"{date_stamp}/{REGION}/s3/aws4_request"
    string_to_sign = "\n".join([
        "AWS4-HMAC-SHA256",
        amz_date,
        scope,
        _sha256(canonical_request.encode()),
    ])

    sig_key = _signing_key(secret_key, date_stamp)
    signature = hmac.new(sig_key, string_to_sign.encode(), hashlib.sha256).hexdigest()

    authorization = (
        f"AWS4-HMAC-SHA256 Credential={access_key}/{scope}, "
        f"SignedHeaders={signed_headers}, Signature={signature}"
    )

    url = f"https://{HOST}/{encoded_key}"
    resp = requests.put(
        url,
        data=body,
        headers={
            "Content-Type": content_type,
            "Host": HOST,
            "x-amz-date": amz_date,
            "x-amz-content-sha256": payload_hash,
            "Authorization": authorization,
        },
        timeout=60,
    )
    resp.raise_for_status()
    logger.info("Uploaded s3://%s/%s (%d bytes)", BUCKET, key, len(body))


# ── JSON serialisation ──────────────────────────────────────────

class DecimalEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, Decimal):
            return float(o)
        return super().default(o)


def sale_to_json(sale) -> dict:
    """Convert an OBSSale dataclass to a JSON-serialisable dict."""
    d = asdict(sale)
    d["synced_at"] = datetime.now(timezone.utc).isoformat()
    return d


def compute_stats(sale_dict: dict) -> dict:
    """Compute aggregate statistics from a sale dict."""
    hips = sale_dict.get("hips", [])

    sold = [h for h in hips if h["sale_status"] == "sold" and h["sale_price"]]
    rna = [h for h in hips if h["sale_status"] == "RNA"]
    out = [h for h in hips if h["sale_status"] == "out"]
    prices = [h["sale_price"] for h in sold]

    total_revenue = sum(prices)
    avg_price = total_revenue / len(prices) if prices else 0
    sorted_prices = sorted(prices)
    median_price = sorted_prices[len(sorted_prices) // 2] if sorted_prices else 0
    max_price = max(prices) if prices else 0

    # Sire stats
    sire_map = {}
    for h in sold:
        sire = h.get("sire") or "Unknown"
        if sire not in sire_map:
            sire_map[sire] = {"count": 0, "total": 0, "prices": []}
        sire_map[sire]["count"] += 1
        sire_map[sire]["total"] += h["sale_price"]
        sire_map[sire]["prices"].append(h["sale_price"])

    top_sires = sorted(
        [
            {
                "name": name,
                "count": s["count"],
                "avgPrice": s["total"] / s["count"],
                "totalRevenue": s["total"],
                "medianPrice": sorted(s["prices"])[len(s["prices"]) // 2],
            }
            for name, s in sire_map.items()
        ],
        key=lambda x: x["avgPrice"],
        reverse=True,
    )

    # Consignor stats
    consignor_map = {}
    for h in sold:
        c = h.get("consignor") or "Unknown"
        if c not in consignor_map:
            consignor_map[c] = {"count": 0, "total": 0}
        consignor_map[c]["count"] += 1
        consignor_map[c]["total"] += h["sale_price"]

    top_consignors = sorted(
        [
            {
                "name": name,
                "count": c["count"],
                "avgPrice": c["total"] / c["count"],
                "totalRevenue": c["total"],
            }
            for name, c in consignor_map.items()
        ],
        key=lambda x: x["totalRevenue"],
        reverse=True,
    )

    # Breeze time stats
    with_times = [h for h in hips if h.get("under_tack_time") and h.get("under_tack_distance")]
    breeze_by_distance = {}
    for h in with_times:
        dist = h["under_tack_distance"]
        if dist not in breeze_by_distance:
            breeze_by_distance[dist] = []
        breeze_by_distance[dist].append({
            "time": h["under_tack_time"],
            "price": h["sale_price"],
            "hip": h["hip_number"],
            "sire": h.get("sire"),
        })

    # Price distribution
    buckets = [
        {"label": "< $10K", "min": 0, "max": 10_000},
        {"label": "$10K-$25K", "min": 10_000, "max": 25_000},
        {"label": "$25K-$50K", "min": 25_000, "max": 50_000},
        {"label": "$50K-$100K", "min": 50_000, "max": 100_000},
        {"label": "$100K-$250K", "min": 100_000, "max": 250_000},
        {"label": "$250K-$500K", "min": 250_000, "max": 500_000},
        {"label": "$500K-$1M", "min": 500_000, "max": 1_000_000},
        {"label": "$1M+", "min": 1_000_000, "max": 1_000_000_000},
    ]
    price_distribution = [
        {**b, "count": sum(1 for p in prices if b["min"] <= p < b["max"])}
        for b in buckets
    ]

    buyback_rate = (
        (len(rna) / (len(sold) + len(rna))) * 100 if (sold or rna) else 0
    )

    return {
        "totalHips": len(hips),
        "soldCount": len(sold),
        "rnaCount": len(rna),
        "outCount": len(out),
        "totalRevenue": total_revenue,
        "avgPrice": avg_price,
        "medianPrice": median_price,
        "maxPrice": max_price,
        "buybackRate": buyback_rate,
        "topSires": top_sires[:30],
        "breezeByDistance": breeze_by_distance,
        "priceDistribution": price_distribution,
        "topConsignors": top_consignors[:30],
        "synced_at": datetime.now(timezone.utc).isoformat(),
    }


# ── Sale key mapping ────────────────────────────────────────────

# Use the canonical catalog IDs from config
SALE_MAP: dict[str, int] = dict(OBS_CATALOG_IDS)

# Legacy sales that must be synced from local JSON files (no live API)
LEGACY_SALE_KEYS: list[str] = list(OBS_LEGACY_RESULTS.keys())

# Fasig-Tipton sales (synced from local JSON files scraped via FT API)
FT_SALE_KEYS: list[str] = list(FT_CATALOG_IDS.keys())


def _upload_sale(sale_key: str, sale_dict: dict) -> None:
    """Compute stats and upload a sale dict to S3."""
    sale_json = json.dumps(sale_dict, cls=DecimalEncoder, indent=2)
    stats_dict = compute_stats(sale_dict)
    stats_json = json.dumps(stats_dict, cls=DecimalEncoder, indent=2)

    s3_put(f"data/{sale_key}/sale.json", sale_json.encode())
    s3_put(f"data/{sale_key}/stats.json", stats_json.encode())

    hip_count = len(sale_dict.get("hips", []))
    logger.info(
        "Done: %s — %d hips, %d sold, $%s total revenue",
        sale_key,
        hip_count,
        stats_dict["soldCount"],
        f"{stats_dict['totalRevenue']:,.0f}",
    )


def sync_sale(sale_key: str) -> None:
    """Fetch a sale from OBS API, process it, and upload to S3."""
    catalog_id = SALE_MAP.get(sale_key)
    if catalog_id is None:
        logger.error("Unknown API sale key: %s (known: %s)", sale_key, list(SALE_MAP.keys()))
        return

    logger.info("Syncing %s (catalog_id=%s) from OBS API", sale_key, catalog_id)
    sale = fetch_sale(catalog_id)
    sale_dict = sale_to_json(sale)
    sale_dict["synced_at"] = datetime.now(timezone.utc).isoformat()
    _upload_sale(sale_key, sale_dict)


def sync_local_sale(sale_key: str) -> None:
    """Upload a pre-scraped sale from data/sales/{sale_key}.json to S3."""
    local_path = LOCAL_SALES_DIR / f"{sale_key}.json"
    if not local_path.exists():
        logger.error(
            "Local file not found: %s — run scripts/scrape_all_obs_sales.py first",
            local_path,
        )
        return

    logger.info("Syncing %s from local file %s", sale_key, local_path)
    with open(local_path) as f:
        sale_dict = json.load(f)

    sale_dict["synced_at"] = datetime.now(timezone.utc).isoformat()
    _upload_sale(sale_key, sale_dict)


def main():
    # Verify AWS credentials
    if not os.environ.get("BREEZEUP_AWS_ACCESS_KEY_ID"):
        logger.error("BREEZEUP_AWS_ACCESS_KEY_ID not set")
        sys.exit(1)
    if not os.environ.get("BREEZEUP_AWS_SECRET_ACCESS_KEY"):
        logger.error("BREEZEUP_AWS_SECRET_ACCESS_KEY not set")
        sys.exit(1)

    args = sys.argv[1:]

    if "--discover" in args:
        logger.info("Discovering OBS sale IDs...")
        sales = discover_sale_ids()
        for s in sales:
            print(f"  {s['sale_id']}: {s['sale_name']} ({s.get('sale_starts', 'TBD')})")
        return

    if "--all" in args:
        # Sync everything: API sales + legacy local files + FT sales
        args = [k for k in args if k != "--all"]
        logger.info("Syncing ALL sales: %d API + %d legacy + %d FT",
                     len(SALE_MAP), len(LEGACY_SALE_KEYS), len(FT_SALE_KEYS))
        for key in sorted(SALE_MAP):
            sync_sale(key)
        for key in sorted(LEGACY_SALE_KEYS):
            sync_local_sale(key)
        for key in sorted(FT_SALE_KEYS):
            sync_local_sale(key)
        return

    if args:
        # Sync specific sales (auto-detect API vs local)
        for key in args:
            if key in SALE_MAP:
                sync_sale(key)
            elif (LOCAL_SALES_DIR / f"{key}.json").exists():
                sync_local_sale(key)
            else:
                logger.error("Unknown sale: %s (not in API map or local files)", key)
    else:
        # Default: sync API-based sales only (same as before)
        for key in SALE_MAP:
            sync_sale(key)


if __name__ == "__main__":
    main()
