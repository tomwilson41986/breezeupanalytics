"""Gait cycle detection from equine keypoint trajectories.

Detects stride boundaries from vertical oscillation of the withers keypoint,
identifies stance/swing phases per limb, suspension phases, overreach distances,
and segments the gait cycle for metric computation.
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
class SuspensionPhase:
    """A period where all four hooves are off the ground (aerial phase)."""
    start_frame: int
    end_frame: int
    duration_frames: int
    duration_s: float
    stride_index: int | None = None  # which stride this belongs to


@dataclass
class OverreachEvent:
    """Measurement of hind hoof landing ahead of fore hoof print.

    Positive overreach_px means the hind hoof lands in front of where
    the ipsilateral fore hoof was — desirable for forward propulsion.
    """
    frame: int
    side: str              # "left" or "right"
    overreach_px: float    # positive = hind lands ahead of fore
    overreach_m: float | None = None
    stride_index: int | None = None


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
    suspension_phases: list[SuspensionPhase] = field(default_factory=list)
    overreach_events: list[OverreachEvent] = field(default_factory=list)
    withers_vertical: np.ndarray | None = None  # vertical displacement of withers
    mean_stride_frequency: float = 0.0
    mean_stride_duration_s: float = 0.0
    stride_count: int = 0
    total_suspension_frames: int = 0
    mean_overreach_px: float = 0.0


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


def detect_suspension_phases(
    contacts: dict[str, np.ndarray],
    strides: list[StrideCycle],
    fps: float,
    min_duration_frames: int = 1,
) -> list[SuspensionPhase]:
    """Detect aerial (suspension) phases where all four hooves are off the ground.

    In gallop, the horse has a brief suspension phase where no hooves are in
    contact with the ground. This is a key indicator of speed and athleticism.

    Args:
        contacts: Per-limb boolean stance arrays from detect_hoof_contacts.
        strides: Detected stride cycles for assigning suspension to strides.
        fps: Frame rate.
        min_duration_frames: Minimum frames to count as a suspension phase.

    Returns:
        List of SuspensionPhase events.
    """
    required = ["l_fore", "r_fore", "l_hind", "r_hind"]
    if not all(limb in contacts for limb in required):
        return []

    # All hooves off ground = NOT in stance for any limb
    any_stance = np.zeros_like(contacts[required[0]], dtype=bool)
    for limb in required:
        any_stance |= contacts[limb]

    all_aerial = ~any_stance
    T = len(all_aerial)

    # Find contiguous runs of aerial frames
    phases = []
    in_aerial = False
    start = 0

    for i in range(T):
        if all_aerial[i] and not in_aerial:
            start = i
            in_aerial = True
        elif not all_aerial[i] and in_aerial:
            duration = i - start
            if duration >= min_duration_frames:
                # Assign to a stride
                stride_idx = _find_stride_for_frame(start, strides)
                phases.append(SuspensionPhase(
                    start_frame=start,
                    end_frame=i,
                    duration_frames=duration,
                    duration_s=duration / fps,
                    stride_index=stride_idx,
                ))
            in_aerial = False

    # Handle trailing aerial segment
    if in_aerial and (T - start) >= min_duration_frames:
        stride_idx = _find_stride_for_frame(start, strides)
        phases.append(SuspensionPhase(
            start_frame=start,
            end_frame=T,
            duration_frames=T - start,
            duration_s=(T - start) / fps,
            stride_index=stride_idx,
        ))

    return phases


def detect_overreach(
    keypoints_seq: np.ndarray,
    confidence_seq: np.ndarray,
    contacts: dict[str, np.ndarray],
    strides: list[StrideCycle],
    min_confidence: float = 0.3,
    px_per_meter: float | None = None,
) -> list[OverreachEvent]:
    """Measure overreach: how far the hind hoof lands ahead of the fore hoof print.

    At each hind hoof ground contact (stance onset), measure the horizontal
    distance between the hind hoof and the ipsilateral fore hoof position at
    the nearest fore hoof stance onset. Positive = hind lands ahead of fore.

    Args:
        keypoints_seq: (T, K, 2) smoothed keypoints.
        confidence_seq: (T, K) confidence.
        contacts: Per-limb stance arrays.
        strides: Detected stride cycles.
        min_confidence: Minimum keypoint confidence.
        px_per_meter: Optional calibration factor.

    Returns:
        List of OverreachEvent measurements.
    """
    pairs = [
        ("left", "l_hind", "l_fore", "l_hind_hoof", "l_fore_hoof"),
        ("right", "r_hind", "r_fore", "r_hind_hoof", "r_fore_hoof"),
    ]

    events = []

    for side, hind_limb, fore_limb, hind_hoof_name, fore_hoof_name in pairs:
        if hind_limb not in contacts or fore_limb not in contacts:
            continue

        hind_stance = contacts[hind_limb]
        fore_stance = contacts[fore_limb]
        hind_hoof_id = KEYPOINT_NAME_TO_ID[hind_hoof_name]
        fore_hoof_id = KEYPOINT_NAME_TO_ID[fore_hoof_name]

        # Find hind hoof stance onsets (transitions from swing to stance)
        hind_onsets = _find_stance_onsets(hind_stance)
        fore_onsets = _find_stance_onsets(fore_stance)

        if len(hind_onsets) == 0 or len(fore_onsets) == 0:
            continue

        for hind_frame in hind_onsets:
            h_conf = confidence_seq[hind_frame, hind_hoof_id]
            if h_conf < min_confidence:
                continue

            # Find the nearest preceding fore stance onset
            preceding = fore_onsets[fore_onsets < hind_frame]
            if len(preceding) == 0:
                continue
            fore_frame = preceding[-1]

            f_conf = confidence_seq[fore_frame, fore_hoof_id]
            if f_conf < min_confidence:
                continue

            # Overreach = horizontal distance (hind position relative to fore)
            hind_x = keypoints_seq[hind_frame, hind_hoof_id, 0]
            fore_x = keypoints_seq[fore_frame, fore_hoof_id, 0]

            # Determine direction of travel from withers horizontal displacement
            w_id = KEYPOINT_NAME_TO_ID["withers"]
            if hind_frame > 0:
                dx = keypoints_seq[min(hind_frame + 1, len(keypoints_seq) - 1), w_id, 0] - \
                     keypoints_seq[max(hind_frame - 1, 0), w_id, 0]
            else:
                dx = 1.0  # assume left-to-right

            # If horse moves left-to-right (positive dx), overreach is fore_x - hind_x
            # being negative means hind lands ahead
            if dx >= 0:
                overreach_px = hind_x - fore_x  # positive = hind ahead (further right)
            else:
                overreach_px = fore_x - hind_x  # positive = hind ahead (further left)

            stride_idx = _find_stride_for_frame(hind_frame, strides)
            overreach_m = overreach_px / px_per_meter if px_per_meter else None

            events.append(OverreachEvent(
                frame=hind_frame,
                side=side,
                overreach_px=float(overreach_px),
                overreach_m=float(overreach_m) if overreach_m is not None else None,
                stride_index=stride_idx,
            ))

    return events


def _find_stride_for_frame(frame: int, strides: list[StrideCycle]) -> int | None:
    """Find which stride index a frame belongs to."""
    for i, s in enumerate(strides):
        if s.start_frame <= frame < s.end_frame:
            return i
    return None


def _find_stance_onsets(stance_mask: np.ndarray) -> np.ndarray:
    """Find frame indices where stance begins (swing -> stance transitions)."""
    if len(stance_mask) < 2:
        return np.array([], dtype=int)
    transitions = np.diff(stance_mask.astype(int))
    onsets = np.where(transitions == 1)[0] + 1  # +1 because diff shifts by 1
    return onsets
