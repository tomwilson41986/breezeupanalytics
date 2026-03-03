"""Active learning module for efficient labeling.

Identifies frames where the model is most uncertain, so annotators
can focus their effort on the most informative samples.

Uncertainty strategies:
- Low confidence: frames where keypoint confidence is lowest
- High variance: frames where keypoint positions jitter most
- Disagreement: frames where multiple model checkpoints disagree
- Boundary: frames near gait phase transitions
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

from src.cv.schema import NUM_KEYPOINTS

logger = logging.getLogger(__name__)


@dataclass
class UncertainFrame:
    """A frame identified as high-uncertainty for active labeling."""
    frame_idx: int
    uncertainty_score: float
    reason: str
    mean_confidence: float
    num_low_conf_keypoints: int


def select_uncertain_frames(
    keypoint_confidences: np.ndarray,
    n_select: int = 50,
    confidence_threshold: float = 0.5,
    strategy: str = "combined",
) -> list[UncertainFrame]:
    """Select the most uncertain frames from a processed video.

    Args:
        keypoint_confidences: (T, K) array of per-frame per-keypoint confidence.
        n_select: Number of uncertain frames to select.
        confidence_threshold: Threshold below which a keypoint is "uncertain".
        strategy: "low_confidence", "high_variance", or "combined".

    Returns:
        List of UncertainFrame, sorted by uncertainty (highest first).
    """
    T, K = keypoint_confidences.shape
    n_select = min(n_select, T)

    candidates = []

    for t in range(T):
        conf = keypoint_confidences[t]
        mean_conf = float(np.mean(conf))
        n_low = int((conf < confidence_threshold).sum())

        # Skip frames with no detections at all
        if mean_conf < 0.01:
            continue

        if strategy == "low_confidence":
            score = 1.0 - mean_conf
            reason = "low_confidence"
        elif strategy == "high_variance":
            # Variance of confidence across keypoints — high means inconsistent
            score = float(np.std(conf))
            reason = "high_variance"
        elif strategy == "combined":
            # Combined: weighted average of low confidence and high variance
            conf_score = 1.0 - mean_conf
            var_score = float(np.std(conf))
            low_kpt_score = n_low / K
            score = 0.4 * conf_score + 0.3 * var_score + 0.3 * low_kpt_score
            reason = "combined"
        else:
            raise ValueError(f"Unknown strategy: {strategy}")

        candidates.append(UncertainFrame(
            frame_idx=t,
            uncertainty_score=score,
            reason=reason,
            mean_confidence=mean_conf,
            num_low_conf_keypoints=n_low,
        ))

    # Sort by uncertainty (highest first)
    candidates.sort(key=lambda x: x.uncertainty_score, reverse=True)

    # Apply minimum spacing to avoid selecting adjacent frames
    selected = _apply_min_spacing(candidates, n_select, min_gap=5)

    logger.info(
        "Selected %d uncertain frames (strategy=%s, top score=%.3f)",
        len(selected), strategy,
        selected[0].uncertainty_score if selected else 0.0,
    )

    return selected


def _apply_min_spacing(
    candidates: list[UncertainFrame],
    n_select: int,
    min_gap: int = 5,
) -> list[UncertainFrame]:
    """Select frames with a minimum spacing between them."""
    selected = []
    used_indices = set()

    for candidate in candidates:
        if len(selected) >= n_select:
            break

        # Check if any already-selected frame is too close
        too_close = False
        for idx in used_indices:
            if abs(candidate.frame_idx - idx) < min_gap:
                too_close = True
                break

        if not too_close:
            selected.append(candidate)
            used_indices.add(candidate.frame_idx)

    return selected


def export_uncertain_frames(
    video_path: str | Path,
    uncertain_frames: list[UncertainFrame],
    output_dir: str | Path,
) -> list[Path]:
    """Extract uncertain frames from video and save as images for labeling.

    Also generates a manifest file with frame metadata to guide annotators.

    Args:
        video_path: Source video.
        uncertain_frames: Frames to extract.
        output_dir: Directory for extracted images.

    Returns:
        List of saved image paths.
    """
    video_path = Path(video_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {video_path}")

    saved = []
    stem = video_path.stem

    for uf in uncertain_frames:
        cap.set(cv2.CAP_PROP_POS_FRAMES, uf.frame_idx)
        ret, frame = cap.read()
        if not ret:
            continue

        fname = f"{stem}_frame{uf.frame_idx:06d}.jpg"
        path = output_dir / fname
        cv2.imwrite(str(path), frame)
        saved.append(path)

    cap.release()

    # Write manifest
    manifest_path = output_dir / "uncertain_frames_manifest.txt"
    with open(manifest_path, "w") as f:
        f.write("# Uncertain frames for active learning annotation\n")
        f.write(f"# Source: {video_path.name}\n")
        f.write(f"# Frames: {len(uncertain_frames)}\n")
        f.write("# frame_idx | uncertainty_score | mean_conf | low_conf_kpts | reason\n\n")
        for uf in uncertain_frames:
            f.write(
                f"{uf.frame_idx:6d} | {uf.uncertainty_score:.4f} | "
                f"{uf.mean_confidence:.3f} | {uf.num_low_conf_keypoints:2d}/{NUM_KEYPOINTS} | "
                f"{uf.reason}\n"
            )

    logger.info("Exported %d uncertain frames to %s", len(saved), output_dir)
    return saved


def compute_per_keypoint_accuracy(
    predictions: np.ndarray,
    ground_truth: np.ndarray,
    gt_visibility: np.ndarray,
    threshold_px: float = 5.0,
) -> dict[str, float]:
    """Compute per-keypoint accuracy (PCK — Percentage of Correct Keypoints).

    Args:
        predictions: (N, K, 2) predicted keypoint positions.
        ground_truth: (N, K, 2) ground truth positions.
        gt_visibility: (N, K) visibility flags (>0 means labeled).
        threshold_px: Distance threshold in pixels for "correct" prediction.

    Returns:
        Dict mapping keypoint name to accuracy percentage.
    """
    from src.cv.schema import KEYPOINT_NAMES

    N, K, _ = predictions.shape
    results = {}

    for k in range(K):
        name = KEYPOINT_NAMES[k] if k < len(KEYPOINT_NAMES) else f"kp_{k}"

        # Only evaluate on visible ground-truth keypoints
        visible = gt_visibility[:, k] > 0
        n_visible = visible.sum()

        if n_visible == 0:
            results[name] = 0.0
            continue

        dists = np.linalg.norm(
            predictions[visible, k] - ground_truth[visible, k],
            axis=1,
        )
        correct = (dists < threshold_px).sum()
        results[name] = float(correct / n_visible * 100)

    return results


def compute_oks(
    predictions: np.ndarray,
    ground_truth: np.ndarray,
    gt_visibility: np.ndarray,
    bbox_areas: np.ndarray,
    sigmas: np.ndarray | None = None,
) -> np.ndarray:
    """Compute Object Keypoint Similarity (OKS) — the standard pose metric.

    OKS is analogous to IoU but for keypoints. It accounts for keypoint
    difficulty (sigma) and object size (bbox area).

    Args:
        predictions: (N, K, 2) predicted keypoint positions.
        ground_truth: (N, K, 2) ground truth positions.
        gt_visibility: (N, K) visibility flags.
        bbox_areas: (N,) bounding box areas for scale normalization.
        sigmas: (K,) per-keypoint standard deviations. If None, uses uniform.

    Returns:
        (N,) OKS score for each instance (0 to 1).
    """
    N, K, _ = predictions.shape

    if sigmas is None:
        # Default sigmas for equine keypoints (estimated from annotation variance)
        # Larger sigma = more tolerance for that keypoint
        sigmas = np.array([
            0.05,  # poll — precise
            0.05,  # nose
            0.06,  # throat
            0.07,  # withers — larger body part
            0.08,  # mid_back
            0.07,  # croup
            0.06,  # tail_base
            0.07,  # l_shoulder
            0.07,  # l_elbow
            0.06,  # l_knee_fore
            0.06,  # l_fetlock_fore
            0.05,  # l_fore_hoof — precise
            0.07,  # r_shoulder
            0.07,  # r_elbow
            0.06,  # r_knee_fore
            0.06,  # r_fetlock_fore
            0.05,  # r_fore_hoof
            0.08,  # l_hip
            0.07,  # l_hock
            0.06,  # l_hind_fetlock
            0.05,  # l_hind_hoof
            0.08,  # r_hip
            0.07,  # r_hock
            0.05,  # r_hind_hoof
        ])

    sigmas = sigmas[:K]
    vars = (sigmas * 2) ** 2

    oks_scores = np.zeros(N)

    for n in range(N):
        visible = gt_visibility[n] > 0
        n_visible = visible.sum()

        if n_visible == 0:
            oks_scores[n] = 0.0
            continue

        dx = predictions[n, visible, 0] - ground_truth[n, visible, 0]
        dy = predictions[n, visible, 1] - ground_truth[n, visible, 1]
        d_sq = dx ** 2 + dy ** 2

        area = bbox_areas[n]
        if area <= 0:
            area = 1.0

        e = d_sq / (2 * area * vars[visible])
        oks_scores[n] = float(np.mean(np.exp(-e)))

    return oks_scores
