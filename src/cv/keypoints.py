"""Equine keypoint estimation.

Provides keypoint detection for horses using YOLO-Pose. Supports both
pretrained COCO-pose models (17 human keypoints as baseline) and custom
fine-tuned equine keypoint models (24-keypoint schema).

The pipeline uses a top-down approach:
1. Detect horse bounding boxes (via detection.py)
2. Run keypoint estimation on each cropped detection
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import torch
from ultralytics import YOLO

from src.cv.detection import Detection, crop_detection
from src.cv.schema import NUM_KEYPOINTS, EquineKeypointSchema

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


class EquineKeypointEstimator:
    """Estimates equine keypoints using YOLO-Pose.

    For Phase 1 (zero-shot), this uses a pretrained YOLO-Pose model.
    The COCO-pose model detects 17 human keypoints — we use it as a
    structural baseline and will replace it with a fine-tuned equine
    model in Phase 2.

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
        try:
            model_kpt_shape = self.model.model.yaml.get("kpt_shape", [17, 3])
            if model_kpt_shape[0] == NUM_KEYPOINTS:
                self._is_custom_equine = True
                logger.info("Custom equine keypoint model detected (%d keypoints)", NUM_KEYPOINTS)
            else:
                logger.info(
                    "Using pretrained model with %d keypoints (will adapt to %d equine keypoints in Phase 2)",
                    model_kpt_shape[0], NUM_KEYPOINTS,
                )
        except (AttributeError, TypeError):
            pass

    def estimate(
        self,
        frame: np.ndarray,
        detections: list[Detection] | None = None,
    ) -> list[KeypointResult]:
        """Estimate keypoints for horses in a frame.

        If detections are provided (top-down approach), runs pose estimation
        on each cropped bounding box. Otherwise, runs the pose model directly
        on the full frame.

        Args:
            frame: BGR image (H, W, 3).
            detections: Optional pre-computed horse detections.

        Returns:
            List of KeypointResult, one per detected horse.
        """
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
                    keypoints=self._adapt_keypoints(kpts_xy),
                    confidence=self._adapt_confidence(kpts_conf),
                    bbox=boxes[i],
                )
                keypoint_results.append(kr)

        return keypoint_results

    def _estimate_topdown(
        self, frame: np.ndarray, detections: list[Detection]
    ) -> list[KeypointResult]:
        """Run pose model on each cropped detection (top-down approach)."""
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

                # Use the first (highest-confidence) pose in the crop
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
                    keypoints=self._adapt_keypoints(kpts_xy),
                    confidence=self._adapt_confidence(kpts_conf),
                    bbox=det.bbox,
                    track_id=det.track_id,
                )
                keypoint_results.append(kr)
                break  # one pose per detection

        return keypoint_results

    def _adapt_keypoints(self, kpts: np.ndarray) -> np.ndarray:
        """Adapt model keypoints to our 24-point equine schema.

        If using a custom equine model, keypoints map directly.
        If using COCO-pose (17 keypoints), we pad to 24 with zeros
        and map the available points as best we can.
        """
        if self._is_custom_equine or kpts.shape[0] == self.num_keypoints:
            return kpts[:self.num_keypoints]

        # COCO-pose has 17 keypoints — create a zero-padded equine array.
        # This is a placeholder mapping; real production uses a fine-tuned model.
        equine_kpts = np.zeros((self.num_keypoints, 2), dtype=np.float32)

        # Approximate mapping from COCO (human) to equine body regions:
        # COCO: 0=nose, 5=l_shoulder, 6=r_shoulder, 7=l_elbow, 8=r_elbow,
        #        9=l_wrist, 10=r_wrist, 11=l_hip, 12=r_hip, 13=l_knee, 14=r_knee,
        #        15=l_ankle, 16=r_ankle
        # These don't map well to horse anatomy, but provide structural anchors
        # for visualization and pipeline testing.
        if kpts.shape[0] >= 17:
            equine_kpts[1] = kpts[0]     # nose -> nose
            equine_kpts[7] = kpts[5]     # l_shoulder
            equine_kpts[12] = kpts[6]    # r_shoulder
            equine_kpts[8] = kpts[7]     # l_elbow
            equine_kpts[13] = kpts[8]    # r_elbow
            equine_kpts[11] = kpts[9]    # l_fore_hoof (wrist proxy)
            equine_kpts[16] = kpts[10]   # r_fore_hoof (wrist proxy)
            equine_kpts[17] = kpts[11]   # l_hip
            equine_kpts[21] = kpts[12]   # r_hip
            equine_kpts[18] = kpts[13]   # l_hock (knee proxy)
            equine_kpts[22] = kpts[14]   # r_hock (knee proxy)
            equine_kpts[20] = kpts[15]   # l_hind_hoof (ankle proxy)
            equine_kpts[23] = kpts[16]   # r_hind_hoof (ankle proxy)

        return equine_kpts

    def _adapt_confidence(self, conf: np.ndarray) -> np.ndarray:
        """Adapt confidence scores to our 24-point schema."""
        if self._is_custom_equine or conf.shape[0] == self.num_keypoints:
            return conf[:self.num_keypoints]

        equine_conf = np.zeros(self.num_keypoints, dtype=np.float32)
        if conf.shape[0] >= 17:
            equine_conf[1] = conf[0]
            equine_conf[7] = conf[5]
            equine_conf[12] = conf[6]
            equine_conf[8] = conf[7]
            equine_conf[13] = conf[8]
            equine_conf[11] = conf[9]
            equine_conf[16] = conf[10]
            equine_conf[17] = conf[11]
            equine_conf[21] = conf[12]
            equine_conf[18] = conf[13]
            equine_conf[22] = conf[14]
            equine_conf[20] = conf[15]
            equine_conf[23] = conf[16]

        return equine_conf
