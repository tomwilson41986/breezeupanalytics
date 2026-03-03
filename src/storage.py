"""S3 storage utilities for uploading pipeline output files.

Usage:
    from src.storage import S3Uploader

    uploader = S3Uploader(bucket="my-bucket")
    urls = uploader.upload_pipeline_output("output/hip654", prefix="keypoint/hip654")
    # Returns dict of {filename: s3_url}

Environment variables:
    AWS_ACCESS_KEY_ID       - AWS access key (or use IAM role / profile)
    AWS_SECRET_ACCESS_KEY   - AWS secret key
    AWS_DEFAULT_REGION      - AWS region (default: us-east-1)
    S3_BUCKET_NAME          - Default bucket name
"""

from __future__ import annotations

import logging
import mimetypes
import os
from pathlib import Path

import boto3
from botocore.exceptions import BotoCoreError, ClientError

logger = logging.getLogger(__name__)

# Content types for our output files
CONTENT_TYPES = {
    ".mp4": "video/mp4",
    ".json": "application/json",
    ".csv": "text/csv",
    ".parquet": "application/octet-stream",
}


class S3Uploader:
    """Upload files to S3 with sensible defaults for pipeline output."""

    def __init__(
        self,
        bucket: str | None = None,
        region: str | None = None,
        prefix: str = "",
    ):
        self.bucket = bucket or os.environ.get("S3_BUCKET_NAME", "")
        self.region = region or os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
        self.prefix = prefix.strip("/")

        if not self.bucket:
            raise ValueError(
                "S3 bucket name required. Set S3_BUCKET_NAME env var or pass bucket= argument."
            )

        self._client = boto3.client("s3", region_name=self.region)
        logger.info("S3Uploader initialized: bucket=%s, region=%s", self.bucket, self.region)

    def upload_file(
        self,
        local_path: str | Path,
        s3_key: str | None = None,
    ) -> str:
        """Upload a single file to S3.

        Args:
            local_path: Path to the local file.
            s3_key: S3 object key. Defaults to prefix/filename.

        Returns:
            The S3 URL of the uploaded object.
        """
        local_path = Path(local_path)
        if not local_path.exists():
            raise FileNotFoundError(f"File not found: {local_path}")

        if s3_key is None:
            s3_key = f"{self.prefix}/{local_path.name}" if self.prefix else local_path.name

        content_type = CONTENT_TYPES.get(
            local_path.suffix.lower(),
            mimetypes.guess_type(str(local_path))[0] or "application/octet-stream",
        )

        size_mb = local_path.stat().st_size / (1024 * 1024)
        logger.info("Uploading %s (%.1f MB) -> s3://%s/%s", local_path.name, size_mb, self.bucket, s3_key)

        try:
            self._client.upload_file(
                str(local_path),
                self.bucket,
                s3_key,
                ExtraArgs={"ContentType": content_type},
            )
        except (BotoCoreError, ClientError) as e:
            logger.error("Failed to upload %s: %s", local_path, e)
            raise

        url = f"https://{self.bucket}.s3.{self.region}.amazonaws.com/{s3_key}"
        logger.info("Uploaded: %s", url)
        return url

    def upload_directory(
        self,
        local_dir: str | Path,
        s3_prefix: str | None = None,
        extensions: set[str] | None = None,
    ) -> dict[str, str]:
        """Upload all files in a directory to S3.

        Args:
            local_dir: Local directory to upload.
            s3_prefix: S3 prefix for all files. Defaults to self.prefix.
            extensions: If set, only upload files with these extensions (e.g. {".json", ".csv"}).

        Returns:
            Dict mapping filename to S3 URL.
        """
        local_dir = Path(local_dir)
        if not local_dir.is_dir():
            raise NotADirectoryError(f"Not a directory: {local_dir}")

        prefix = s3_prefix if s3_prefix is not None else self.prefix
        uploaded: dict[str, str] = {}

        for filepath in sorted(local_dir.iterdir()):
            if not filepath.is_file():
                continue
            if extensions and filepath.suffix.lower() not in extensions:
                continue

            s3_key = f"{prefix}/{filepath.name}" if prefix else filepath.name
            url = self.upload_file(filepath, s3_key=s3_key)
            uploaded[filepath.name] = url

        logger.info("Uploaded %d files from %s", len(uploaded), local_dir)
        return uploaded

    def upload_pipeline_output(
        self,
        output_dir: str | Path,
        s3_prefix: str | None = None,
    ) -> dict[str, str]:
        """Upload all pipeline output files (video, CSV, JSON) from an output directory.

        Args:
            output_dir: Directory containing pipeline output (e.g. output/hip654/).
            s3_prefix: S3 prefix. Defaults to self.prefix.

        Returns:
            Dict mapping filename to S3 URL.
        """
        return self.upload_directory(
            output_dir,
            s3_prefix=s3_prefix,
            extensions={".mp4", ".json", ".csv", ".parquet"},
        )
