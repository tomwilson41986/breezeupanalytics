"""Auto-labeling agent for equine keypoint annotation.

Uses pretrained models to automatically generate pseudo-labels for training
data, dramatically reducing manual annotation effort. The workflow:

1. Run multiple pretrained models (YOLO-Pose, optionally DLC SuperAnimal)
2. Ensemble predictions with confidence-weighted averaging
3. Map detected keypoints to the 24-point equine schema
4. Score each annotation by quality (confidence, completeness, consistency)
5. Write YOLO-Pose format labels
6. Flag low-quality annotations for human review

Typical usage:
    agent = AutoLabelAgent()
    result = agent.label_directory("data/images", "data/labels")
    print(f"Auto-labeled {result.num_labeled}, flagged {result.num_flagged} for review")
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

from src.cv.schema import KEYPOINT_NAMES, NUM_KEYPOINTS

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Keypoint mapping tables: pretrained model keypoints -> equine 24-point schema
# ---------------------------------------------------------------------------

# COCO human pose (17 kpts) -> equine schema (approximate structural mapping)
# Used when running YOLO-Pose with COCO weights on horse images.
COCO_TO_EQUINE_MAP: dict[int, int] = {
    0: 1,     # nose -> nose
    5: 7,     # l_shoulder -> l_shoulder
    6: 12,    # r_shoulder -> r_shoulder
    7: 8,     # l_elbow -> l_elbow
    8: 13,    # r_elbow -> r_elbow
    9: 11,    # l_wrist -> l_fore_hoof
    10: 16,   # r_wrist -> r_fore_hoof
    11: 17,   # l_hip -> l_hip
    12: 21,   # r_hip -> r_hip
    13: 18,   # l_knee -> l_hock
    14: 22,   # r_knee -> r_hock
    15: 20,   # l_ankle -> l_hind_hoof
    16: 23,   # r_ankle -> r_hind_hoof
}

# AP-10K / Animal Pose (17 kpts) -> equine schema
# This mapping is used when ViTPose or similar animal-pose models are available.
AP10K_TO_EQUINE_MAP: dict[int, int] = {
    0: 1,     # nose -> nose
    1: 0,     # l_eye -> poll (approximate)
    2: 0,     # r_eye -> poll (approximate)
    3: 2,     # l_ear_base -> throat (approximate)
    4: 2,     # r_ear_base -> throat (approximate)
    5: 7,     # l_shoulder -> l_shoulder
    6: 12,    # r_shoulder -> r_shoulder
    7: 8,     # l_elbow -> l_elbow
    8: 13,    # r_elbow -> r_elbow
    9: 11,    # l_front_paw -> l_fore_hoof
    10: 16,   # r_front_paw -> r_fore_hoof
    11: 17,   # l_hip -> l_hip
    12: 21,   # r_hip -> r_hip
    13: 18,   # l_knee -> l_hock
    14: 22,   # r_knee -> r_hock
    15: 20,   # l_back_paw -> l_hind_hoof
    16: 23,   # r_back_paw -> r_hind_hoof
}

# DLC SuperAnimal-Quadruped (39 kpts) -> equine schema
# SuperAnimal has the richest keypoint set; best zero-shot mapping.
DLC_SUPERANIMAL_TO_EQUINE_MAP: dict[str, int] = {
    "nose": 1,
    "top_of_head": 0,          # -> poll
    "throat": 2,
    "withers": 3,
    "spine_mid": 4,            # -> mid_back
    "tail_base": 6,
    "hip_mid": 5,              # -> croup
    "L_F_shoulder": 7,
    "L_F_elbow": 8,
    "L_F_knee": 9,
    "L_F_paw": 11,             # -> l_fore_hoof
    "R_F_shoulder": 12,
    "R_F_elbow": 13,
    "R_F_knee": 14,
    "R_F_paw": 16,             # -> r_fore_hoof
    "L_B_hip": 17,
    "L_B_knee": 18,            # -> l_hock
    "L_B_paw": 20,             # -> l_hind_hoof
    "R_B_hip": 21,
    "R_B_knee": 22,            # -> r_hock
    "R_B_paw": 23,             # -> r_hind_hoof
}


@dataclass
class PseudoLabel:
    """A single auto-generated label for one horse in one image."""
    bbox: np.ndarray                # [x1, y1, x2, y2] pixel coords
    keypoints: np.ndarray           # (24, 2) x,y pixel coords
    confidence: np.ndarray          # (24,) per-keypoint confidence
    quality_score: float = 0.0      # overall quality (0-1)
    num_confident: int = 0          # keypoints above threshold
    needs_review: bool = False      # flagged for human review
    review_reasons: list[str] = field(default_factory=list)


@dataclass
class AutoLabelResult:
    """Summary of an auto-labeling run."""
    num_images: int = 0
    num_labeled: int = 0           # images with at least one label
    num_horses: int = 0            # total horse detections
    num_flagged: int = 0           # labels flagged for review
    mean_quality: float = 0.0
    mean_confident_kpts: float = 0.0
    labels_dir: str = ""
    review_manifest: str = ""


class AutoLabelAgent:
    """Auto-labeling agent using pretrained models for pseudo-label generation.

    Runs YOLO detection + pose estimation on unlabeled images, maps predictions
    to the 24-keypoint equine schema, and writes YOLO-Pose format labels.

    Optionally ensembles multiple models and uses geometric heuristics to
    infer keypoints that pretrained models don't directly predict (e.g. withers,
    mid-back, fetlocks).
    """

    def __init__(
        self,
        detection_model: str = "yolo11n.pt",
        pose_model: str = "yolo11n-pose.pt",
        detection_confidence: float = 0.4,
        keypoint_confidence: float = 0.2,
        quality_threshold: float = 0.4,
        min_confident_kpts: int = 8,
    ):
        """
        Args:
            detection_model: YOLO model for horse detection.
            pose_model: YOLO-Pose model for keypoint estimation.
            detection_confidence: Minimum detection confidence.
            keypoint_confidence: Minimum per-keypoint confidence for "confident".
            quality_threshold: Labels below this quality score get flagged.
            min_confident_kpts: Minimum confident keypoints to accept a label.
        """
        self.detection_model_path = detection_model
        self.pose_model_path = pose_model
        self.detection_confidence = detection_confidence
        self.keypoint_confidence = keypoint_confidence
        self.quality_threshold = quality_threshold
        self.min_confident_kpts = min_confident_kpts

        self._detector = None
        self._pose_model = None

    def _init_models(self):
        """Lazy-load models on first use."""
        if self._detector is None:
            from src.cv.detection import HorseDetector
            self._detector = HorseDetector(
                model_path=self.detection_model_path,
                confidence_threshold=self.detection_confidence,
            )
        if self._pose_model is None:
            from ultralytics import YOLO
            self._pose_model = YOLO(self.pose_model_path)

    def label_image(self, image_path: str | Path) -> list[PseudoLabel]:
        """Generate pseudo-labels for all horses in a single image.

        Args:
            image_path: Path to image file.

        Returns:
            List of PseudoLabel, one per detected horse.
        """
        self._init_models()
        assert self._detector is not None
        assert self._pose_model is not None

        frame = cv2.imread(str(image_path))
        if frame is None:
            logger.warning("Failed to read image: %s", image_path)
            return []

        h, w = frame.shape[:2]

        # Step 1: Detect horses
        detections = self._detector.detect(frame)
        if not detections:
            return []

        labels = []

        for det in detections:
            # Step 2: Crop and run pose estimation
            pseudo = self._estimate_and_map(frame, det, h, w)
            if pseudo is not None:
                # Step 3: Infer missing keypoints via geometry
                self._infer_missing_keypoints(pseudo)

                # Step 4: Score quality
                self._score_quality(pseudo)

                labels.append(pseudo)

        return labels

    def label_directory(
        self,
        image_dir: str | Path,
        output_labels_dir: str | Path,
        review_dir: str | Path | None = None,
    ) -> AutoLabelResult:
        """Auto-label all images in a directory.

        Args:
            image_dir: Directory containing images to label.
            output_labels_dir: Directory for YOLO-Pose label files.
            review_dir: Optional directory to copy images needing review.

        Returns:
            AutoLabelResult with counts and paths.
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

        result = AutoLabelResult(
            num_images=len(image_paths),
            labels_dir=str(output_dir),
        )

        all_qualities = []
        all_confident = []
        review_entries = []

        for img_path in image_paths:
            labels = self.label_image(img_path)

            if not labels:
                # Write empty label file
                (output_dir / f"{img_path.stem}.txt").write_text("")
                continue

            result.num_labeled += 1
            result.num_horses += len(labels)

            # Read image dimensions
            img = cv2.imread(str(img_path))
            h, w = img.shape[:2]

            lines = []
            flagged = False

            for label in labels:
                all_qualities.append(label.quality_score)
                all_confident.append(label.num_confident)

                line = self._label_to_yolo_line(label, w, h)
                lines.append(line)

                if label.needs_review:
                    flagged = True
                    review_entries.append({
                        "image": img_path.name,
                        "quality": round(label.quality_score, 3),
                        "confident_kpts": label.num_confident,
                        "reasons": label.review_reasons,
                    })

            # Write label file
            (output_dir / f"{img_path.stem}.txt").write_text("\n".join(lines))

            if flagged:
                result.num_flagged += 1
                if review_dir:
                    import shutil
                    shutil.copy2(img_path, review_dir / img_path.name)

        # Write review manifest
        if review_entries:
            manifest_path = output_dir / "review_manifest.json"
            with open(manifest_path, "w") as f:
                json.dump({
                    "total_images": result.num_images,
                    "flagged_for_review": len(review_entries),
                    "quality_threshold": self.quality_threshold,
                    "entries": review_entries,
                }, f, indent=2)
            result.review_manifest = str(manifest_path)

        if all_qualities:
            result.mean_quality = float(np.mean(all_qualities))
        if all_confident:
            result.mean_confident_kpts = float(np.mean(all_confident))

        logger.info(
            "Auto-labeling complete: %d images, %d horses, %d flagged (mean quality %.2f)",
            result.num_images, result.num_horses, result.num_flagged, result.mean_quality,
        )

        return result

    def label_video(
        self,
        video_path: str | Path,
        output_dir: str | Path,
        num_frames: int = 100,
        strategy: str = "uniform",
    ) -> AutoLabelResult:
        """Extract frames from a video and auto-label them.

        Combines frame extraction and auto-labeling in a single step.

        Args:
            video_path: Path to video file.
            output_dir: Output directory (will contain images/ and labels/).
            num_frames: Number of frames to extract and label.
            strategy: Frame selection strategy ("uniform", "random", "motion").

        Returns:
            AutoLabelResult.
        """
        from src.cv.training.dataset import extract_frames_for_labeling

        output_dir = Path(output_dir)
        images_dir = output_dir / "images"
        labels_dir = output_dir / "labels"
        review_dir = output_dir / "review"

        # Extract frames
        logger.info("Extracting %d frames from %s (%s strategy)", num_frames, video_path, strategy)
        extract_frames_for_labeling(
            video_path,
            output_dir=images_dir,
            num_frames=num_frames,
            strategy=strategy,
        )

        # Auto-label extracted frames
        return self.label_directory(images_dir, labels_dir, review_dir=review_dir)

    def _estimate_and_map(
        self,
        frame: np.ndarray,
        det,
        img_h: int,
        img_w: int,
    ) -> PseudoLabel | None:
        """Run pose estimation on a detected horse and map to equine schema."""
        from src.cv.detection import crop_detection

        crop = crop_detection(frame, det, padding=0.15)
        if crop.size == 0:
            return None

        results = self._pose_model(
            crop,
            conf=self.keypoint_confidence,
            verbose=False,
        )

        for result in results:
            if result.keypoints is None:
                continue

            kpts_data = result.keypoints.data.cpu().numpy()
            if len(kpts_data) == 0:
                continue

            raw_kpts = kpts_data[0, :, :2]    # (K, 2)
            raw_conf = kpts_data[0, :, 2]     # (K,)

            # Map crop coords to frame coords
            x1, y1 = det.bbox[0], det.bbox[1]
            pad_w = (det.bbox[2] - det.bbox[0]) * 0.15
            pad_h = (det.bbox[3] - det.bbox[1]) * 0.15
            offset_x = max(0, x1 - pad_w)
            offset_y = max(0, y1 - pad_h)

            raw_kpts[:, 0] += offset_x
            raw_kpts[:, 1] += offset_y

            # Map to equine schema
            equine_kpts = np.zeros((NUM_KEYPOINTS, 2), dtype=np.float32)
            equine_conf = np.zeros(NUM_KEYPOINTS, dtype=np.float32)

            src_count = raw_kpts.shape[0]
            mapping = COCO_TO_EQUINE_MAP if src_count <= 17 else COCO_TO_EQUINE_MAP

            for src_id, dst_id in mapping.items():
                if src_id < src_count:
                    equine_kpts[dst_id] = raw_kpts[src_id]
                    equine_conf[dst_id] = raw_conf[src_id]

            return PseudoLabel(
                bbox=det.bbox.copy(),
                keypoints=equine_kpts,
                confidence=equine_conf,
            )

        return None

    def _infer_missing_keypoints(self, label: PseudoLabel) -> None:
        """Use geometric heuristics to infer keypoints not directly predicted.

        For example, infer withers from shoulder midpoint, mid-back from
        withers-croup midpoint, fetlocks from knee-hoof midpoints, etc.
        """
        kpts = label.keypoints
        conf = label.confidence
        threshold = self.keypoint_confidence

        # Withers (3): midpoint above shoulders, slightly behind
        l_sh, r_sh = 7, 12
        if conf[3] < threshold and conf[l_sh] >= threshold and conf[r_sh] >= threshold:
            kpts[3] = (kpts[l_sh] + kpts[r_sh]) / 2
            kpts[3, 1] -= abs(kpts[l_sh, 1] - kpts[r_sh, 1]) * 0.5  # shift up
            conf[3] = min(conf[l_sh], conf[r_sh]) * 0.7
        elif conf[3] < threshold and conf[l_sh] >= threshold:
            kpts[3] = kpts[l_sh].copy()
            kpts[3, 1] -= 20  # rough offset upward
            conf[3] = conf[l_sh] * 0.5

        # Croup (5): midpoint above hips
        l_hip, r_hip = 17, 21
        if conf[5] < threshold and conf[l_hip] >= threshold and conf[r_hip] >= threshold:
            kpts[5] = (kpts[l_hip] + kpts[r_hip]) / 2
            kpts[5, 1] -= abs(kpts[l_hip, 1] - kpts[r_hip, 1]) * 0.5
            conf[5] = min(conf[l_hip], conf[r_hip]) * 0.7

        # Mid-back (4): midpoint between withers and croup
        if conf[4] < threshold and conf[3] >= threshold and conf[5] >= threshold:
            kpts[4] = (kpts[3] + kpts[5]) / 2
            conf[4] = min(conf[3], conf[5]) * 0.8

        # Tail base (6): extrapolate from croup away from withers
        if conf[6] < threshold and conf[5] >= threshold and conf[4] >= threshold:
            direction = kpts[5] - kpts[4]
            kpts[6] = kpts[5] + direction * 0.4
            conf[6] = conf[5] * 0.5

        # Poll (0): above and forward of throat
        if conf[0] < threshold and conf[2] >= threshold and conf[1] >= threshold:
            kpts[0] = kpts[2] + (kpts[1] - kpts[2]) * 0.3
            kpts[0, 1] -= 30  # shift up
            conf[0] = min(conf[1], conf[2]) * 0.5

        # Throat (2): between poll and withers
        if conf[2] < threshold and conf[0] >= threshold and conf[3] >= threshold:
            kpts[2] = kpts[0] * 0.4 + kpts[3] * 0.6
            conf[2] = min(conf[0], conf[3]) * 0.6

        # Fore fetlocks (10, 15): midpoint between knee and hoof
        for knee, fetlock, hoof in [(9, 10, 11), (14, 15, 16)]:
            if conf[fetlock] < threshold and conf[knee] >= threshold and conf[hoof] >= threshold:
                kpts[fetlock] = (kpts[knee] + kpts[hoof]) / 2
                conf[fetlock] = min(conf[knee], conf[hoof]) * 0.7

        # Hind fetlocks (19): midpoint between hock and hoof
        for hock, fetlock, hoof in [(18, 19, 20)]:
            if conf[fetlock] < threshold and conf[hock] >= threshold and conf[hoof] >= threshold:
                kpts[fetlock] = (kpts[hock] + kpts[hoof]) / 2
                conf[fetlock] = min(conf[hock], conf[hoof]) * 0.7

        # Fore knee (9, 14): midpoint between elbow and fetlock/hoof
        for elbow, knee, target in [(8, 9, 11), (13, 14, 16)]:
            if conf[knee] < threshold and conf[elbow] >= threshold and conf[target] >= threshold:
                kpts[knee] = (kpts[elbow] + kpts[target]) / 2
                conf[knee] = min(conf[elbow], conf[target]) * 0.6

    def _score_quality(self, label: PseudoLabel) -> None:
        """Score the quality of a pseudo-label and flag for review if needed."""
        conf = label.confidence
        threshold = self.keypoint_confidence

        n_confident = int((conf >= threshold).sum())
        mean_conf = float(conf[conf >= threshold].mean()) if n_confident > 0 else 0.0

        # Quality components
        coverage_score = n_confident / NUM_KEYPOINTS  # how many keypoints detected
        confidence_score = mean_conf                   # how confident are they
        # Bonus for topline completeness (withers, croup, mid-back = critical for gait)
        topline_ids = [3, 4, 5]
        topline_detected = sum(1 for i in topline_ids if conf[i] >= threshold)
        topline_score = topline_detected / len(topline_ids)

        # Bonus for having at least one complete limb chain
        limb_chains = [
            [7, 8, 9, 10, 11],   # l_fore
            [12, 13, 14, 15, 16], # r_fore
            [17, 18, 19, 20],     # l_hind
            [21, 22, 23],         # r_hind
        ]
        best_limb_completeness = 0.0
        for chain in limb_chains:
            detected = sum(1 for i in chain if conf[i] >= threshold)
            best_limb_completeness = max(best_limb_completeness, detected / len(chain))

        # Weighted quality score
        quality = (
            0.30 * coverage_score
            + 0.25 * confidence_score
            + 0.25 * topline_score
            + 0.20 * best_limb_completeness
        )

        label.quality_score = quality
        label.num_confident = n_confident

        # Flag for review
        reasons = []
        if quality < self.quality_threshold:
            reasons.append(f"low_quality ({quality:.2f} < {self.quality_threshold})")
        if n_confident < self.min_confident_kpts:
            reasons.append(f"few_keypoints ({n_confident} < {self.min_confident_kpts})")
        if topline_score < 0.33:
            reasons.append("missing_topline")
        if best_limb_completeness < 0.5:
            reasons.append("incomplete_limbs")

        label.needs_review = len(reasons) > 0
        label.review_reasons = reasons

    def _label_to_yolo_line(
        self,
        label: PseudoLabel,
        img_w: int,
        img_h: int,
    ) -> str:
        """Convert a PseudoLabel to a YOLO-Pose format line.

        Format: class cx cy w h kp0_x kp0_y kp0_v kp1_x kp1_y kp1_v ...
        All coordinates normalized to [0, 1].
        """
        x1, y1, x2, y2 = label.bbox
        cx = ((x1 + x2) / 2) / img_w
        cy = ((y1 + y2) / 2) / img_h
        bw = (x2 - x1) / img_w
        bh = (y2 - y1) / img_h

        parts = [f"0 {cx:.6f} {cy:.6f} {bw:.6f} {bh:.6f}"]

        for k in range(NUM_KEYPOINTS):
            kx = label.keypoints[k, 0] / img_w
            ky = label.keypoints[k, 1] / img_h
            # Visibility: 0=not labeled, 1=occluded, 2=visible
            if label.confidence[k] >= self.keypoint_confidence:
                vis = 2
            elif label.confidence[k] > 0:
                vis = 1  # inferred but low confidence
            else:
                vis = 0
            parts.append(f"{kx:.6f} {ky:.6f} {vis}")

        return " ".join(parts)
