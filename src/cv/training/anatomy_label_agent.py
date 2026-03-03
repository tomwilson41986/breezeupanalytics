"""Anatomy-aware auto-labeling agent for equine keypoints.

Wraps the base AutoLabelAgent with anatomical correction and validation,
producing higher-quality pseudo-labels for fine-tuning.

Pipeline:
    1. Base model predictions (ViTPose++ / ensemble)
    2. Anatomical validation (detect violations)
    3. Anatomical correction (fix impossible poses)
    4. Quality scoring (anatomy-weighted)
    5. Temporal consistency (for video sequences)
    6. YOLO-Pose label output

Usage:
    agent = AnatomyLabelAgent(source="vitpose")
    result = agent.label_video("video.mp4", "output/")
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

from src.cv.schema import KEYPOINT_NAMES, NUM_KEYPOINTS
from src.cv.training.anatomy import (
    AnatomyCorrector,
    AnatomyReport,
    AnatomyValidator,
    VERTICAL_ORDER,
    JOINT_ANGLE_RANGES,
    BONE_LENGTH_RATIOS,
)
from src.cv.training.auto_label import AutoLabelAgent, AutoLabelResult, PseudoLabel

logger = logging.getLogger(__name__)


@dataclass
class AnatomyLabelResult(AutoLabelResult):
    """Extended result with anatomy metrics."""
    mean_anatomy_score: float = 0.0
    total_violations: int = 0
    total_corrections: int = 0
    violations_by_rule: dict[str, int] = field(default_factory=dict)


class AnatomyLabelAgent:
    """Auto-labeling agent trained on horse anatomy.

    Extends AutoLabelAgent by:
    1. Running anatomical validation on every prediction
    2. Correcting anatomically impossible poses
    3. Scoring labels with anatomy-aware quality metrics
    4. Enforcing temporal consistency across video frames
    5. Flagging frames that need human review based on anatomy violations
    """

    def __init__(
        self,
        detection_confidence: float = 0.25,
        keypoint_confidence: float = 0.15,
        quality_threshold: float = 0.4,
        min_confident_kpts: int = 6,
        source: str = "ensemble",
        vitpose_size: str = "base",
        correction_strength: float = 0.7,
        temporal_window: int = 5,
    ):
        self.base_agent = AutoLabelAgent(
            detection_confidence=detection_confidence,
            keypoint_confidence=keypoint_confidence,
            quality_threshold=quality_threshold,
            min_confident_kpts=min_confident_kpts,
            source=source,
            vitpose_size=vitpose_size,
        )
        self.validator = AnatomyValidator(keypoint_confidence)
        self.corrector = AnatomyCorrector(
            confidence_threshold=keypoint_confidence,
            correction_strength=correction_strength,
        )
        self.keypoint_confidence = keypoint_confidence
        self.quality_threshold = quality_threshold
        self.min_confident_kpts = min_confident_kpts
        self.temporal_window = temporal_window

    def label_image(self, image_path: str | Path) -> list[PseudoLabel]:
        """Label a single image with anatomy-aware corrections.

        Steps:
        1. Get base predictions from AutoLabelAgent
        2. Validate against anatomy constraints
        3. Correct violations
        4. Rescore quality with anatomy weight
        """
        # Base predictions
        labels = self.base_agent.label_image(image_path)

        # Anatomy pass on each label
        corrected = []
        for label in labels:
            label = self._apply_anatomy(label)
            corrected.append(label)

        return corrected

    def label_directory(
        self,
        image_dir: str | Path,
        output_labels_dir: str | Path,
        review_dir: str | Path | None = None,
    ) -> AnatomyLabelResult:
        """Auto-label all images with anatomy corrections.

        Same interface as AutoLabelAgent.label_directory but with
        anatomy-aware post-processing.
        """
        image_dir = Path(image_dir)
        output_dir = Path(output_labels_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        if review_dir:
            review_dir = Path(review_dir)
            review_dir.mkdir(parents=True, exist_ok=True)

        image_paths = []
        for ext in ("*.jpg", "*.jpeg", "*.png", "*.bmp"):
            image_paths.extend(image_dir.glob(ext))
        image_paths.sort()

        result = AnatomyLabelResult(
            num_images=len(image_paths),
            labels_dir=str(output_dir),
        )

        all_qualities = []
        all_confident = []
        all_anatomy = []
        review_entries = []
        violation_counts: dict[str, int] = {}

        for img_path in image_paths:
            labels = self.label_image(img_path)

            if not labels:
                (output_dir / f"{img_path.stem}.txt").write_text("")
                continue

            result.num_labeled += 1
            result.num_horses += len(labels)

            img = cv2.imread(str(img_path))
            h, w = img.shape[:2]

            lines = []
            flagged = False

            for label in labels:
                all_qualities.append(label.quality_score)
                all_confident.append(label.num_confident)

                # Validate and track anatomy
                report = self.validator.validate(label.keypoints, label.confidence)
                all_anatomy.append(report.anatomy_score)
                for v in report.violations:
                    violation_counts[v.rule] = violation_counts.get(v.rule, 0) + 1
                    result.total_violations += 1

                line = self.base_agent._label_to_yolo_line(label, w, h)
                lines.append(line)

                if label.needs_review:
                    flagged = True
                    review_entries.append({
                        "image": img_path.name,
                        "quality": round(label.quality_score, 3),
                        "anatomy_score": round(report.anatomy_score, 3),
                        "confident_kpts": label.num_confident,
                        "violations": [v.message for v in report.violations],
                        "reasons": label.review_reasons,
                    })

            (output_dir / f"{img_path.stem}.txt").write_text("\n".join(lines))

            if flagged:
                result.num_flagged += 1
                if review_dir:
                    import shutil
                    shutil.copy2(img_path, review_dir / img_path.name)

        # Write review manifest
        if review_entries and output_dir:
            manifest = {
                "total_images": result.num_images,
                "flagged_for_review": len(review_entries),
                "quality_threshold": self.quality_threshold,
                "anatomy_violations_summary": violation_counts,
                "entries": review_entries,
            }
            manifest_path = output_dir / "review_manifest.json"
            with open(manifest_path, "w") as f:
                json.dump(manifest, f, indent=2)
            result.review_manifest = str(manifest_path)

        if all_qualities:
            result.mean_quality = float(np.mean(all_qualities))
        if all_confident:
            result.mean_confident_kpts = float(np.mean(all_confident))
        if all_anatomy:
            result.mean_anatomy_score = float(np.mean(all_anatomy))
        result.violations_by_rule = violation_counts

        logger.info(
            "AnatomyLabelAgent: %d images, %d labeled, %d horses, "
            "quality=%.3f, anatomy=%.3f, violations=%d, flagged=%d",
            result.num_images, result.num_labeled, result.num_horses,
            result.mean_quality, result.mean_anatomy_score,
            result.total_violations, result.num_flagged,
        )

        return result

    def label_video(
        self,
        video_path: str | Path,
        output_dir: str | Path,
        num_frames: int = 100,
        strategy: str = "uniform",
    ) -> AnatomyLabelResult:
        """Extract frames from a video and auto-label with anatomy corrections.

        Adds temporal consistency: smooths keypoint predictions across
        consecutive frames to reduce flicker.
        """
        from src.cv.training.dataset import extract_frames_for_labeling

        output_dir = Path(output_dir)
        images_dir = output_dir / "images"
        labels_dir = output_dir / "labels"
        review_dir = output_dir / "review"

        logger.info("Extracting %d frames from %s (%s)", num_frames, video_path, strategy)
        extract_frames_for_labeling(
            video_path,
            output_dir=images_dir,
            num_frames=num_frames,
            strategy=strategy,
        )

        # Label with anatomy corrections
        result = self.label_directory(images_dir, labels_dir, review_dir=review_dir)

        # Apply temporal smoothing to sequential labels
        self._apply_temporal_smoothing(labels_dir)

        return result

    def _apply_anatomy(self, label: PseudoLabel) -> PseudoLabel:
        """Apply anatomy validation and correction to a single label."""
        # Validate first
        pre_report = self.validator.validate(label.keypoints, label.confidence)

        if pre_report.violations:
            # Correct anatomical issues
            corrected_kpts, corrected_conf, post_report = self.corrector.correct(
                label.keypoints, label.confidence,
            )
            label.keypoints = corrected_kpts
            label.confidence = corrected_conf

        # Rescore with anatomy weight
        self._score_with_anatomy(label)
        return label

    def _score_with_anatomy(self, label: PseudoLabel) -> None:
        """Score quality incorporating anatomical plausibility.

        Quality = 0.20×coverage + 0.20×confidence + 0.20×topline + 0.15×limb + 0.25×anatomy
        """
        conf = label.confidence
        threshold = self.keypoint_confidence

        n_confident = int((conf >= threshold).sum())
        mean_conf = float(conf[conf >= threshold].mean()) if n_confident > 0 else 0.0

        coverage_score = n_confident / NUM_KEYPOINTS
        confidence_score = mean_conf

        # Topline completeness
        topline_ids = [3, 4, 5]
        topline_detected = sum(1 for i in topline_ids if conf[i] >= threshold)
        topline_score = topline_detected / len(topline_ids)

        # Limb completeness
        limb_chains = [
            [7, 8, 9, 10, 11], [12, 13, 14, 15, 16],
            [17, 18, 19, 20], [21, 22, 23],
        ]
        best_limb = 0.0
        for chain in limb_chains:
            detected = sum(1 for i in chain if conf[i] >= threshold)
            best_limb = max(best_limb, detected / len(chain))

        # Anatomy score
        report = self.validator.validate(label.keypoints, conf)
        anatomy_score = report.anatomy_score

        # Weighted quality
        quality = (
            0.20 * coverage_score
            + 0.20 * confidence_score
            + 0.20 * topline_score
            + 0.15 * best_limb
            + 0.25 * anatomy_score
        )

        label.quality_score = quality
        label.num_confident = n_confident

        # Flag for review
        reasons = []
        if quality < self.quality_threshold:
            reasons.append(f"low_quality ({quality:.2f})")
        if n_confident < self.min_confident_kpts:
            reasons.append(f"few_keypoints ({n_confident})")
        if topline_score < 0.33:
            reasons.append("missing_topline")
        if best_limb < 0.5:
            reasons.append("incomplete_limbs")
        if anatomy_score < 0.5:
            reasons.append(f"anatomy_violations ({report.num_severe} severe)")

        label.needs_review = len(reasons) > 0
        label.review_reasons = reasons

    def _apply_temporal_smoothing(self, labels_dir: Path) -> None:
        """Smooth keypoints across temporally adjacent frames.

        For sequential video frames, applies a weighted moving average
        to keypoint positions, reducing flicker in low-confidence joints.
        """
        label_files = sorted(labels_dir.glob("*.txt"))
        if len(label_files) < 3:
            return

        # Parse all labels into arrays
        all_kpts: list[np.ndarray | None] = []
        all_confs: list[np.ndarray | None] = []
        all_lines_prefix: list[str | None] = []  # bbox prefix per file

        for lf in label_files:
            text = lf.read_text().strip()
            if not text:
                all_kpts.append(None)
                all_confs.append(None)
                all_lines_prefix.append(None)
                continue

            # Take first horse only for temporal smoothing
            line = text.split("\n")[0]
            parts = line.strip().split()
            if len(parts) < 5 + NUM_KEYPOINTS * 3:
                all_kpts.append(None)
                all_confs.append(None)
                all_lines_prefix.append(None)
                continue

            prefix = " ".join(parts[:5])
            kpt_vals = parts[5:]

            kpts = np.zeros((NUM_KEYPOINTS, 2))
            confs = np.zeros(NUM_KEYPOINTS)
            for k in range(NUM_KEYPOINTS):
                idx = k * 3
                kpts[k, 0] = float(kpt_vals[idx])
                kpts[k, 1] = float(kpt_vals[idx + 1])
                confs[k] = float(kpt_vals[idx + 2]) / 2.0  # vis→conf approx

            all_kpts.append(kpts)
            all_confs.append(confs)
            all_lines_prefix.append(prefix)

        # Apply weighted temporal smoothing
        w = self.temporal_window
        smoothed_count = 0

        for i in range(len(all_kpts)):
            if all_kpts[i] is None:
                continue

            # Gather neighbors
            neighbors_kpts = []
            neighbors_weights = []

            for j in range(max(0, i - w), min(len(all_kpts), i + w + 1)):
                if all_kpts[j] is None:
                    continue
                # Weight: center frame highest, falloff with distance
                dist = abs(i - j)
                weight = 1.0 / (1.0 + dist)
                neighbors_kpts.append(all_kpts[j])
                neighbors_weights.append(weight)

            if len(neighbors_kpts) < 2:
                continue

            weights = np.array(neighbors_weights)
            weights /= weights.sum()

            stacked = np.stack(neighbors_kpts)  # (N, 24, 2)

            # Only smooth low-confidence keypoints
            for k in range(NUM_KEYPOINTS):
                if all_confs[i][k] < 0.4:  # low confidence → smooth
                    smoothed_pos = np.average(stacked[:, k], axis=0, weights=weights)
                    all_kpts[i][k] = smoothed_pos
                    smoothed_count += 1

        # Write back smoothed labels
        for i, lf in enumerate(label_files):
            if all_kpts[i] is None or all_lines_prefix[i] is None:
                continue

            kpts = all_kpts[i]
            parts = [all_lines_prefix[i]]
            for k in range(NUM_KEYPOINTS):
                x, y = kpts[k]
                # Determine visibility from original
                original_text = lf.read_text().strip().split("\n")[0].split()
                vis_idx = 5 + k * 3 + 2
                vis = original_text[vis_idx] if vis_idx < len(original_text) else "0"
                parts.append(f"{x:.6f} {y:.6f} {vis}")

            lf.write_text(" ".join(parts))

        if smoothed_count > 0:
            logger.info("Temporal smoothing: adjusted %d keypoint positions", smoothed_count)
