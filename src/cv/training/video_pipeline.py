"""Pipeline to fetch OBS breeze videos and auto-label them for training.

Connects the OBS catalog scraper with the CV auto-labeling agent:
1. Fetch sale data from OBS API
2. Download breeze videos for selected hips
3. Extract frames from each video
4. Run auto-labeler to generate pseudo-labels
5. Output a YOLO-Pose dataset ready for training

Usage:
    pipeline = SaleVideoLabelPipeline(sale_id=149)
    result = pipeline.run(output_dir="data/labeled/obs_march_2026")
"""

from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path

import requests

from src.config import MAX_RETRIES, REQUEST_DELAY_SECONDS, RETRY_BACKOFF_FACTOR, USER_AGENT

logger = logging.getLogger(__name__)


@dataclass
class VideoDownload:
    """A downloaded breeze video."""
    hip_number: int
    sale_id: str
    horse_name: str | None
    sire: str | None
    video_url: str
    local_path: Path
    file_size: int = 0
    checksum: str = ""


@dataclass
class SaleLabelResult:
    """Result of auto-labeling a full sale catalog."""
    sale_id: str
    sale_name: str
    num_hips_with_video: int = 0
    num_videos_downloaded: int = 0
    num_download_errors: int = 0
    num_frames_extracted: int = 0
    num_frames_labeled: int = 0
    num_horses_detected: int = 0
    num_flagged_for_review: int = 0
    mean_quality: float = 0.0
    output_dir: str = ""
    dataset_dir: str = ""


def download_video(
    url: str,
    output_path: Path,
    session: requests.Session | None = None,
    timeout: int = 60,
) -> int:
    """Download a video file with retry logic.

    Args:
        url: Video URL to download.
        output_path: Local path to save the file.
        session: Optional requests session.
        timeout: Request timeout in seconds.

    Returns:
        File size in bytes.
    """
    if session is None:
        session = requests.Session()
        session.headers.update({"User-Agent": USER_AGENT})

    output_path.parent.mkdir(parents=True, exist_ok=True)

    for attempt in range(MAX_RETRIES + 1):
        try:
            resp = session.get(url, timeout=timeout, stream=True)
            resp.raise_for_status()

            with open(output_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)

            size = output_path.stat().st_size
            logger.debug("Downloaded %s (%d bytes)", output_path.name, size)
            return size

        except requests.RequestException as e:
            if attempt == MAX_RETRIES:
                raise
            wait = REQUEST_DELAY_SECONDS * (RETRY_BACKOFF_FACTOR ** attempt)
            logger.warning("Download failed (attempt %d/%d): %s. Retrying in %.1fs",
                           attempt + 1, MAX_RETRIES, e, wait)
            time.sleep(wait)

    return 0


