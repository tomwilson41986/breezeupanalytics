"""Gait cycle detection from equine keypoint trajectories.

Detects stride boundaries from vertical oscillation of the withers keypoint,
identifies stance/swing phases per limb, and segments the gait cycle for
metric computation.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import numpy as np
from scipy.signal import find_peaks

from src.cv.schema import KEYPOINT_NAME_TO_ID

logger = logging.getLogger(__name__)


@dataclass
class StrideCycle:
    """A single detected gait cycle (stride)."""
    start_frame: int       # frame index where stride begins
    end_frame: int         # frame index where stride ends
    duration_frames: int   # number of frames in this stride
    duration_s: float      # duration in seconds
    frequency_hz: float    # stride frequency (1 / duration_s)


@dataclass
class LimbPhase:
    """Stance and swing phases for a single limb within a stride."""
    limb: str                          # e.g. "l_fore", "r_fore", "l_hind", "r_hind"
    stance_start: int                  # frame index
    stance_end: int                    # frame index
    swing_start: int                   # frame index
    swing_end: int                     # frame index
    stance_duration_s: float = 0.0
    swing_duration_s: float = 0.0
    duty_factor: float = 0.0           # stance / total


@dataclass
class GaitAnalysis:
    """Complete gait analysis for one horse across a video segment."""
    track_id: int | None = None
    strides: list[StrideCycle] = field(default_factory=list)
    limb_phases: dict[str, list[LimbPhase]] = field(default_factory=dict)
    withers_vertical: np.ndarray | None = None  # vertical displacement of withers
    mean_stride_frequency: float = 0.0
    mean_stride_duration_s: float = 0.0
    stride_count: int = 0


def detect_strides(
    keypoints_seq: np.ndarray,
    confidence_seq: np.ndarray,
    fps: float,
    min_confidence: float = 0.3,
    min_stride_frames: int | None = None,
    max_stride_frames: int | None = None,
) -> GaitAnalysis:
    """Detect gait cycles from withers vertical oscillation.

    The withers keypoint undergoes a characteristic vertical oscillation
    during gallop. Each cycle (peak to peak) corresponds to one complete stride.

    Args:
        keypoints_seq: (T, K, 2) smoothed keypoint positions.
        confidence_seq: (T, K) keypoint confidence scores.
        fps: Video frame rate.
        min_confidence: Minimum withers confidence to use.
        min_stride_frames: Minimum frames per stride (filters noise).
        max_stride_frames: Maximum frames per stride.

    Returns:
        GaitAnalysis with detected stride cycles.
    """
    withers_id = KEYPOINT_NAME_TO_ID["withers"]
    withers_conf = confidence_seq[:, withers_id]
    withers_y = keypoints_seq[:, withers_id, 1]  # vertical position

    # Default stride constraints based on typical gallop at various FPS
    if min_stride_frames is None:
        min_stride_frames = max(3, int(fps * 0.3))  # min ~0.3s per stride
    if max_stride_frames is None:
        max_stride_frames = int(fps * 0.8)  # max ~0.8s per stride

    # Only use frames where withers is visible
    valid = withers_conf >= min_confidence
    if valid.sum() < min_stride_frames * 2:
        logger.warning("Insufficient withers data for gait detection (%d valid frames)", valid.sum())
        return GaitAnalysis()

    # Find peaks in withers vertical position (lowest point of oscillation = highest y value)
    # In image coordinates, y increases downward, so peaks in y = lowest point of body
    peaks, properties = find_peaks(
        withers_y,
        distance=min_stride_frames,
        prominence=5.0,  # minimum pixel displacement to count as a stride
    )

    # Filter peaks to valid (confident) frames
    peaks = peaks[valid[peaks]]

    if len(peaks) < 2:
        logger.warning("Fewer than 2 stride peaks detected (%d peaks)", len(peaks))
        return GaitAnalysis()

    # Build stride cycles from consecutive peaks
    strides = []
    for i in range(len(peaks) - 1):
        start = int(peaks[i])
        end = int(peaks[i + 1])
        duration_frames = end - start

        if duration_frames < min_stride_frames or duration_frames > max_stride_frames:
            continue

        duration_s = duration_frames / fps
        freq = 1.0 / duration_s if duration_s > 0 else 0.0

        strides.append(StrideCycle(
            start_frame=start,
            end_frame=end,
            duration_frames=duration_frames,
            duration_s=duration_s,
            frequency_hz=freq,
        ))

    analysis = GaitAnalysis(
        strides=strides,
        withers_vertical=withers_y,
        stride_count=len(strides),
    )

    if strides:
        analysis.mean_stride_duration_s = float(np.mean([s.duration_s for s in strides]))
        analysis.mean_stride_frequency = float(np.mean([s.frequency_hz for s in strides]))

    logger.info("Detected %d strides (mean %.2f Hz, mean %.3f s)", len(strides), analysis.mean_stride_frequency, analysis.mean_stride_duration_s)

    return analysis


def detect_hoof_contacts(
    keypoints_seq: np.ndarray,
    confidence_seq: np.ndarray,
    fps: float,
    min_confidence: float = 0.3,
) -> dict[str, np.ndarray]:
    """Detect ground contact events from hoof keypoint trajectories.

    A hoof is in stance (ground contact) when its vertical velocity
    approaches zero and its vertical position is near its lowest point.

    Args:
        keypoints_seq: (T, K, 2) smoothed keypoints.
        confidence_seq: (T, K) confidence.
        fps: Frame rate.

    Returns:
        Dict mapping limb name to boolean array (T,) where True = stance.
    """
    hoof_keypoints = {
        "l_fore": KEYPOINT_NAME_TO_ID["l_fore_hoof"],
        "r_fore": KEYPOINT_NAME_TO_ID["r_fore_hoof"],
        "l_hind": KEYPOINT_NAME_TO_ID["l_hind_hoof"],
        "r_hind": KEYPOINT_NAME_TO_ID["r_hind_hoof"],
    }

    contacts = {}

    for limb_name, kp_id in hoof_keypoints.items():
        y = keypoints_seq[:, kp_id, 1]
        conf = confidence_seq[:, kp_id]
        valid = conf >= min_confidence

        if valid.sum() < 5:
            contacts[limb_name] = np.zeros(len(y), dtype=bool)
            continue

        # Compute vertical velocity (pixels/frame)
        vy = np.gradient(y)

        # Hoof is near ground when y is in the bottom 20% of its range
        y_min, y_max = np.percentile(y[valid], [5, 95])
        y_range = y_max - y_min
        if y_range < 3:
            contacts[limb_name] = np.zeros(len(y), dtype=bool)
            continue

        ground_threshold = y_max - y_range * 0.2
        near_ground = y >= ground_threshold

        # Stance = near ground AND low velocity
        low_velocity = np.abs(vy) < (y_range * 0.15)
        stance = near_ground & low_velocity & valid

        contacts[limb_name] = stance

    return contacts


def compute_limb_phases(
    contacts: dict[str, np.ndarray],
    strides: list[StrideCycle],
    fps: float,
) -> dict[str, list[LimbPhase]]:
    """Compute stance/swing phases for each limb within each stride.

    Args:
        contacts: Per-limb boolean stance arrays from detect_hoof_contacts.
        strides: Detected stride cycles.
        fps: Frame rate.

    Returns:
        Dict mapping limb name to list of LimbPhase per stride.
    """
    phases: dict[str, list[LimbPhase]] = {}

    for limb_name, stance_mask in contacts.items():
        limb_phases = []

        for stride in strides:
            seg = stance_mask[stride.start_frame:stride.end_frame]
            n = len(seg)

            if n == 0:
                continue

            # Find transitions
            stance_frames = int(seg.sum())
            swing_frames = n - stance_frames

            # Find first stance and first swing
            stance_start = stride.start_frame
            stance_end = stride.start_frame + stance_frames
            swing_start = stance_end
            swing_end = stride.end_frame

            stance_dur = stance_frames / fps
            swing_dur = swing_frames / fps
            total_dur = n / fps
            duty = stance_dur / total_dur if total_dur > 0 else 0.0

            limb_phases.append(LimbPhase(
                limb=limb_name,
                stance_start=stance_start,
                stance_end=stance_end,
                swing_start=swing_start,
                swing_end=swing_end,
                stance_duration_s=stance_dur,
                swing_duration_s=swing_dur,
                duty_factor=duty,
            ))

        phases[limb_name] = limb_phases

    return phases
