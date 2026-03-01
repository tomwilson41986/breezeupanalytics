#!/usr/bin/env python3
"""Upload downloaded videos to S3 for a sale.

Usage:
    python scripts/upload_to_s3.py obs_march_2025
    python scripts/upload_to_s3.py obs_march_2025 --bucket my-bucket
    python scripts/upload_to_s3.py obs_march_2025 --delete-local  # remove after upload

Requires AWS credentials via env vars or ~/.aws/credentials:
    export AWS_ACCESS_KEY_ID=...
    export AWS_SECRET_ACCESS_KEY=...
    export S3_BUCKET=breezeup-media
"""

import argparse
import logging
import sys

sys.path.insert(0, ".")

from src.db import get_engine, get_session_factory
from src.storage import upload_sale_assets


def main():
    parser = argparse.ArgumentParser(description="Upload sale videos to S3")
    parser.add_argument("sale_id", help="Internal sale ID (e.g. obs_march_2025)")
    parser.add_argument("--bucket", default=None,
                        help="S3 bucket (default: from S3_BUCKET env var)")
    parser.add_argument("--delete-local", action="store_true",
                        help="Delete local files after successful upload")
    parser.add_argument("--all-media", action="store_true",
                        help="Upload all media types, not just breeze videos")
    parser.add_argument("--db-url", default=None)
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-8s %(message)s",
    )
    if not args.verbose:
        logging.getLogger("sqlalchemy").setLevel(logging.WARNING)
        logging.getLogger("botocore").setLevel(logging.WARNING)

    engine = get_engine(url=args.db_url)
    SessionFactory = get_session_factory(engine)

    asset_types = None if args.all_media else ["breeze_video"]
    kwargs = {}
    if args.bucket:
        kwargs["bucket"] = args.bucket

    print(f"Uploading videos for {args.sale_id} to S3...")

    with SessionFactory() as db:
        stats = upload_sale_assets(
            args.sale_id, db,
            asset_types=asset_types,
            delete_local=args.delete_local,
            **kwargs,
        )

    mb = stats.get("bytes", 0) / 1024 / 1024
    print(f"\nComplete: {stats['uploaded']} uploaded ({mb:.0f} MB), "
          f"{stats['failed']} failed")


if __name__ == "__main__":
    main()