class SaleVideoLabelPipeline:
    """Pipeline to fetch OBS sale videos and auto-label them.

    Designed to produce training data at scale from the OBS catalog.
    Supports filtering by hip range, sale status, and video availability.
    """

    def __init__(
        self,
        sale_id: int | str = 149,
        frames_per_video: int = 30,
        frame_strategy: str = "motion",
        detection_confidence: float = 0.4,
        keypoint_confidence: float = 0.2,
        quality_threshold: float = 0.4,
        min_confident_kpts: int = 8,
        max_hips: int | None = None,
        skip_downloaded: bool = True,
    ):
        """
        Args:
            sale_id: OBS catalog sale ID (e.g. 149 for 2026 March).
            frames_per_video: Number of frames to extract per video.
            frame_strategy: Frame selection ("uniform", "random", "motion").
            detection_confidence: Horse detection threshold.
            keypoint_confidence: Keypoint confidence threshold.
            quality_threshold: Minimum quality score to accept auto-labels.
            min_confident_kpts: Minimum confident keypoints per label.
            max_hips: Cap on number of hips to process (None = all).
            skip_downloaded: Skip videos already downloaded locally.
        """
        self.sale_id = str(sale_id)
        self.frames_per_video = frames_per_video
        self.frame_strategy = frame_strategy
        self.detection_confidence = detection_confidence
        self.keypoint_confidence = keypoint_confidence
        self.quality_threshold = quality_threshold
        self.min_confident_kpts = min_confident_kpts
        self.max_hips = max_hips
        self.skip_downloaded = skip_downloaded

    def run(self, output_dir: str | Path) -> SaleLabelResult:
        """Execute the full pipeline: fetch -> download -> label.

        Args:
            output_dir: Root output directory. Will create subdirectories:
                videos/    - Downloaded .mp4 files
                images/    - Extracted frames
                labels/    - YOLO-Pose auto-labels
                review/    - Flagged images for human review

        Returns:
            SaleLabelResult with counts and paths.
        """
        from src.cv.training.auto_label import AutoLabelAgent
        from src.cv.training.dataset import extract_frames_for_labeling

        output_dir = Path(output_dir)
        videos_dir = output_dir / "videos"
        images_dir = output_dir / "images"
        labels_dir = output_dir / "labels"
        review_dir = output_dir / "review"

        for d in [videos_dir, images_dir, labels_dir, review_dir]:
            d.mkdir(parents=True, exist_ok=True)

        # Step 1: Fetch sale data
        logger.info("Fetching sale %s from OBS API...", self.sale_id)
        from src.scrapers.obs.catalog import fetch_sale
        sale = fetch_sale(self.sale_id)

        result = SaleLabelResult(
            sale_id=self.sale_id,
            sale_name=sale.sale_name,
            output_dir=str(output_dir),
            dataset_dir=str(output_dir),
        )

        # Step 2: Filter hips with breeze videos
        hips_with_video = [h for h in sale.hips if h.has_video and h.video_url]
        result.num_hips_with_video = len(hips_with_video)
        logger.info("Sale %s: %d hips with breeze video out of %d total",
                     sale.sale_name, len(hips_with_video), len(sale.hips))

        if self.max_hips:
            hips_with_video = hips_with_video[:self.max_hips]

        # Step 3: Download videos
        session = requests.Session()
        session.headers.update({"User-Agent": USER_AGENT})
        downloads: list[VideoDownload] = []

        for hip in hips_with_video:
            video_path = videos_dir / f"hip{hip.hip_number:04d}.mp4"

            if self.skip_downloaded and video_path.exists() and video_path.stat().st_size > 0:
                logger.debug("Skipping already downloaded: %s", video_path.name)
                downloads.append(VideoDownload(
                    hip_number=hip.hip_number,
                    sale_id=hip.sale_id,
                    horse_name=hip.horse_name,
                    sire=hip.sire,
                    video_url=hip.video_url,
                    local_path=video_path,
                    file_size=video_path.stat().st_size,
                ))
                continue

            try:
                size = download_video(hip.video_url, video_path, session=session)
                downloads.append(VideoDownload(
                    hip_number=hip.hip_number,
                    sale_id=hip.sale_id,
                    horse_name=hip.horse_name,
                    sire=hip.sire,
                    video_url=hip.video_url,
                    local_path=video_path,
                    file_size=size,
                ))
                result.num_videos_downloaded += 1

                # Polite delay between downloads
                time.sleep(REQUEST_DELAY_SECONDS)

            except Exception as e:
                logger.error("Failed to download hip %d: %s", hip.hip_number, e)
                result.num_download_errors += 1

        logger.info("Downloaded %d videos (%d errors)",
                     result.num_videos_downloaded, result.num_download_errors)

        # Step 4: Extract frames from all downloaded videos
        logger.info("Extracting frames (%d per video, %s strategy)...",
                     self.frames_per_video, self.frame_strategy)

        for dl in downloads:
            if not dl.local_path.exists() or dl.local_path.stat().st_size == 0:
                continue

            try:
                frames = extract_frames_for_labeling(
                    dl.local_path,
                    output_dir=images_dir,
                    num_frames=self.frames_per_video,
                    strategy=self.frame_strategy,
                )
                result.num_frames_extracted += len(frames)
            except Exception as e:
                logger.error("Failed to extract frames from hip %d: %s", dl.hip_number, e)

        logger.info("Extracted %d total frames", result.num_frames_extracted)

        # Step 5: Auto-label all extracted frames
        logger.info("Running auto-labeler...")
        agent = AutoLabelAgent(
            detection_confidence=self.detection_confidence,
            keypoint_confidence=self.keypoint_confidence,
            quality_threshold=self.quality_threshold,
            min_confident_kpts=self.min_confident_kpts,
        )

        label_result = agent.label_directory(images_dir, labels_dir, review_dir=review_dir)

        result.num_frames_labeled = label_result.num_labeled
        result.num_horses_detected = label_result.num_horses
        result.num_flagged_for_review = label_result.num_flagged
        result.mean_quality = label_result.mean_quality

        logger.info(
            "Auto-labeling complete: %d frames labeled, %d horses, %d flagged, quality %.2f",
            result.num_frames_labeled, result.num_horses_detected,
            result.num_flagged_for_review, result.mean_quality,
        )

        # Write pipeline manifest
        self._write_manifest(output_dir, result, downloads)

        return result

    def _write_manifest(
        self,
        output_dir: Path,
        result: SaleLabelResult,
        downloads: list[VideoDownload],
    ) -> None:
        """Write a JSON manifest with pipeline metadata."""
        import json

        manifest = {
            "pipeline": "sale_video_label",
            "sale_id": result.sale_id,
            "sale_name": result.sale_name,
            "config": {
                "frames_per_video": self.frames_per_video,
                "frame_strategy": self.frame_strategy,
                "detection_confidence": self.detection_confidence,
                "keypoint_confidence": self.keypoint_confidence,
                "quality_threshold": self.quality_threshold,
                "min_confident_kpts": self.min_confident_kpts,
            },
            "results": {
                "hips_with_video": result.num_hips_with_video,
                "videos_downloaded": result.num_videos_downloaded,
                "download_errors": result.num_download_errors,
                "frames_extracted": result.num_frames_extracted,
                "frames_labeled": result.num_frames_labeled,
                "horses_detected": result.num_horses_detected,
                "flagged_for_review": result.num_flagged_for_review,
                "mean_quality": round(result.mean_quality, 3),
            },
            "videos": [
                {
                    "hip": dl.hip_number,
                    "horse_name": dl.horse_name,
                    "sire": dl.sire,
                    "url": dl.video_url,
                    "local_path": str(dl.local_path),
                    "file_size": dl.file_size,
                }
                for dl in downloads
            ],
        }

        manifest_path = output_dir / "pipeline_manifest.json"
        with open(manifest_path, "w") as f:
            json.dump(manifest, f, indent=2)

        logger.info("Wrote pipeline manifest to %s", manifest_path)
