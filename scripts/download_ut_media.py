#!/usr/bin/env python3
"""Download all media (breeze, walk, pedigree) for horses with under-tack times.

Streams files to S3 and deletes locally to conserve disk space.

Usage:
    python scripts/download_ut_media.py obs_march_2024
    python scripts/download_ut_media.py --all-2024
    python scripts/download_ut_media.py --all
"""

import argparse
import hashlib
import logging
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, ".")

from src.config import S3_BUCKET, USER_AGENT
from src.db import get_engine, get_session_factory
from src.models import Asset, Lot
from src.storage import get_s3_client, s3_key_for_asset, upload_file

logger = logging.getLogger(__name__)

DATA_ROOT = Path("data/videos")

SUFFIX_MAP = {
    "breeze_video": ".mp4",
    "walk_video": "w.mp4",
    "photo": "p.jpg",
    "pedigree_page": ".pdf",
}

ASSET_TYPES = ["breeze_video", "walk_video", "pedigree_page", "photo"]


def download_and_upload(asset, sale_id, hip_number, http_session, s3_client):
    """Download a single asset, upload to S3, delete local. Returns bytes or 0."""
    if not asset.source_url:
        return 0

    suffix = SUFFIX_MAP.get(asset.asset_type, "")
    local_path = DATA_ROOT / sale_id / f"{hip_number}{suffix}"
    local_path.parent.mkdir(parents=True, exist_ok=True)

    # Already on S3?
    if asset.s3_key:
        return 0

    try:
        resp = http_session.get(asset.source_url, timeout=120, stream=True)
        resp.raise_for_status()

        md5 = hashlib.md5()
        size = 0
        with open(local_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=65536):
                f.write(chunk)
                md5.update(chunk)
                size += len(chunk)

        # Upload to S3
        s3_key = s3_key_for_asset(sale_id, str(local_path))
        if upload_file(str(local_path), s3_key, s3_client=s3_client):
            asset.local_path = str(local_path)
            asset.file_size = size
            asset.checksum = md5.hexdigest()
            asset.downloaded_at = datetime.utcnow()
            asset.s3_key = s3_key
            asset.uploaded_at = datetime.utcnow()

            # Delete local
            local_path.unlink(missing_ok=True)
            asset.local_path = None
            return size
        else:
            local_path.unlink(missing_ok=True)
            return 0

    except Exception as e:
        logger.error("Failed %s hip %s %s: %s", sale_id, hip_number, asset.asset_type, e)
        if local_path.exists():
            local_path.unlink(missing_ok=True)
        return 0


def process_sale(sale_id, db, s3_client, delay=0.3):
    """Download all media for UT-timed horses in a sale."""
    # Get assets for lots WITH under-tack times
    assets = (
        db.query(Asset)
        .join(Asset.lot)
        .filter(Lot.sale_id == sale_id)
        .filter(Lot.under_tack_time.isnot(None))
        .filter(Asset.asset_type.in_(ASSET_TYPES))
        .filter(Asset.source_url.isnot(None))
        .filter(Asset.s3_key.is_(None))  # Not yet uploaded
        .all()
    )

    total = len(assets)
    if total == 0:
        print(f"  {sale_id}: Nothing to download (all done or no UT horses)")
        return {"downloaded": 0, "failed": 0, "bytes": 0}

    print(f"  {sale_id}: {total} assets to download")

    import requests
    http = requests.Session()
    http.headers.update({"User-Agent": USER_AGENT})

    stats = {"downloaded": 0, "failed": 0, "bytes": 0}
    start = time.time()

    for i, asset in enumerate(assets, 1):
        lot = asset.lot
        size = download_and_upload(asset, sale_id, lot.hip_number, http, s3_client)

        if size > 0:
            stats["downloaded"] += 1
            stats["bytes"] += size
            db.commit()
        elif asset.source_url and not asset.s3_key:
            stats["failed"] += 1

        # Progress
        if i % 10 == 0 or i == total:
            elapsed = time.time() - start
            mb = stats["bytes"] / 1024 / 1024
            rate = mb / elapsed * 60 if elapsed > 0 else 0
            pct = i / total * 100
            print(f"\r  [{i}/{total}] {pct:.0f}%  {stats['downloaded']} done  "
                  f"{mb:.0f} MB  {rate:.0f} MB/min  "
                  f"{stats['failed']} failed   ", end="", flush=True)

        time.sleep(delay)

    print()
    db.commit()
    return stats


def main():
    parser = argparse.ArgumentParser(description="Download UT-horse media to S3")
    parser.add_argument("sale_ids", nargs="*", help="Sale IDs to process")
    parser.add_argument("--all", action="store_true", help="Process all 2024+2025 sales")
    parser.add_argument("--delay", type=float, default=0.3)
    parser.add_argument("--db-url", default=None)
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-8s %(message)s",
    )
    if not args.verbose:
        logging.getLogger("sqlalchemy").setLevel(logging.WARNING)

    if args.all:
        sale_ids = [
            "obs_march_2024", "obs_spring_2024", "obs_june_2024",
            "obs_june_2025",
        ]
    elif args.sale_ids:
        sale_ids = args.sale_ids
    else:
        parser.error("Provide sale_ids or --all")

    engine = get_engine(url=args.db_url)
    SF = get_session_factory(engine)
    s3 = get_s3_client()

    grand_total = {"downloaded": 0, "failed": 0, "bytes": 0}

    for sid in sale_ids:
        print(f"\n{'='*50}")
        print(f"Processing: {sid}")
        with SF() as db:
            stats = process_sale(sid, db, s3, delay=args.delay)
            for k in grand_total:
                grand_total[k] += stats[k]

    gb = grand_total["bytes"] / 1024**3
    print(f"\n{'='*50}")
    print(f"TOTAL: {grand_total['downloaded']} files, {gb:.1f} GB to S3, {grand_total['failed']} failed")


if __name__ == "__main__":
    main()
