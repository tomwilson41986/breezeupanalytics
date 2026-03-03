"""ViTPose++ keypoint estimation for horses — hybrid with quality gating.

Runs ViTPose++ (AP-10K animal head, dataset_index=3) on each detection crop
to produce 17 keypoints.  A spatial quality gate counts how many keypoints
land inside the bounding box — if fewer than ``min_valid_keypoints`` pass,
the frame falls back to ``BBoxKeypointEstimator`` (proportion + contour
heuristic) which is more robust to challenging angles and jockeys.

Valid ViTPose keypoints are mapped to our 24-keypoint equine schema.
Keypoints that land outside the padded bbox are zeroed out.

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
from src.cv.keypoints import BBoxKeypointEstimator, KeypointResult
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

# Minimum in-bbox keypoints for ViTPose to be accepted (out of 17).
# Below this, output is garbage and we fall back to BBox heuristic.
_MIN_VALID_KEYPOINTS = 8

# Padding fraction for bbox validity check — keypoints can be slightly
# outside the detection box and still be valid.
_BBOX_PAD_FRAC = 0.15


def _count_valid_in_bbox(
    kpts: np.ndarray,
    scores: np.ndarray,
    bbox: np.ndarray,
    pad_frac: float = _BBOX_PAD_FRAC,
    min_score: float = 0.2,
) -> int:
    """Count AP-10K keypoints that land inside the padded bbox."""
    bw = bbox[2] - bbox[0]
    bh = bbox[3] - bbox[1]
    pad_x, pad_y = bw * pad_frac, bh * pad_frac
    x1, y1 = bbox[0] - pad_x, bbox[1] - pad_y
    x2, y2 = bbox[2] + pad_x, bbox[3] + pad_y

    count = 0
    for i in range(len(kpts)):
        x, y = kpts[i]
        if scores[i] >= min_score and x1 <= x <= x2 and y1 <= y <= y2:
            count += 1
    return count


def _filter_out_of_bbox(
    kpts: np.ndarray,
    scores: np.ndarray,
    bbox: np.ndarray,
    pad_frac: float = _BBOX_PAD_FRAC,
) -> tuple[np.ndarray, np.ndarray]:
    """Zero out AP-10K keypoints that land outside the padded bbox."""
    bw = bbox[2] - bbox[0]
    bh = bbox[3] - bbox[1]
    pad_x, pad_y = bw * pad_frac, bh * pad_frac
    x1, y1 = bbox[0] - pad_x, bbox[1] - pad_y
    x2, y2 = bbox[2] + pad_x, bbox[3] + pad_y

    kpts = kpts.copy()
    scores = scores.copy()
    for i in range(len(kpts)):
        x, y = kpts[i]
        if not (x1 <= x <= x2 and y1 <= y <= y2):
            kpts[i] = 0.0
            scores[i] = 0.0
    return kpts, scores


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
        throat = eyes_mid + 0.40 * (neck - eyes_mid)
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
    """Hybrid estimator: ViTPose++ with automatic fallback to bbox heuristic.

    For each detection:
    1. Run ViTPose++ AP-10K to get 17 animal keypoints
    2. Count how many land inside the bounding box (quality gate)
    3. If ≥ min_valid_keypoints pass → use ViTPose output, filtering
       out-of-bbox keypoints and mapping to 24-point equine schema
    4. If too few pass → ViTPose produced garbage for this crop,
       fall back to BBoxKeypointEstimator (heuristic)

    This hybrid approach handles challenging scenarios (oblique angles,
    jockeys, occlusion) where ViTPose fails while still leveraging
    learned keypoints when the model is confident.
    """

    def __init__(
        self,
        model_size: str = "base",
        confidence_threshold: float = 0.3,
        device: str | None = None,
        min_valid_keypoints: int = _MIN_VALID_KEYPOINTS,
    ):
        from transformers import VitPoseForPoseEstimation, VitPoseImageProcessor

        self.confidence_threshold = confidence_threshold
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.min_valid_keypoints = min_valid_keypoints

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

        self._fallback = BBoxKeypointEstimator(confidence_threshold=confidence_threshold)
        self._vitpose_used = 0
        self._fallback_used = 0
        logger.info(
            "ViTPose++ hybrid ready — quality gate at %d/17 in-bbox keypoints, "
            "fallback to BBox heuristic",
            self.min_valid_keypoints,
        )

    def estimate(
        self,
        frame: np.ndarray,
        detections: list[Detection] | None = None,
    ) -> list[KeypointResult]:
        """Estimate equine keypoints for detected horses in a frame.

        Runs ViTPose++ on all detections, then per-detection quality gate
        decides whether to keep ViTPose output or fall back to heuristic.
        """
        if not detections:
            return []

        # --- ViTPose inference ---
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        pil_image = Image.fromarray(rgb)
        boxes = [det.bbox.tolist() for det in detections]

        inputs = self.processor(pil_image, boxes=[boxes], return_tensors="pt")
        inputs = {k: v.to(self.device) for k, v in inputs.items()}

        dataset_idx = torch.tensor(_AP10K_DATASET_INDEX, device=self.device)
        with torch.no_grad():
            outputs = self.model(**inputs, dataset_index=dataset_idx)

        pose_results = self.processor.post_process_pose_estimation(
            outputs, boxes=[boxes]
        )

        # --- Per-detection quality gate ---
        results: list[KeypointResult] = []

        for i, det in enumerate(detections):
            if i >= len(pose_results[0]):
                # ViTPose didn't produce output for this detection
                fb = self._fallback.estimate(frame, [det])
                results.extend(fb)
                self._fallback_used += 1
                continue

            result = pose_results[0][i]
            ap10k_kpts = result["keypoints"].cpu().numpy()    # (17, 2)
            ap10k_scores = result["scores"].cpu().numpy()     # (17,)

            # Quality gate: count keypoints inside the bbox
            n_valid = _count_valid_in_bbox(ap10k_kpts, ap10k_scores, det.bbox)

            if n_valid < self.min_valid_keypoints:
                # ViTPose failed for this detection — use heuristic
                fb = self._fallback.estimate(frame, [det])
                results.extend(fb)
                self._fallback_used += 1
                continue

            # ViTPose passed — filter out-of-bbox keypoints, then map
            self._vitpose_used += 1
            ap10k_kpts, ap10k_scores = _filter_out_of_bbox(
                ap10k_kpts, ap10k_scores, det.bbox
            )
            equine_kpts, equine_conf = _map_ap10k_to_equine(ap10k_kpts, ap10k_scores)

            results.append(KeypointResult(
                keypoints=equine_kpts,
                confidence=equine_conf,
                bbox=det.bbox,
                track_id=det.track_id,
            ))

        return results

    @property
    def stats(self) -> dict[str, int]:
        """Return usage statistics for ViTPose vs fallback."""
        total = self._vitpose_used + self._fallback_used
        return {
            "vitpose_used": self._vitpose_used,
            "fallback_used": self._fallback_used,
            "total": total,
            "vitpose_pct": round(self._vitpose_used / total * 100, 1) if total else 0,
        }
