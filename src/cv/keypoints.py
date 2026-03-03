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
    """Estimates equine keypoints from bounding box + image contours.

    Phase 1 fallback when no custom equine pose model is available.
    Uses a two-step approach:
    1. Initial placement via anatomical proportions relative to the bbox
       (corrected for the jockey occupying the top ~20% of the box).
    2. Contour-based refinement: segments the horse foreground, traces
       the topline and locates the lowest limb extremities (hooves)
       to snap keypoints onto the actual horse outline.

    Phase 2 will replace this with a fine-tuned YOLO-Pose equine model.
    """

    # Relative (rx, ry) proportions inside the bounding box for a horse
    # facing RIGHT.  rx: 0 = left edge (rear), 1 = right edge (front).
    # ry: 0 = top edge, 1 = bottom edge.
    # When the horse faces LEFT, rx is mirrored (1 - rx).
    #
    # IMPORTANT: ry values account for the jockey occupying the top ~20%
    # of the bbox.  The horse's topline sits at ry ≈ 0.22, not ry ≈ 0.
    _PROPORTIONS_FACING_RIGHT: dict[str, tuple[float, float]] = {
        # Head / topline  —  shifted DOWN from jockey level
        "poll":           (0.97, 0.22),
        "nose":           (1.00, 0.38),
        "throat":         (0.93, 0.36),
        "withers":        (0.72, 0.22),
        "mid_back":       (0.52, 0.24),
        "croup":          (0.33, 0.20),
        "tail_base":      (0.18, 0.26),
        # Left forelimb  —  roughly vertical below shoulder
        "l_shoulder":     (0.70, 0.40),
        "l_elbow":        (0.71, 0.52),
        "l_knee_fore":    (0.73, 0.66),
        "l_fetlock_fore": (0.74, 0.82),
        "l_fore_hoof":    (0.75, 0.97),
        # Right forelimb  —  slightly offset (far-side)
        "r_shoulder":     (0.68, 0.38),
        "r_elbow":        (0.69, 0.50),
        "r_knee_fore":    (0.71, 0.64),
        "r_fetlock_fore": (0.72, 0.80),
        "r_fore_hoof":    (0.73, 0.95),
        # Left hindlimb  —  angled slightly rearward
        "l_hip":          (0.36, 0.36),
        "l_hock":         (0.33, 0.58),
        "l_hind_fetlock": (0.30, 0.80),
        "l_hind_hoof":    (0.28, 0.97),
        # Right hindlimb  —  slightly offset
        "r_hip":          (0.38, 0.34),
        "r_hock":         (0.35, 0.56),
        "r_hind_hoof":    (0.32, 0.95),
    }

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
            kpts, conf = self._refine_with_contours(frame, det.bbox, kpts, conf, facing_right)
            results.append(KeypointResult(
                keypoints=kpts,
                confidence=conf,
                bbox=det.bbox,
                track_id=det.track_id,
            ))
        return results

    # ------------------------------------------------------------------
    def _detect_direction(self, frame: np.ndarray, det: Detection) -> bool:
        """Detect whether the horse faces right or left.

        Uses the middle band of the bbox (ry 0.20–0.50, the horse's body
        excluding jockey helmet and legs) to compare edge density in each half.
        """
        x1, y1, x2, y2 = det.bbox.astype(int)
        h, w = frame.shape[:2]
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(w, x2), min(h, y2)
        bh = y2 - y1

        # Middle band: 20–50% of bbox height (horse body, not jockey or legs)
        band_top = y1 + int(bh * 0.20)
        band_bot = y1 + int(bh * 0.50)
        band = frame[band_top:band_bot, x1:x2]

        if band.size == 0:
            return True

        gray = cv2.cvtColor(band, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, 50, 150)

        mid_x = edges.shape[1] // 2
        left_energy = float(edges[:, :mid_x].sum())
        right_energy = float(edges[:, mid_x:].sum())

        return right_energy > left_energy

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

            is_topline = kp_id <= 6
            conf[kp_id] = self._CONF_TOPLINE if is_topline else self._CONF_LIMB

        return kpts, conf

    # ------------------------------------------------------------------
    def _refine_with_contours(
        self,
        frame: np.ndarray,
        bbox: np.ndarray,
        kpts: np.ndarray,
        conf: np.ndarray,
        facing_right: bool,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Refine keypoint positions using the horse's foreground contour.

        1. Segments the horse body from the background using adaptive
           thresholding on the bbox crop.
        2. Traces the topline (uppermost foreground row at each column).
        3. Snaps topline keypoints (withers, mid_back, croup) onto the
           detected topline contour.
        4. Finds the lowest foreground pixels in each limb column band
           to refine hoof positions.
        """
        x1, y1, x2, y2 = bbox.astype(int)
        h, w = frame.shape[:2]
        x1c, y1c = max(0, x1), max(0, y1)
        x2c, y2c = min(w, x2), min(h, y2)
        crop = frame[y1c:y2c, x1c:x2c]

        if crop.size == 0:
            return kpts, conf

        bh, bw_px = crop.shape[:2]
        if bh < 20 or bw_px < 20:
            return kpts, conf

        # --- Build foreground mask ---
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        # Use Otsu to separate foreground (horse) from background (track/sky)
        _, fg_mask = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        # Also try edge-based fill
        edges = cv2.Canny(gray, 40, 120)
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
        edges_dilated = cv2.dilate(edges, kernel, iterations=2)
        # Combine: foreground OR strong edges
        combined = cv2.bitwise_or(fg_mask, edges_dilated)
        combined = cv2.morphologyEx(combined, cv2.MORPH_CLOSE, kernel, iterations=3)

        # --- Trace topline (uppermost foreground row per column) ---
        # Only look in the horse body region (ry 0.12 to 0.45)
        body_top = int(bh * 0.12)
        body_bot = int(bh * 0.45)
        body_band = combined[body_top:body_bot, :]

        topline_y = np.full(bw_px, -1, dtype=np.float32)
        for col in range(bw_px):
            col_pixels = body_band[:, col]
            fg_rows = np.where(col_pixels > 0)[0]
            if len(fg_rows) > 0:
                topline_y[col] = body_top + fg_rows[0]

        # Smooth the topline to remove noise
        valid_cols = topline_y >= 0
        if valid_cols.sum() > 10:
            # Interpolate gaps and smooth
            valid_x = np.where(valid_cols)[0]
            valid_vals = topline_y[valid_cols]
            # Simple moving average (window=15% of bbox width)
            win = max(5, bw_px // 7)
            if len(valid_vals) > win:
                smoothed = np.convolve(valid_vals, np.ones(win) / win, mode="same")
                topline_y[valid_x] = smoothed

            # Snap topline keypoints: withers (3), mid_back (4), croup (5)
            for kp_id in [3, 4, 5]:
                kx_frame = kpts[kp_id, 0]
                col_in_crop = int(kx_frame - x1c)
                col_in_crop = np.clip(col_in_crop, 0, bw_px - 1)

                # Search a ±8% window around the expected column
                search_w = max(5, bw_px // 12)
                c_lo = max(0, col_in_crop - search_w)
                c_hi = min(bw_px, col_in_crop + search_w)
                window = topline_y[c_lo:c_hi]
                valid_window = window[window >= 0]

                if len(valid_window) > 0:
                    best_y_crop = float(valid_window.min())  # highest point in window
                    kpts[kp_id, 1] = y1c + best_y_crop
                    conf[kp_id] = min(0.75, conf[kp_id] + 0.10)  # boost confidence

        # --- Refine hoof positions (lowest foreground per limb column) ---
        # Only look in the lower portion (ry 0.70 to 1.0)
        leg_top = int(bh * 0.70)
        leg_band = combined[leg_top:bh, :]

        hoof_ids = [11, 16, 20, 23]  # l_fore, r_fore, l_hind, r_hind hooves
        for kp_id in hoof_ids:
            if conf[kp_id] <= 0:
                continue
            kx_frame = kpts[kp_id, 0]
            col_in_crop = int(kx_frame - x1c)
            col_in_crop = np.clip(col_in_crop, 0, bw_px - 1)

            search_w = max(8, bw_px // 8)
            c_lo = max(0, col_in_crop - search_w)
            c_hi = min(bw_px, col_in_crop + search_w)

            for col in range(c_lo, c_hi):
                col_pixels = leg_band[:, col]
                fg_rows = np.where(col_pixels > 0)[0]
                if len(fg_rows) > 0:
                    lowest_y_crop = leg_top + int(fg_rows[-1])
                    if lowest_y_crop > (kpts[kp_id, 1] - y1c):
                        kpts[kp_id, 1] = y1c + lowest_y_crop
                        conf[kp_id] = min(0.65, conf[kp_id] + 0.05)

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
