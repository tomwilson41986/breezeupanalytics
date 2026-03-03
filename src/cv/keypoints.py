"""Equine keypoint estimation.

Provides keypoint detection for horses using either:
- A custom fine-tuned equine YOLO-Pose model (24-keypoint schema) — Phase 2+
- Bounding-box anatomical heuristics (Phase 1 fallback when no equine model)

The pipeline uses a top-down approach:
1. Detect horse bounding boxes (via detection.py)
2. Estimate equine keypoints on each detected horse
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np
import torch
from ultralytics import YOLO

from src.cv.detection import Detection, crop_detection
from src.cv.schema import KEYPOINT_NAME_TO_ID, NUM_KEYPOINTS, EquineKeypointSchema

logger = logging.getLogger(__name__)


@dataclass
class KeypointResult:
    """Keypoint predictions for a single horse."""
    keypoints: np.ndarray          # (N, 2) x,y coordinates in original frame space
    confidence: np.ndarray         # (N,) per-keypoint confidence scores
    bbox: np.ndarray               # [x1, y1, x2, y2] source bounding box
    track_id: int | None = None
    frame_idx: int = 0

    @property
    def num_visible(self) -> int:
        """Number of keypoints above the visibility threshold."""
        return int((self.confidence > 0.3).sum())

    def get_keypoint(self, name: str) -> tuple[float, float, float]:
        """Get (x, y, confidence) for a named keypoint."""
        idx = EquineKeypointSchema.name_to_id[name]
        return (
            float(self.keypoints[idx, 0]),
            float(self.keypoints[idx, 1]),
            float(self.confidence[idx]),
        )

    def visible_mask(self, threshold: float = 0.3) -> np.ndarray:
        """Boolean mask of keypoints above confidence threshold."""
        return self.confidence > threshold


@dataclass
class FrameKeypoints:
    """All keypoint results for a single frame."""
    frame_idx: int
    horses: list[KeypointResult] = field(default_factory=list)

    @property
    def num_horses(self) -> int:
        return len(self.horses)


class BBoxKeypointEstimator:
    """Estimates equine keypoints from bounding box anatomy — Phase 1 fallback.

    When no custom equine pose model is available, the COCO YOLO-Pose model
    detects the jockey (human) rather than the horse.  This estimator bypasses
    the pose model entirely and places 24 equine keypoints on the horse body
    using the detected bounding box and anatomical proportions for a
    side-on galloping Thoroughbred.

    The proportions are approximate but put keypoints on the *horse*, not the
    jockey.  Phase 2 will replace this with a fine-tuned YOLO-Pose equine model.
    """

    # Relative (rx, ry) proportions inside the bounding box for a horse
    # facing RIGHT.  rx: 0 = left edge (rear), 1 = right edge (front).
    # ry: 0 = top edge, 1 = bottom edge.
    # When the horse faces LEFT, rx is mirrored (1 - rx).
    _PROPORTIONS_FACING_RIGHT: dict[str, tuple[float, float]] = {
        # Head / topline
        "poll":           (0.95, 0.02),
        "nose":           (1.00, 0.20),
        "throat":         (0.90, 0.22),
        "withers":        (0.75, 0.00),
        "mid_back":       (0.55, 0.03),
        "croup":          (0.32, 0.00),
        "tail_base":      (0.15, 0.08),
        # Left forelimb (visible / near-side when facing right, camera on left)
        "l_shoulder":     (0.72, 0.30),
        "l_elbow":        (0.68, 0.48),
        "l_knee_fore":    (0.65, 0.65),
        "l_fetlock_fore": (0.62, 0.82),
        "l_fore_hoof":    (0.60, 0.97),
        # Right forelimb (far-side — slightly offset)
        "r_shoulder":     (0.74, 0.28),
        "r_elbow":        (0.70, 0.46),
        "r_knee_fore":    (0.67, 0.63),
        "r_fetlock_fore": (0.64, 0.80),
        "r_fore_hoof":    (0.62, 0.95),
        # Left hindlimb
        "l_hip":          (0.35, 0.28),
        "l_hock":         (0.30, 0.55),
        "l_hind_fetlock": (0.27, 0.78),
        "l_hind_hoof":    (0.25, 0.97),
        # Right hindlimb
        "r_hip":          (0.37, 0.26),
        "r_hock":         (0.32, 0.53),
        "r_hind_hoof":    (0.27, 0.95),
    }

    # Confidence assigned to heuristic keypoints (topline is more reliable
    # because the bbox captures the body outline; limbs are less certain).
    _CONF_TOPLINE = 0.6
    _CONF_LIMB = 0.45

    def __init__(self, confidence_threshold: float = 0.3):
        self.confidence_threshold = confidence_threshold

    def estimate(
        self,
        frame: np.ndarray,
        detections: list[Detection] | None = None,
    ) -> list[KeypointResult]:
        if not detections:
            return []

        results = []
        for det in detections:
            facing_right = self._detect_direction(frame, det)
            kpts, conf = self._place_keypoints(det.bbox, facing_right)
            results.append(KeypointResult(
                keypoints=kpts,
                confidence=conf,
                bbox=det.bbox,
                track_id=det.track_id,
            ))
        return results

    # ------------------------------------------------------------------
    def _detect_direction(self, frame: np.ndarray, det: Detection) -> bool:
        """Heuristic: detect whether the horse faces right or left.

        Uses the upper portion of the bounding box.  The head/neck area has
        more visual detail (mane, ears, bridle) than the tail end, so the
        half with higher edge density is the front.
        """
        x1, y1, x2, y2 = det.bbox.astype(int)
        h, w = frame.shape[:2]
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(w, x2), min(h, y2)

        # Upper 40% of the bbox (body, not legs)
        y_upper = y1 + int((y2 - y1) * 0.40)
        upper = frame[y1:y_upper, x1:x2]

        if upper.size == 0:
            return True

        gray = cv2.cvtColor(upper, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, 50, 150)

        mid_x = edges.shape[1] // 2
        left_energy = float(edges[:, :mid_x].sum())
        right_energy = float(edges[:, mid_x:].sum())

        return right_energy > left_energy  # more detail on right → facing right

    # ------------------------------------------------------------------
    def _place_keypoints(
        self, bbox: np.ndarray, facing_right: bool,
    ) -> tuple[np.ndarray, np.ndarray]:
        x1, y1, x2, y2 = bbox
        bw = x2 - x1
        bh = y2 - y1

        kpts = np.zeros((NUM_KEYPOINTS, 2), dtype=np.float32)
        conf = np.zeros(NUM_KEYPOINTS, dtype=np.float32)

        for name, (rx, ry) in self._PROPORTIONS_FACING_RIGHT.items():
            kp_id = KEYPOINT_NAME_TO_ID.get(name)
            if kp_id is None:
                continue

            if not facing_right:
                rx = 1.0 - rx

            kpts[kp_id, 0] = x1 + rx * bw
            kpts[kp_id, 1] = y1 + ry * bh

            # Topline keypoints get higher confidence
            is_topline = kp_id <= 6
            conf[kp_id] = self._CONF_TOPLINE if is_topline else self._CONF_LIMB

        return kpts, conf


class EquineKeypointEstimator:
    """Estimates equine keypoints using YOLO-Pose.

    Automatically detects whether the loaded model is a custom equine
    model (24 keypoints) or a COCO human pose model (17 keypoints).
    When using a human model, falls back to BBoxKeypointEstimator so
    that keypoints are placed on the horse rather than the jockey.

    For production use, set `model_path` to a custom-trained YOLO-Pose
    model with 24 equine keypoints.
    """

    def __init__(
        self,
        model_path: str = "yolo11n-pose.pt",
        confidence_threshold: float = 0.3,
        device: str | None = None,
        num_keypoints: int = NUM_KEYPOINTS,
    ):
        self.confidence_threshold = confidence_threshold
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.num_keypoints = num_keypoints

        logger.info("Loading keypoint model: %s on %s", model_path, self.device)
        self.model = YOLO(model_path)

        # Detect if this is a custom equine model or COCO-pose
        self._is_custom_equine = False
        self._bbox_fallback: BBoxKeypointEstimator | None = None
        try:
            model_kpt_shape = self.model.model.yaml.get("kpt_shape", [17, 3])
            if model_kpt_shape[0] == NUM_KEYPOINTS:
                self._is_custom_equine = True
                logger.info("Custom equine keypoint model detected (%d keypoints)", NUM_KEYPOINTS)
            else:
                logger.info(
                    "Model has %d keypoints (human pose). Using bbox-anatomy "
                    "estimator for horse keypoints (Phase 1 fallback).",
                    model_kpt_shape[0],
                )
                self._bbox_fallback = BBoxKeypointEstimator(confidence_threshold)
        except (AttributeError, TypeError):
            self._bbox_fallback = BBoxKeypointEstimator(confidence_threshold)

    def estimate(
        self,
        frame: np.ndarray,
        detections: list[Detection] | None = None,
    ) -> list[KeypointResult]:
        """Estimate keypoints for horses in a frame.

        If using a custom equine model: runs pose estimation on each crop.
        If using a COCO human model: falls back to bbox-based horse anatomy
        so keypoints land on the horse, not the jockey.

        Args:
            frame: BGR image (H, W, 3).
            detections: Optional pre-computed horse detections.

        Returns:
            List of KeypointResult, one per detected horse.
        """
        # Phase 1 fallback: use bbox heuristics instead of human pose model
        if self._bbox_fallback is not None:
            return self._bbox_fallback.estimate(frame, detections)

        # Custom equine model — use top-down YOLO-Pose
        if detections:
            return self._estimate_topdown(frame, detections)
        return self._estimate_bottomup(frame)

    def _estimate_bottomup(self, frame: np.ndarray) -> list[KeypointResult]:
        """Run pose model directly on the full frame."""
        results = self.model(
            frame,
            conf=self.confidence_threshold,
            verbose=False,
            device=self.device,
        )

        keypoint_results = []
        for result in results:
            if result.keypoints is None or result.boxes is None:
                continue

            kpts_data = result.keypoints.data.cpu().numpy()  # (N, K, 3) x,y,conf
            boxes = result.boxes.xyxy.cpu().numpy()

            for i in range(len(boxes)):
                kpts_xy = kpts_data[i, :, :2]
                kpts_conf = kpts_data[i, :, 2]

                kr = KeypointResult(
                    keypoints=kpts_xy[:self.num_keypoints],
                    confidence=kpts_conf[:self.num_keypoints],
                    bbox=boxes[i],
                )
                keypoint_results.append(kr)

        return keypoint_results

    def _estimate_topdown(
        self, frame: np.ndarray, detections: list[Detection]
    ) -> list[KeypointResult]:
        """Run custom equine pose model on each cropped detection."""
        keypoint_results = []

        for det in detections:
            crop = crop_detection(frame, det, padding=0.15)
            if crop.size == 0:
                continue

            results = self.model(
                crop,
                conf=self.confidence_threshold,
                verbose=False,
                device=self.device,
            )

            for result in results:
                if result.keypoints is None:
                    continue

                kpts_data = result.keypoints.data.cpu().numpy()
                if len(kpts_data) == 0:
                    continue

                kpts_xy = kpts_data[0, :, :2]
                kpts_conf = kpts_data[0, :, 2]

                # Map crop coordinates back to original frame space
                x1, y1 = det.bbox[0], det.bbox[1]
                pad_w = det.width * 0.15
                pad_h = det.height * 0.15
                offset_x = max(0, x1 - pad_w)
                offset_y = max(0, y1 - pad_h)

                kpts_xy[:, 0] += offset_x
                kpts_xy[:, 1] += offset_y

                kr = KeypointResult(
                    keypoints=kpts_xy[:self.num_keypoints],
                    confidence=kpts_conf[:self.num_keypoints],
                    bbox=det.bbox,
                    track_id=det.track_id,
                )
                keypoint_results.append(kr)
                break  # one pose per detection

        return keypoint_results
