"""Tests for S3 storage module."""

import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.storage import S3Uploader


class TestS3UploaderInit:
    """Test S3Uploader initialization."""

    def test_requires_bucket_name(self):
        """Raise ValueError when no bucket is provided."""
        with patch.dict(os.environ, {}, clear=True):
            # Ensure S3_BUCKET_NAME is not set
            os.environ.pop("S3_BUCKET_NAME", None)
            with pytest.raises(ValueError, match="bucket name required"):
                S3Uploader()

    @patch("src.storage.boto3")
    def test_init_with_explicit_bucket(self, mock_boto3):
        """Accept explicit bucket name."""
        uploader = S3Uploader(bucket="my-bucket")
        assert uploader.bucket == "my-bucket"
        assert uploader.region == "us-east-1"  # default

    @patch("src.storage.boto3")
    def test_init_with_env_bucket(self, mock_boto3):
        """Read bucket from environment variable."""
        with patch.dict(os.environ, {"S3_BUCKET_NAME": "env-bucket"}):
            uploader = S3Uploader()
            assert uploader.bucket == "env-bucket"

    @patch("src.storage.boto3")
    def test_init_custom_region(self, mock_boto3):
        """Accept custom region."""
        uploader = S3Uploader(bucket="my-bucket", region="eu-west-1")
        assert uploader.region == "eu-west-1"

    @patch("src.storage.boto3")
    def test_init_with_prefix(self, mock_boto3):
        """Store and strip prefix."""
        uploader = S3Uploader(bucket="my-bucket", prefix="/keypoint/")
        assert uploader.prefix == "keypoint"


class TestS3UploaderUploadFile:
    """Test single file upload."""

    @patch("src.storage.boto3")
    def test_upload_file(self, mock_boto3, tmp_path):
        """Upload a file and return the S3 URL."""
        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client

        # Create a test file
        test_file = tmp_path / "metrics.json"
        test_file.write_text('{"test": true}')

        uploader = S3Uploader(bucket="test-bucket", prefix="keypoint/hip654")
        url = uploader.upload_file(test_file)

        mock_client.upload_file.assert_called_once()
        call_args = mock_client.upload_file.call_args
        assert call_args[0][0] == str(test_file)
        assert call_args[0][1] == "test-bucket"
        assert call_args[0][2] == "keypoint/hip654/metrics.json"
        assert "application/json" in str(call_args)
        assert "test-bucket.s3.us-east-1.amazonaws.com" in url

    @patch("src.storage.boto3")
    def test_upload_file_custom_key(self, mock_boto3, tmp_path):
        """Use a custom S3 key instead of prefix/filename."""
        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client

        test_file = tmp_path / "data.csv"
        test_file.write_text("a,b\n1,2")

        uploader = S3Uploader(bucket="test-bucket")
        url = uploader.upload_file(test_file, s3_key="custom/path/data.csv")

        call_args = mock_client.upload_file.call_args
        assert call_args[0][2] == "custom/path/data.csv"

    @patch("src.storage.boto3")
    def test_upload_file_not_found(self, mock_boto3):
        """Raise FileNotFoundError for missing files."""
        uploader = S3Uploader(bucket="test-bucket")
        with pytest.raises(FileNotFoundError):
            uploader.upload_file("/nonexistent/file.json")

    @patch("src.storage.boto3")
    def test_content_type_mp4(self, mock_boto3, tmp_path):
        """Detect MP4 content type."""
        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client

        test_file = tmp_path / "video.mp4"
        test_file.write_bytes(b"\x00" * 100)

        uploader = S3Uploader(bucket="test-bucket", prefix="output")
        uploader.upload_file(test_file)

        call_args = mock_client.upload_file.call_args
        assert call_args[1]["ExtraArgs"]["ContentType"] == "video/mp4"


class TestS3UploaderUploadDirectory:
    """Test directory upload."""

    @patch("src.storage.boto3")
    def test_upload_directory(self, mock_boto3, tmp_path):
        """Upload all matching files in a directory."""
        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client

        # Create test files
        (tmp_path / "metrics.json").write_text("{}")
        (tmp_path / "metrics.csv").write_text("a,b")
        (tmp_path / "video.mp4").write_bytes(b"\x00" * 10)
        (tmp_path / "notes.txt").write_text("ignore me")

        uploader = S3Uploader(bucket="test-bucket", prefix="keypoint/hip654")
        urls = uploader.upload_directory(tmp_path, extensions={".json", ".csv", ".mp4"})

        assert len(urls) == 3
        assert "metrics.json" in urls
        assert "metrics.csv" in urls
        assert "video.mp4" in urls
        assert "notes.txt" not in urls

    @patch("src.storage.boto3")
    def test_upload_directory_no_filter(self, mock_boto3, tmp_path):
        """Upload all files when no extension filter."""
        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client

        (tmp_path / "a.json").write_text("{}")
        (tmp_path / "b.txt").write_text("hello")

        uploader = S3Uploader(bucket="test-bucket", prefix="data")
        urls = uploader.upload_directory(tmp_path)

        assert len(urls) == 2

    @patch("src.storage.boto3")
    def test_upload_directory_not_a_dir(self, mock_boto3, tmp_path):
        """Raise error for non-directory path."""
        uploader = S3Uploader(bucket="test-bucket")
        test_file = tmp_path / "file.txt"
        test_file.write_text("hi")
        with pytest.raises(NotADirectoryError):
            uploader.upload_directory(test_file)


class TestS3UploaderPipelineOutput:
    """Test pipeline output upload convenience method."""

    @patch("src.storage.boto3")
    def test_upload_pipeline_output(self, mock_boto3, tmp_path):
        """Upload only pipeline output file types."""
        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client

        # Simulate pipeline output directory
        (tmp_path / "hip654_raw_analyzed.mp4").write_bytes(b"\x00" * 50)
        (tmp_path / "hip654_raw_metrics.json").write_text("{}")
        (tmp_path / "hip654_raw_metrics.csv").write_text("a,b")
        (tmp_path / "hip654_raw.mp4").write_bytes(b"\x00" * 50)
        (tmp_path / "debug.log").write_text("should be skipped")
        (tmp_path / ".gitkeep").write_text("")

        uploader = S3Uploader(bucket="test-bucket", prefix="keypoint/hip654")
        urls = uploader.upload_pipeline_output(tmp_path)

        # Should upload .mp4, .json, .csv but not .log or .gitkeep
        assert len(urls) == 4
        assert "debug.log" not in urls
        assert ".gitkeep" not in urls
