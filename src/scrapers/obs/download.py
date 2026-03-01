"""Download media assets (videos, photos, PDFs) for OBS sale lots.

Downloads are resumable: existing files with the correct size are skipped.
Files are stored under data/videos/{sale_id}/ with naming convention:
  {hip}.mp4        - breeze video
  {hip}w.mp4       - walk video
  {hip}p.jpg       - conformation photo
  {hip}.pdf        - pedigree page
"""

import hashlib
import logging
import time
from datetime import datetime
from pathlib import Path

import requests
from sqlalchemy.orm import Session

from src.config import REQUEST_DELAY_SECONDS, USER_AGENT
from src.models import Asset

logger = logging.getLogger(__name__)

DATA_ROOT = Path("data/videos")

# Map asset_type to file suffix
SUFFIX_MAP = {
    "breeze_video": ".mp4",
    "walk_video": "w.mp4",
    "photo": "p.jpg",
    "pedigree_page": ".pdf",
}


def _build_local_path(sale_id: str, hip_number: int, asset_type: str) -> Path:
    suffix = SUFFIX_MAP.get(asset_type, "")
    return DATA_ROOT / sale_id / f"{hip_number}{suffix}"


def download_asset(
    asset: Asset,
    sale_id: str,
    hip_number: int,
    session: requests.Session,
    force: bool = False,
) -> bool:
    """Download a single asset file. Returns True if downloaded, False if skipped."""
    if not asset.source_url:
        return False

    local_path = _build_local_path(sale_id, hip_number, asset.asset_type)

    # Skip if already downloaded and not forcing
    if not force and local_path.exists():
        # File on disk — update DB metadata if needed and skip
        if asset.downloaded_at is None:
            size = local_path.stat().st_size
            asset.local_path = str(local_path)
            asset.file_size = size
            asset.downloaded_at = datetime.utcnow()
            logger.debug("Recovered existing file %s (%d bytes)", local_path, size)
        return False

    local_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        resp = session.get(asset.source_url, timeout=60, stream=True)
        resp.raise_for_status()

        md5 = hashlib.md5()
        size = 0
        with open(local_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
                md5.update(chunk)
                size += len(chunk)

        asset.local_path = str(local_path)
        asset.file_size = size
        asset.checksum = md5.hexdigest()
        asset.downloaded_at = datetime.utcnow()

        logger.info("Downloaded %s (%d bytes)", local_path, size)
        return True

    except requests.RequestException as e:
        logger.error("Failed to download %s: %s", asset.source_url, e)
        if local_path.exists():
            local_path.unlink()
        return False


def download_sale_assets(
    sale_id: str,
    db: Session,
    asset_types: list[str] | None = None,
    delay: float = REQUEST_DELAY_SECONDS,
    force: bool = False,
    upload_s3: bool = False,
    delete_local: bool = False,
) -> dict:
    """Download all pending assets for a sale, optionally uploading to S3.

    Args:
        sale_id: Internal sale ID (e.g. "obs_march_2025").
        db: SQLAlchemy session.
        asset_types: Filter to specific types (e.g. ["breeze_video"]).
            Defaults to all types.
        delay: Seconds to wait between downloads.
        force: Re-download even if already present.
        upload_s3: Upload each file to S3 after download.
        delete_local: Delete local file after S3 upload (requires upload_s3).

    Returns:
        Dict with download stats.
    """
    query = (
        db.query(Asset)
        .join(Asset.lot)
        .filter(Asset.lot.has(sale_id=sale_id))
        .filter(Asset.source_url.isnot(None))
    )

    if not force:
        query = query.filter(Asset.downloaded_at.is_(None))

    if asset_types:
        query = query.filter(Asset.asset_type.in_(asset_types))

    # Lazy import to avoid boto3 dependency when S3 isn't used
    s3_uploader = None
    if upload_s3:
        from src.storage import get_s3_client, s3_key_for_asset, upload_file
        s3_uploader = get_s3_client()

    assets = query.all()
    total = len(assets)
    logger.info("Found %d assets to download for sale %s", total, sale_id)

    http_session = requests.Session()
    http_session.headers.update({"User-Agent": USER_AGENT})

    stats = {"downloaded": 0, "skipped": 0, "failed": 0, "bytes": 0, "s3_uploaded": 0}
    start_time = time.time()

    for i, asset in enumerate(assets, 1):
        lot = asset.lot
        success = download_asset(asset, sale_id, lot.hip_number, http_session, force=force)

        if success:
            stats["downloaded"] += 1
            stats["bytes"] += asset.file_size or 0
            db.commit()

            # Upload to S3 if requested
            if s3_uploader and asset.local_path:
                key = s3_key_for_asset(sale_id, asset.local_path)
                if upload_file(asset.local_path, key, s3_client=s3_uploader):
                    asset.s3_key = key
                    asset.uploaded_at = datetime.utcnow()
                    stats["s3_uploaded"] += 1
                    db.commit()
                    if delete_local:
                        Path(asset.local_path).unlink(missing_ok=True)
                        asset.local_path = None
                        db.commit()

            # Progress line
            elapsed = time.time() - start_time
            mb = stats["bytes"] / 1024 / 1024
            rate = mb / elapsed * 60 if elapsed > 0 else 0
            pct = i / total * 100
            s3_tag = f" ({stats['s3_uploaded']} to S3)" if upload_s3 else ""
            print(f"\r  [{i}/{total}] {pct:.0f}%  "
                  f"{mb:.0f} MB downloaded{s3_tag}  "
                  f"{rate:.0f} MB/min  "
                  f"hip {lot.hip_number}   ", end="", flush=True)

            time.sleep(delay)
        elif asset.source_url:
            stats["failed"] += 1
        else:
            stats["skipped"] += 1

    print()  # Newline after progress
    logger.info("Download complete: %d downloaded (%.1f MB), %d failed, %d skipped",
                stats["downloaded"], stats["bytes"] / 1024 / 1024,
                stats["failed"], stats["skipped"])
    return stats
