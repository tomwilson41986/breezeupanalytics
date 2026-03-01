"""S3 storage for breeze-up video and media assets.

Provides upload, download, and presigned URL generation for files
stored in S3.  Key layout:

    s3://{bucket}/{prefix}/{sale_id}/{hip}{suffix}

Example:
    s3://breezeup-media/videos/obs_march_2025/42.mp4
"""

import logging
from datetime import datetime
from pathlib import Path

import boto3
from botocore.exceptions import ClientError
from sqlalchemy.orm import Session

from src.config import S3_BUCKET, S3_PREFIX, S3_REGION
from src.models import Asset

logger = logging.getLogger(__name__)

CONTENT_TYPES = {
    ".mp4": "video/mp4",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".pdf": "application/pdf",
}


def get_s3_client():
    return boto3.client("s3", region_name=S3_REGION)


def s3_key_for_asset(sale_id: str, local_path: str) -> str:
    """Build an S3 key from a sale_id and local file path.

    Example: videos/obs_march_2025/42.mp4
    """
    filename = Path(local_path).name
    return f"{S3_PREFIX}/{sale_id}/{filename}"


def upload_file(
    local_path: str | Path,
    s3_key: str,
    bucket: str = S3_BUCKET,
    s3_client=None,
) -> bool:
    """Upload a local file to S3. Returns True on success."""
    local_path = Path(local_path)
    if not local_path.exists():
        logger.error("File not found: %s", local_path)
        return False

    s3 = s3_client or get_s3_client()
    content_type = CONTENT_TYPES.get(local_path.suffix.lower(), "application/octet-stream")

    try:
        s3.upload_file(
            str(local_path),
            bucket,
            s3_key,
            ExtraArgs={"ContentType": content_type},
        )
        logger.debug("Uploaded %s -> s3://%s/%s", local_path, bucket, s3_key)
        return True
    except ClientError as e:
        logger.error("S3 upload failed for %s: %s", s3_key, e)
        return False


def upload_sale_assets(
    sale_id: str,
    db: Session,
    asset_types: list[str] | None = None,
    bucket: str = S3_BUCKET,
    delete_local: bool = False,
) -> dict:
    """Upload all downloaded assets for a sale to S3.

    Only uploads assets that have a local_path and no s3_key yet.

    Returns:
        Dict with upload stats.
    """
    query = (
        db.query(Asset)
        .join(Asset.lot)
        .filter(Asset.lot.has(sale_id=sale_id))
        .filter(Asset.local_path.isnot(None))
        .filter(Asset.s3_key.is_(None))
    )

    if asset_types:
        query = query.filter(Asset.asset_type.in_(asset_types))

    assets = query.all()
    total = len(assets)
    logger.info("Found %d assets to upload for sale %s", total, sale_id)

    s3 = get_s3_client()
    stats = {"uploaded": 0, "failed": 0, "bytes": 0}

    for i, asset in enumerate(assets, 1):
        local = Path(asset.local_path)
        if not local.exists():
            logger.warning("Missing local file: %s", local)
            stats["failed"] += 1
            continue

        key = s3_key_for_asset(sale_id, asset.local_path)

        if upload_file(local, key, bucket=bucket, s3_client=s3):
            asset.s3_key = key
            asset.uploaded_at = datetime.utcnow()
            stats["uploaded"] += 1
            stats["bytes"] += asset.file_size or local.stat().st_size
            db.commit()

            mb = stats["bytes"] / 1024 / 1024
            pct = i / total * 100
            print(f"\r  [{i}/{total}] {pct:.0f}%  "
                  f"{mb:.0f} MB uploaded  "
                  f"s3://{bucket}/{key}   ", end="", flush=True)

            if delete_local:
                local.unlink()
                asset.local_path = None
                db.commit()
        else:
            stats["failed"] += 1

    print()
    logger.info("Upload complete: %d uploaded (%.1f MB), %d failed",
                stats["uploaded"], stats["bytes"] / 1024 / 1024, stats["failed"])
    return stats


def presigned_url(s3_key: str, bucket: str = S3_BUCKET, expires: int = 3600) -> str:
    """Generate a presigned URL for an S3 object (default 1h expiry)."""
    s3 = get_s3_client()
    return s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket, "Key": s3_key},
        ExpiresIn=expires,
    )
