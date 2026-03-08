#!/usr/bin/env python3
"""Upload live sale detailed times CSV to S3.

Reads a CSV of detailed breeze times and uploads as JSON to S3
so the frontend can display it on hip profile and sale pages.

Usage:
    python scripts/upload_live_sale_times.py data/obs_march_2026_times.csv --sale obs_march_2026
    python scripts/upload_live_sale_times.py data/obs_march_2026_times.csv --sale obs_march_2026 --dry-run

Expected CSV columns (flexible — auto-detected):
    Hip (or Hip #, Hip Number)
    Distance (e.g. "1/8", "1/4", "3/8")
    Time (in seconds, e.g. 10.1, 21.2)
    Any additional columns are preserved as-is (e.g. gallop out, splits, etc.)

Environment variables required:
    BREEZEUP_AWS_ACCESS_KEY_ID     - AWS access key
    BREEZEUP_AWS_SECRET_ACCESS_KEY - AWS secret key
"""

import argparse
import csv
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logger = logging.getLogger(__name__)


def normalize_header(header: str) -> str:
    """Normalize CSV header to a consistent snake_case key."""
    h = header.strip().lower()
    # Remove special characters, replace spaces with underscores
    h = h.replace("#", "").replace("(", "").replace(")", "").replace("/", "")
    h = h.replace(" ", "_")
    # Collapse multiple underscores and strip trailing/leading underscores
    while "__" in h:
        h = h.replace("__", "_")
    h = h.strip("_")
    # Common aliases
    aliases = {
        "hip": "hip_number",
        "hip_number": "hip_number",
        "hipnumber": "hip_number",
        "hipno": "hip_number",
        "hip_no": "hip_number",
    }
    return aliases.get(h, h)


def parse_number(value: str):
    """Parse a string to int or float, returning None if empty/invalid."""
    value = value.strip()
    if not value or value == "-" or value == "—":
        return None
    try:
        # Try int first
        if "." not in value:
            return int(value)
        return float(value)
    except ValueError:
        return value  # Keep as string if not numeric


def parse_csv(csv_path: str) -> list[dict]:
    """Parse the detailed times CSV into a list of hip records."""
    records = []
    with open(csv_path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        raw_headers = reader.fieldnames or []
        header_map = {h: normalize_header(h) for h in raw_headers}

        for row in reader:
            record = {}
            for raw_key, normalized_key in header_map.items():
                record[normalized_key] = parse_number(row[raw_key])
            records.append(record)

    logger.info("Parsed %d records from %s", len(records), csv_path)
    logger.info("Columns: %s", list(header_map.values()))
    return records


def build_times_json(records: list[dict], sale_key: str) -> dict:
    """Build the JSON structure for S3 upload."""
    # Group by hip number
    by_hip = {}
    for rec in records:
        hip = rec.get("hip_number")
        if hip is None:
            continue
        hip_key = str(int(hip)) if isinstance(hip, (int, float)) else str(hip)
        by_hip[hip_key] = {k: v for k, v in rec.items()}

    return {
        "sale_key": sale_key,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "count": len(by_hip),
        "columns": list(records[0].keys()) if records else [],
        "hips": by_hip,
    }


def upload_to_s3(data: dict, sale_key: str) -> None:
    """Upload the times JSON to S3."""
    try:
        import hashlib
        import hmac
        from urllib.request import Request, urlopen

        bucket = "breezeup"
        region = "eu-north-1"
        host = f"{bucket}.s3.{region}.amazonaws.com"
        s3_key = f"data/{sale_key}/live-sale-times.json"

        access_key = os.environ["BREEZEUP_AWS_ACCESS_KEY_ID"]
        secret_key = os.environ["BREEZEUP_AWS_SECRET_ACCESS_KEY"]

        body = json.dumps(data, indent=2).encode("utf-8")

        now = datetime.now(timezone.utc)
        amz_date = now.strftime("%Y%m%dT%H%M%SZ")
        date_stamp = now.strftime("%Y%m%d")

        payload_hash = hashlib.sha256(body).hexdigest()
        encoded_key = "/".join(
            __import__("urllib.parse", fromlist=["quote"]).quote(p, safe="")
            for p in s3_key.split("/")
        )

        canonical_headers = (
            f"content-type:application/json\n"
            f"host:{host}\n"
            f"x-amz-content-sha256:{payload_hash}\n"
            f"x-amz-date:{amz_date}\n"
        )
        signed_headers = "content-type;host;x-amz-content-sha256;x-amz-date"

        canonical_request = "\n".join([
            "PUT",
            f"/{encoded_key}",
            "",
            canonical_headers,
            signed_headers,
            payload_hash,
        ])

        scope = f"{date_stamp}/{region}/s3/aws4_request"
        string_to_sign = "\n".join([
            "AWS4-HMAC-SHA256",
            amz_date,
            scope,
            hashlib.sha256(canonical_request.encode()).hexdigest(),
        ])

        def _hmac(key, msg):
            return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()

        signing_key = _hmac(
            _hmac(
                _hmac(
                    _hmac(f"AWS4{secret_key}".encode("utf-8"), date_stamp),
                    region,
                ),
                "s3",
            ),
            "aws4_request",
        )
        signature = hmac.new(
            signing_key, string_to_sign.encode("utf-8"), hashlib.sha256
        ).hexdigest()

        authorization = (
            f"AWS4-HMAC-SHA256 Credential={access_key}/{scope}, "
            f"SignedHeaders={signed_headers}, Signature={signature}"
        )

        req = Request(
            f"https://{host}/{encoded_key}",
            data=body,
            method="PUT",
            headers={
                "Host": host,
                "Content-Type": "application/json",
                "x-amz-date": amz_date,
                "x-amz-content-sha256": payload_hash,
                "Authorization": authorization,
            },
        )

        with urlopen(req) as resp:
            if resp.status in (200, 201):
                logger.info("Uploaded to s3://%s/%s", bucket, s3_key)
            else:
                logger.error("S3 upload failed: %s", resp.status)
                sys.exit(1)

    except KeyError as e:
        logger.error("Missing environment variable: %s", e)
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Upload live sale detailed times CSV to S3"
    )
    parser.add_argument("csv_path", help="Path to the CSV file")
    parser.add_argument(
        "--sale",
        required=True,
        help="Sale key (e.g. obs_march_2026)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse CSV and print JSON without uploading",
    )
    parser.add_argument(
        "--output",
        help="Also write JSON to a local file (e.g. for frontend/public/data/)",
    )
    parser.add_argument("--verbose", "-v", action="store_true")

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    csv_path = Path(args.csv_path)
    if not csv_path.exists():
        print(f"Error: CSV file not found: {csv_path}", file=sys.stderr)
        sys.exit(1)

    records = parse_csv(str(csv_path))
    if not records:
        print("Error: no records parsed from CSV", file=sys.stderr)
        sys.exit(1)

    data = build_times_json(records, args.sale)

    print(f"Parsed {data['count']} hips with columns: {data['columns']}")

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(data, indent=2))
        print(f"Written to {out_path}")

    if args.dry_run:
        print(json.dumps(data, indent=2)[:2000])
        print("(dry run — not uploading)")
    else:
        upload_to_s3(data, args.sale)
        print("Upload complete.")


if __name__ == "__main__":
    main()
