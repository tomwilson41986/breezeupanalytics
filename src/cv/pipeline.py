"""End-to-end equine gait analysis pipeline.

Orchestrates: video loading -> detection -> keypoint estimation -> tracking
-> smoothing -> gait analysis -> metrics -> visualization -> output.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path

import csv
import numpy as np

from src.cv.calibration import Calibration
from src.cv.detection import HorseDetector
from src.cv.gait import (
    GaitAnalysis, compute_limb_phases, detect_hoof_contacts, detect_overreach,
    detect_strides, detect_suspension_phases,
)
from src.cv.keypoints import EquineKeypointEstimator, FrameKeypoints, KeypointResult
from src.cv.metrics import HorseMetrics, compute_metrics
from src.cv.schema import NUM_KEYPOINTS
from src.cv.smoothing import smooth_all_keypoints
from src.cv.video import FrameBatch, VideoWriter, extract_frames, get_video_meta
from src.cv.visualization import draw_frame_overlay, draw_metrics_panel

logger = logging.getLogger(__name__)


@dataclass
class PipelineConfig:
    """Configuration for the gait analysis pipeline."""
    # Detection
    detection_model: str = "yolo11n.pt"
    detection_confidence: float = 0.5

    # Keypoints
    keypoint_model: str = "yolo11n-pose.pt"
    keypoint_confidence: float = 0.3

    # Tracking
    enable_tracking: bool = True
    tracker: str = "bytetrack.yaml"

    # Smoothing
    smoothing_window: int = 7
    smoothing_polyorder: int = 2

    # Output
    output_video: bool = True
    output_csv: bool = True
    output_json: bool = True

    # Video processing
    frame_stride: int = 1      # process every Nth frame
    max_frames: int | None = None

    # Calibration
    px_per_meter: float | None = None

    # S3 upload
    s3_upload: bool = False
    s3_bucket: str | None = None
    s3_prefix: str = "keypoint"


@dataclass
class PipelineResult:
    """Result of running the gait analysis pipeline on a video."""
    video_path: str
    duration_s: float = 0.0
    fps: float = 0.0
    frames_processed: int = 0
    horses_detected: int = 0
    horse_metrics: list[HorseMetrics] = field(default_factory=list)
    output_video_path: str | None = None
    output_csv_path: str | None = None
    output_json_path: str | None = None
    processing_time_s: float = 0.0
    s3_urls: dict[str, str] = field(default_factory=dict)


class GaitAnalysisPipeline:
    """End-to-end pipeline for equine gait analysis from video."""

    def __init__(self, config: PipelineConfig | None = None):
        self.config = config or PipelineConfig()
        self._detector: HorseDetector | None = None
        self._estimator: EquineKeypointEstimator | None = None

    def _init_models(self) -> None:
        """Lazy-initialize detection and keypoint models."""
        if self._detector is None:
            self._detector = HorseDetector(
                model_path=self.config.detection_model,
                confidence_threshold=self.config.detection_confidence,
            )
        if self._estimator is None:
            self._estimator = EquineKeypointEstimator(
                model_path=self.config.keypoint_model,
                confidence_threshold=self.config.keypoint_confidence,
            )

    def process_video(
        self,
        video_path: str | Path,
        output_dir: str | Path | None = None,
    ) -> PipelineResult:
        """Process a video end-to-end and generate gait analysis.

        Args:
            video_path: Path to the input video file.
            output_dir: Directory for output files. Defaults to same dir as video.

        Returns:
            PipelineResult with metrics and output file paths.
        """
        t_start = time.time()
        video_path = Path(video_path)
        output_dir = Path(output_dir) if output_dir else video_path.parent
        output_dir.mkdir(parents=True, exist_ok=True)

        logger.info("Processing video: %s", video_path)

        # --- Step 1: Load video ---
        meta = get_video_meta(video_path)
        logger.info("Video: %dx%d @ %.1f FPS, %d frames (%.1fs)",
                     meta.width, meta.height, meta.fps, meta.frame_count, meta.duration_s)

        batch = extract_frames(
            video_path,
            stride=self.config.frame_stride,
            max_frames=self.config.max_frames,
        )

        # --- Step 2: Initialize models ---
        self._init_models()
        assert self._detector is not None
        assert self._estimator is not None

        # --- Step 3: Detect + track + estimate keypoints ---
        logger.info("Running detection and keypoint estimation on %d frames...", len(batch.frames))

        all_detections = []
        all_keypoints: list[FrameKeypoints] = []

        # Track horses across frames for consistent IDs
        if self.config.enable_tracking:
            tracked = self._detector.detect_and_track(batch.frames, self.config.tracker)
            all_detections = tracked
        else:
            all_detections = self._detector.detect_batch(batch.frames)

        for i, (frame, dets) in enumerate(zip(batch.frames, all_detections)):
            kpts = self._estimator.estimate(frame, dets)
            fk = FrameKeypoints(frame_idx=batch.indices[i], horses=kpts)

            # Propagate track IDs
            for j, kr in enumerate(kpts):
                if j < len(dets):
                    kr.track_id = dets[j].track_id
                kr.frame_idx = batch.indices[i]

            all_keypoints.append(fk)

        # --- Step 4: Organize by horse track ID ---
        horse_tracks = self._organize_by_track(all_keypoints, batch.fps)

        # --- Step 5: Smooth, detect gait, compute metrics per horse ---
        all_horse_metrics = []
        calibration_factor = self.config.px_per_meter

        for track_id, (kpts_seq, conf_seq) in horse_tracks.items():
            logger.info("Analyzing horse track #%s (%d frames)", track_id, len(kpts_seq))

            # Smooth keypoint trajectories
            kpts_smoothed = smooth_all_keypoints(
                kpts_seq, conf_seq,
                window_length=self.config.smoothing_window,
                polyorder=self.config.smoothing_polyorder,
            )

            # Detect gait cycles
            gait = detect_strides(kpts_smoothed, conf_seq, batch.fps)
            gait.track_id = track_id

            # Detect hoof contacts
            contacts = detect_hoof_contacts(kpts_smoothed, conf_seq, batch.fps)
            limb_phases = compute_limb_phases(contacts, gait.strides, batch.fps)

            # Detect suspension phases (all 4 hooves off ground)
            gait.suspension_phases = detect_suspension_phases(
                contacts, gait.strides, batch.fps,
            )

            # Detect overreach
            gait.overreach_events = detect_overreach(
                kpts_smoothed, conf_seq, contacts, gait.strides,
                px_per_meter=calibration_factor,
            )

            # Compute metrics (including Phase 3 additions)
            horse_m = compute_metrics(
                kpts_smoothed, conf_seq, gait, batch.fps,
                limb_phases=limb_phases,
                px_per_meter=calibration_factor,
            )
            all_horse_metrics.append(horse_m)

        # --- Step 6: Generate output ---
        result = PipelineResult(
            video_path=str(video_path),
            duration_s=meta.duration_s,
            fps=meta.fps,
            frames_processed=len(batch.frames),
            horses_detected=len(horse_tracks),
            horse_metrics=all_horse_metrics,
        )

        stem = video_path.stem

        # Annotated video
        if self.config.output_video:
            out_video = output_dir / f"{stem}_analyzed.mp4"
            self._write_annotated_video(
                out_video, batch, all_detections, all_keypoints, meta, all_horse_metrics
            )
            result.output_video_path = str(out_video)

        # CSV
        if self.config.output_csv and all_horse_metrics:
            out_csv = output_dir / f"{stem}_metrics.csv"
            self._write_csv(out_csv, all_horse_metrics)
            result.output_csv_path = str(out_csv)

        # JSON
        if self.config.output_json and all_horse_metrics:
            out_json = output_dir / f"{stem}_metrics.json"
            self._write_json(out_json, all_horse_metrics, result)
            result.output_json_path = str(out_json)

        # S3 upload
        if self.config.s3_upload:
            result.s3_urls = self._upload_to_s3(output_dir, stem)

        result.processing_time_s = time.time() - t_start
        logger.info(
            "Pipeline complete: %d horses, %d total strides, %.1fs processing time",
            len(all_horse_metrics),
            sum(m.num_strides for m in all_horse_metrics),
            result.processing_time_s,
        )

        return result

    def _organize_by_track(
        self,
        all_keypoints: list[FrameKeypoints],
        fps: float,
    ) -> dict[int, tuple[np.ndarray, np.ndarray]]:
        """Organize keypoint results by horse track ID.

        Returns dict mapping track_id to (keypoints_seq, confidence_seq)
        arrays of shape (T, K, 2) and (T, K).
        """
        # Collect all unique track IDs
        track_ids: set[int] = set()
        for fk in all_keypoints:
            for kr in fk.horses:
                tid = kr.track_id if kr.track_id is not None else 0
                track_ids.add(tid)

        if not track_ids:
            return {}

        T = len(all_keypoints)
        result: dict[int, tuple[np.ndarray, np.ndarray]] = {}

        for tid in track_ids:
            kpts_seq = np.zeros((T, NUM_KEYPOINTS, 2), dtype=np.float32)
            conf_seq = np.zeros((T, NUM_KEYPOINTS), dtype=np.float32)

            for t, fk in enumerate(all_keypoints):
                for kr in fk.horses:
                    kr_tid = kr.track_id if kr.track_id is not None else 0
                    if kr_tid == tid:
                        kpts_seq[t] = kr.keypoints
                        conf_seq[t] = kr.confidence
                        break

            result[tid] = (kpts_seq, conf_seq)

        return result

    def _write_annotated_video(
        self,
        output_path: Path,
        batch: FrameBatch,
        all_detections: list[list],
        all_keypoints: list[FrameKeypoints],
        meta,
        horse_metrics: list[HorseMetrics],
    ) -> None:
        """Write annotated video with keypoint overlays and metrics panel."""
        logger.info("Writing annotated video to %s", output_path)

        # Get aggregate metrics for the panel
        stride_freq = None
        stride_len = None
        speed = None
        symmetry = None

        if horse_metrics:
            m = horse_metrics[0]
            stride_freq = m.mean_stride_frequency_hz if m.mean_stride_frequency_hz > 0 else None
            stride_len = m.mean_stride_length_px if m.mean_stride_length_px > 0 else None
            speed = m.mean_speed_px_s if m.mean_speed_px_s > 0 else None
            symmetry = m.mean_lateral_symmetry

        with VideoWriter(output_path, meta.fps, meta.width, meta.height) as writer:
            for i, frame in enumerate(batch.frames):
                dets = all_detections[i] if i < len(all_detections) else []
                fk = all_keypoints[i] if i < len(all_keypoints) else FrameKeypoints(frame_idx=i)

                vis = draw_frame_overlay(frame, dets, fk.horses, batch.indices[i])
                vis = draw_metrics_panel(vis, stride_freq, stride_len, speed, symmetry)
                writer.write(vis)

    def _write_csv(self, path: Path, horse_metrics: list[HorseMetrics]) -> None:
        """Write per-horse summary metrics to CSV."""
        if not horse_metrics:
            return

        rows = [m.to_dict() for m in horse_metrics]
        # Use union of all field names to handle varying duty factor columns
        all_fields: dict[str, None] = {}
        for row in rows:
            for key in row:
                all_fields[key] = None
        fieldnames = list(all_fields.keys())

        with open(path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

        logger.info("Wrote metrics CSV to %s", path)

    def _write_json(self, path: Path, horse_metrics: list[HorseMetrics], result: PipelineResult) -> None:
        """Write detailed metrics to JSON including per-stride breakdown."""
        output = {
            "video": result.video_path,
            "duration_s": result.duration_s,
            "fps": result.fps,
            "frames_processed": result.frames_processed,
            "horses_detected": result.horses_detected,
            "processing_time_s": round(result.processing_time_s, 2),
            "horses": [m.to_detail_dict() for m in horse_metrics],
        }

        with open(path, "w") as f:
            json.dump(output, f, indent=2)

        logger.info("Wrote metrics JSON to %s", path)

    def _upload_to_s3(self, output_dir: Path, stem: str) -> dict[str, str]:
        """Upload pipeline output files to S3."""
        from src.storage import S3Uploader

        s3_prefix = f"{self.config.s3_prefix}/{stem}"
        uploader = S3Uploader(
            bucket=self.config.s3_bucket,
            prefix=s3_prefix,
        )
        urls = uploader.upload_pipeline_output(output_dir)
        logger.info("Uploaded %d files to S3: %s", len(urls), list(urls.keys()))
        return urls
