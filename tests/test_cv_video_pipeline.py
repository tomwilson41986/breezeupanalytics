"""Tests for the OBS sale video -> auto-label pipeline."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import cv2
import numpy as np
import pytest

from src.cv.training.video_pipeline import (
    SaleLabelResult,
    SaleVideoLabelPipeline,
    VideoDownload,
    download_video,
)


# ---------- Helpers ----------

def _make_test_video(path: Path, n_frames: int = 30) -> None:
    """Create a minimal test video."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(path), fourcc, 30.0, (320, 240))
    for i in range(n_frames):
        frame = np.random.randint(0, 255, (240, 320, 3), dtype=np.uint8)
        writer.write(frame)
    writer.release()


def _make_mock_obs_hip(hip_number: int, has_video: bool = True):
    """Create a mock OBSHip dataclass."""
    mock = MagicMock()
    mock.hip_number = hip_number
    mock.sale_id = "149"
    mock.horse_name = f"Horse {hip_number}"
    mock.sire = f"Sire {hip_number}"
    mock.has_video = has_video
    mock.video_url = f"https://obscatalog.com/2026/149/{hip_number}.mp4" if has_video else None
    return mock


def _make_mock_obs_sale(num_hips: int = 10, num_with_video: int = 8):
    """Create a mock OBSSale."""
    mock = MagicMock()
    mock.sale_id = "149"
    mock.sale_name = "2026 March 2YOs in Training Sale"
    mock.hips = []
    for i in range(num_hips):
        has_video = i < num_with_video
        mock.hips.append(_make_mock_obs_hip(i + 1, has_video=has_video))
    return mock


# ---------- Download tests ----------

class TestVideoDownload:
    def test_download_video_success(self, tmp_path):
        """Test video download with mocked HTTP response."""
        output_path = tmp_path / "test.mp4"
        fake_content = b"\x00" * 1024  # 1KB fake video

        with patch("src.cv.training.video_pipeline.requests") as mock_requests:
            mock_session = MagicMock()
            mock_resp = MagicMock()
            mock_resp.iter_content.return_value = [fake_content]
            mock_session.get.return_value = mock_resp

            size = download_video(
                "https://example.com/video.mp4",
                output_path,
                session=mock_session,
            )

        assert output_path.exists()
        assert size == 1024

    def test_download_creates_parent_dirs(self, tmp_path):
        """Download should create parent directories if they don't exist."""
        output_path = tmp_path / "nested" / "deep" / "test.mp4"
        fake_content = b"\x00" * 512

        with patch("src.cv.training.video_pipeline.requests") as mock_requests:
            mock_session = MagicMock()
            mock_resp = MagicMock()
            mock_resp.iter_content.return_value = [fake_content]
            mock_session.get.return_value = mock_resp

            download_video("https://example.com/v.mp4", output_path, session=mock_session)

        assert output_path.exists()


# ---------- Pipeline tests (fully mocked) ----------

class TestSaleVideoLabelPipeline:
    def _run_pipeline(self, tmp_path, sale, max_hips=None, frames_per_video=30,
                       download_side_effect=None, label_result_kwargs=None):
        """Helper to run the pipeline with all dependencies mocked."""
        label_kwargs = {
            "num_labeled": 0, "num_horses": 0, "num_flagged": 0, "mean_quality": 0.0
        }
        if label_result_kwargs:
            label_kwargs.update(label_result_kwargs)

        dl_effect = download_side_effect or 1024

        with patch("src.scrapers.obs.catalog.fetch_sale") as mock_fetch, \
             patch("src.cv.training.video_pipeline.download_video") as mock_download, \
             patch("src.cv.training.auto_label.AutoLabelAgent._init_models"), \
             patch("src.cv.training.auto_label.AutoLabelAgent.label_image") as mock_label_img, \
             patch("src.cv.training.dataset.extract_frames_for_labeling") as mock_extract:

            mock_fetch.return_value = sale

            if isinstance(dl_effect, list):
                mock_download.side_effect = dl_effect
            else:
                mock_download.return_value = dl_effect

            mock_extract.return_value = []
            mock_label_img.return_value = []

            pipeline = SaleVideoLabelPipeline(
                sale_id=149, max_hips=max_hips, frames_per_video=frames_per_video,
            )
            result = pipeline.run(tmp_path / "output")

        return result, mock_fetch, mock_download

    def test_pipeline_fetches_sale(self, tmp_path):
        """Pipeline should fetch sale data from OBS API."""
        sale = _make_mock_obs_sale(num_hips=5, num_with_video=3)
        result, mock_fetch, _ = self._run_pipeline(
            tmp_path, sale, max_hips=3,
            label_result_kwargs={"num_labeled": 3, "num_horses": 3, "num_flagged": 1, "mean_quality": 0.6},
        )

        mock_fetch.assert_called_once_with("149")
        assert result.sale_name == "2026 March 2YOs in Training Sale"
        assert result.num_hips_with_video == 3

    def test_pipeline_downloads_videos(self, tmp_path):
        """Pipeline should download breeze videos for hips with video."""
        sale = _make_mock_obs_sale(num_hips=5, num_with_video=3)
        result, _, mock_download = self._run_pipeline(
            tmp_path, sale, download_side_effect=2048,
        )

        assert mock_download.call_count == 3
        assert result.num_videos_downloaded == 3

    def test_pipeline_max_hips_limit(self, tmp_path):
        """Pipeline should respect max_hips limit."""
        sale = _make_mock_obs_sale(num_hips=20, num_with_video=15)
        result, _, mock_download = self._run_pipeline(
            tmp_path, sale, max_hips=5,
        )

        assert mock_download.call_count == 5

    def test_pipeline_handles_download_errors(self, tmp_path):
        """Pipeline should continue processing when individual downloads fail."""
        sale = _make_mock_obs_sale(num_hips=4, num_with_video=4)
        result, _, _ = self._run_pipeline(
            tmp_path, sale,
            download_side_effect=[1024, 1024, Exception("timeout"), Exception("404")],
        )

        assert result.num_videos_downloaded == 2
        assert result.num_download_errors == 2

    def test_pipeline_writes_manifest(self, tmp_path):
        """Pipeline should write a JSON manifest with pipeline metadata."""
        sale = _make_mock_obs_sale(num_hips=2, num_with_video=2)
        self._run_pipeline(tmp_path, sale, frames_per_video=20)

        manifest_path = tmp_path / "output" / "pipeline_manifest.json"
        assert manifest_path.exists()

        with open(manifest_path) as f:
            manifest = json.load(f)

        assert manifest["sale_id"] == "149"
        assert manifest["config"]["frames_per_video"] == 20
        assert len(manifest["videos"]) == 2
        assert manifest["results"]["videos_downloaded"] == 2

    def test_pipeline_output_directory_structure(self, tmp_path):
        """Pipeline should create proper subdirectory structure."""
        sale = _make_mock_obs_sale(num_hips=1, num_with_video=1)
        self._run_pipeline(tmp_path, sale)

        out = tmp_path / "output"
        assert (out / "videos").is_dir()
        assert (out / "images").is_dir()
        assert (out / "labels").is_dir()
        assert (out / "review").is_dir()


class TestVideoDownloadDataclass:
    def test_video_download_fields(self):
        dl = VideoDownload(
            hip_number=42,
            sale_id="149",
            horse_name="Test Horse",
            sire="Test Sire",
            video_url="https://example.com/42.mp4",
            local_path=Path("/tmp/42.mp4"),
            file_size=1024,
        )
        assert dl.hip_number == 42
        assert dl.file_size == 1024
