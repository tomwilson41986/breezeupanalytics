#!/usr/bin/env python3
"""Upload pipeline output files to S3.

Usage:
    # Upload a specific hip's output to S3 keypoint folder:
    python scripts/upload_to_s3.py output/hip654 --prefix keypoint/hip654

    # Upload with explicit bucket:
    python scripts/upload_to_s3.py output/hip654 --bucket my-bucket --prefix keypoint/hip654

    # Upload all output directories:
    python scripts/upload_to_s3.py output/ --prefix keypoint --recursive

Environment variables required:
    AWS_ACCESS_KEY_ID       - AWS access key
    AWS_SECRET_ACCESS_KEY   - AWS secret key
    S3_BUCKET_NAME          - S3 bucket name (or use --bucket)
    AWS_DEFAULT_REGION      - AWS region (default: us-east-1)
"""

import argparse
import logging
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.storage import S3Uploader


def main() -> None:
    parser = argparse.ArgumentParser(description="Upload pipeline output to S3")
    parser.add_argument("path", help="Local directory containing pipeline output")
    parser.add_argument("--bucket", help="S3 bucket name (or set S3_BUCKET_NAME)")
    parser.add_argument("--prefix", default="keypoint", help="S3 key prefix (default: keypoint)")
    parser.add_argument("--region", help="AWS region (or set AWS_DEFAULT_REGION)")
    parser.add_argument(
        "--recursive", action="store_true",
        help="Upload all subdirectories (each becomes prefix/subdir/)",
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose logging")

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    local_path = Path(args.path)
    if not local_path.exists():
        print(f"Error: path does not exist: {local_path}", file=sys.stderr)
        sys.exit(1)

    uploader = S3Uploader(
        bucket=args.bucket,
        region=args.region,
        prefix=args.prefix,
    )

    if args.recursive and local_path.is_dir():
        all_uploaded: dict[str, str] = {}
        for subdir in sorted(local_path.iterdir()):
            if subdir.is_dir():
                sub_prefix = f"{args.prefix}/{subdir.name}"
                urls = uploader.upload_pipeline_output(subdir, s3_prefix=sub_prefix)
                all_uploaded.update(urls)
        uploaded = all_uploaded
    elif local_path.is_dir():
        uploaded = uploader.upload_pipeline_output(local_path)
    else:
        url = uploader.upload_file(local_path)
        uploaded = {local_path.name: url}

    print(f"\nUploaded {len(uploaded)} file(s):")
    for name, url in uploaded.items():
        print(f"  {name}: {url}")


if __name__ == "__main__":
    main()
