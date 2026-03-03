"""ViTPose++ keypoint estimation for horses.

Uses the HuggingFace transformers ViTPose++ model with the AP-10K animal
keypoint head (dataset_index=3) to detect 17 anatomical keypoints on horses
zero-shot, then maps them to our 24-keypoint equine schema.

Replaces the BBoxKeypointEstimator heuristic with a real learned model —
no custom training required.

AP-10K 17 keypoints (generic quadruped):
    0: left_eye        1: right_eye       2: nose
    3: neck            4: root_of_tail    5: left_shoulder
    6: left_elbow      7: left_front_paw  8: right_shoulder
    9: right_elbow    10: right_front_paw 11: left_hip
   12: left_knee      13: left_back_paw  14: right_hip
   15: right_knee     16: right_back_paw

Our 24-keypoint equine schema:
    0: poll           1: nose            2: throat
    3: withers        4: mid_back        5: croup
    6: tail_base      7: l_shoulder      8: l_elbow
    9: l_knee_fore   10: l_fetlock_fore 11: l_fore_hoof
   12: r_shoulder    13: r_elbow        14: r_knee_fore
   15: r_fetlock_fore 16: r_fore_hoof   17: l_hip
   18: l_hock        19: l_hind_fetlock 20: l_hind_hoof
   21: r_hip         22: r_hock         23: r_hind_hoof
"""

from __future__ import annotations

import logging

import cv2
import numpy as np
import torch
from PIL import Image

from src.cv.detection import Detection
from src.cv.keypoints import KeypointResult
from src.cv.schema import NUM_KEYPOINTS

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# AP-10K (17) → Equine Schema (24) mapping
# ---------------------------------------------------------------------------

# Direct mappings: AP-10K index → our equine keypoint index
_DIRECT_MAP: dict[int, int] = {
    2: 1,    # nose → nose
    3: 3,    # neck → withers (closest topline landmark)
    4: 6,    # root_of_tail → tail_base
    5: 7,    # left_shoulder → l_shoulder
    6: 8,    # left_elbow → l_elbow
    7: 11,   # left_front_paw → l_fore_hoof
    8: 12,   # right_shoulder → r_shoulder
    9: 13,   # right_elbow → r_elbow
    10: 16,  # right_front_paw → r_fore_hoof
    11: 17,  # left_hip → l_hip (stifle)
    12: 18,  # left_knee → l_hock
    13: 20,  # left_back_paw → l_hind_hoof
    14: 21,  # right_hip → r_hip (stifle)
    15: 22,  # right_knee → r_hock
    16: 23,  # right_back_paw → r_hind_hoof
}

# Interpolated keypoints: (equine_id, source_a, source_b, ratio, conf_scale)
# Result = source_a + ratio * (source_b - source_a)
# conf_scale reduces confidence for interpolated points.
_INTERP_MAP: list[tuple[int, int, int, float, float]] = [
    # poll (0): midpoint of left_eye (0) and right_eye (1)
    (0, 0, 1, 0.5, 0.85),
    # throat (2): 60% from eyes-midpoint toward neck
    # handled specially below since it uses 3 source points
    # mid_back (4): midpoint between neck (3) and root_of_tail (4)
    (4, 3, 4, 0.5, 0.80),
    # croup (5): 70% from neck toward root_of_tail
    (5, 3, 4, 0.70, 0.80),
    # l_knee_fore (9): 55% from elbow (6) toward front_paw (7)
    (9, 6, 7, 0.55, 0.75),
    # l_fetlock_fore (10): 80% from elbow (6) toward front_paw (7)
    (10, 6, 7, 0.80, 0.70),
    # r_knee_fore (14): 55% from elbow (9) toward front_paw (10)
    (14, 9, 10, 0.55, 0.75),
    # r_fetlock_fore (15): 80% from elbow (9) toward front_paw (10)
    (15, 9, 10, 0.80, 0.70),
    # l_hind_fetlock (19): 65% from hock/knee (12) toward back_paw (13)
    (19, 12, 13, 0.65, 0.70),
]

# Supported model IDs on HuggingFace
VITPOSE_MODELS = {
    "small": "usyd-community/vitpose-plus-small",
    "base": "usyd-community/vitpose-plus-base",
    "large": "usyd-community/vitpose-plus-large",
    "huge": "usyd-community/vitpose-plus-huge",
}

# AP-10K is dataset_index=3 in ViTPose++
_AP10K_DATASET_INDEX = 3


def _map_ap10k_to_equine(
    ap10k_kpts: np.ndarray,
    ap10k_scores: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Map 17 AP-10K keypoints to our 24-keypoint equine schema.

    Args:
        ap10k_kpts: (17, 2) keypoint coordinates.
        ap10k_scores: (17,) confidence scores.

    Returns:
        Tuple of (24, 2) keypoints and (24,) confidence scores.
    """
    equine_kpts = np.zeros((NUM_KEYPOINTS, 2), dtype=np.float32)
    equine_conf = np.zeros(NUM_KEYPOINTS, dtype=np.float32)

    # 1. Direct mappings
    for ap_idx, eq_idx in _DIRECT_MAP.items():
        equine_kpts[eq_idx] = ap10k_kpts[ap_idx]
        equine_conf[eq_idx] = ap10k_scores[ap_idx]

    # 2. Poll (0): midpoint of eyes
    eye_l, eye_r = ap10k_kpts[0], ap10k_kpts[1]
    score_l, score_r = ap10k_scores[0], ap10k_scores[1]
    if score_l > 0.1 and score_r > 0.1:
        equine_kpts[0] = (eye_l + eye_r) / 2.0
        equine_conf[0] = min(score_l, score_r) * 0.85
    elif score_l > 0.1:
        equine_kpts[0] = eye_l
        equine_conf[0] = score_l * 0.7
    elif score_r > 0.1:
        equine_kpts[0] = eye_r
        equine_conf[0] = score_r * 0.7

    # 3. Throat (2): between eyes-midpoint and neck, shifted down
    eyes_mid = (eye_l + eye_r) / 2.0
    neck = ap10k_kpts[3]
    score_eyes = min(score_l, score_r) if (score_l > 0.1 and score_r > 0.1) else 0.0
    score_neck = ap10k_scores[3]
    if score_eyes > 0.1 and score_neck > 0.1:
        # Throat sits ~40% from eyes toward neck, and slightly below the line
        throat = eyes_mid + 0.40 * (neck - eyes_mid)
        # Shift downward (positive y) by ~8% of the eye-to-neck distance
        dy = abs(neck[1] - eyes_mid[1])
        throat[1] += dy * 0.08
        equine_kpts[2] = throat
        equine_conf[2] = min(score_eyes, score_neck) * 0.75

    # 4. Standard interpolations
    for eq_idx, src_a, src_b, ratio, conf_scale in _INTERP_MAP:
        sa, sb = ap10k_scores[src_a], ap10k_scores[src_b]
        if sa > 0.1 and sb > 0.1:
            equine_kpts[eq_idx] = (
                ap10k_kpts[src_a] + ratio * (ap10k_kpts[src_b] - ap10k_kpts[src_a])
            )
            equine_conf[eq_idx] = min(sa, sb) * conf_scale

    return equine_kpts, equine_conf


class ViTPoseKeypointEstimator:
    """Estimates equine keypoints using ViTPose++ with the AP-10K animal head.

    Uses our existing YOLO horse detector for bounding boxes, then runs
    ViTPose++ on each crop to produce 17 AP-10K keypoints which are mapped
    to our 24-keypoint equine schema.

    This replaces BBoxKeypointEstimator with a real learned model — no custom
    training or annotation required.
    """

    def __init__(
        self,
        model_size: str = "base",
        confidence_threshold: float = 0.3,
        device: str | None = None,
    ):
        """Initialize the ViTPose++ estimator.

        Args:
            model_size: One of 'small', 'base', 'large', 'huge'.
            confidence_threshold: Minimum confidence for visible keypoints.
            device: PyTorch device ('cuda', 'cpu', or None for auto-detect).
        """
        from transformers import VitPoseForPoseEstimation, VitPoseImageProcessor

        self.confidence_threshold = confidence_threshold
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")

        model_id = VITPOSE_MODELS.get(model_size)
        if model_id is None:
            raise ValueError(
                f"Unknown model size '{model_size}'. "
                f"Choose from: {list(VITPOSE_MODELS.keys())}"
            )

        logger.info("Loading ViTPose++ (%s) from %s on %s", model_size, model_id, self.device)
        self.processor = VitPoseImageProcessor.from_pretrained(model_id)
        self.model = VitPoseForPoseEstimation.from_pretrained(model_id)
        self.model.to(self.device)
        self.model.eval()
        logger.info("ViTPose++ ready — 17 AP-10K keypoints → 24 equine schema")

    def estimate(
        self,
        frame: np.ndarray,
        detections: list[Detection] | None = None,
    ) -> list[KeypointResult]:
        """Estimate equine keypoints for detected horses in a frame.

        Args:
            frame: BGR image (H, W, 3).
            detections: Pre-computed horse bounding boxes from YOLO detector.

        Returns:
            List of KeypointResult with 24 equine keypoints per horse.
        """
        if not detections:
            return []

        # Convert BGR → RGB PIL image (ViTPose expects PIL)
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        pil_image = Image.fromarray(rgb)

        # Collect bounding boxes in [x1, y1, x2, y2] format
        boxes = [det.bbox.tolist() for det in detections]

        # Run ViTPose++ with AP-10K animal head
        inputs = self.processor(pil_image, boxes=[boxes], return_tensors="pt")
        inputs = {k: v.to(self.device) for k, v in inputs.items()}

        with torch.no_grad():
            outputs = self.model(**inputs, dataset_index=_AP10K_DATASET_INDEX)

        # Post-process to get keypoints in original image space
        pose_results = self.processor.post_process_pose_estimation(
            outputs, boxes=[boxes]
        )

        # Map each result to our 24-keypoint equine schema
        results: list[KeypointResult] = []

        for i, det in enumerate(detections):
            if i >= len(pose_results[0]):
                break

            result = pose_results[0][i]
            ap10k_kpts = result["keypoints"].cpu().numpy()    # (17, 2)
            ap10k_scores = result["scores"].cpu().numpy()     # (17,)

            # Map 17 AP-10K → 24 equine keypoints
            equine_kpts, equine_conf = _map_ap10k_to_equine(ap10k_kpts, ap10k_scores)

            results.append(KeypointResult(
                keypoints=equine_kpts,
                confidence=equine_conf,
                bbox=det.bbox,
                track_id=det.track_id,
            ))

        return results
