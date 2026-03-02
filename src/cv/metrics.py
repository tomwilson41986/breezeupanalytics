"""Biomechanical and performance metric computation.

Computes all gait cycle, biomechanical, and performance metrics from
smoothed keypoint trajectories and detected stride cycles.

Reference: equine_gait_analysis_spec.md Section 5.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import numpy as np

from src.cv.gait import GaitAnalysis, LimbPhase, StrideCycle
from src.cv.schema import KEYPOINT_NAME_TO_ID

logger = logging.getLogger(__name__)


@dataclass
class StrideMetrics:
    """Metrics computed for a single stride cycle."""
    stride_index: int
    stride_length_px: float = 0.0       # pixels
    stride_length_m: float | None = None # meters (if calibrated)
    stride_duration_s: float = 0.0
    stride_frequency_hz: float = 0.0
    withers_vertical_displacement_px: float = 0.0
    head_neck_angle_deg: float | None = None
    forelimb_protraction_angle_deg: float | None = None
    hindlimb_engagement_angle_deg: float | None = None
    lateral_symmetry_index: float | None = None
    estimated_speed_px_s: float = 0.0
    estimated_speed_m_s: float | None = None


@dataclass
class HorseMetrics:
    """Aggregated metrics for a single horse across all strides."""
    track_id: int | None = None
    num_strides: int = 0
    per_stride: list[StrideMetrics] = field(default_factory=list)

    # Gait cycle averages
    mean_stride_length_px: float = 0.0
    mean_stride_frequency_hz: float = 0.0
    mean_stride_duration_s: float = 0.0
    stride_length_cv: float = 0.0       # coefficient of variation

    # Biomechanical averages
    mean_withers_displacement_px: float = 0.0
    mean_head_neck_angle_deg: float | None = None
    mean_forelimb_protraction_deg: float | None = None
    mean_hindlimb_engagement_deg: float | None = None
    mean_lateral_symmetry: float | None = None

    # Performance
    mean_speed_px_s: float = 0.0
    mean_speed_m_s: float | None = None
    peak_speed_px_s: float = 0.0

    # Limb duty factors
    duty_factors: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Export metrics as a flat dictionary for CSV/JSON output."""
        d = {
            "track_id": self.track_id,
            "num_strides": self.num_strides,
            "mean_stride_length_px": round(self.mean_stride_length_px, 2),
            "mean_stride_frequency_hz": round(self.mean_stride_frequency_hz, 3),
            "mean_stride_duration_s": round(self.mean_stride_duration_s, 4),
            "stride_length_cv": round(self.stride_length_cv, 4),
            "mean_withers_displacement_px": round(self.mean_withers_displacement_px, 2),
            "mean_speed_px_s": round(self.mean_speed_px_s, 2),
            "peak_speed_px_s": round(self.peak_speed_px_s, 2),
        }
        if self.mean_stride_length_px > 0 and self.mean_speed_m_s is not None:
            d["mean_speed_m_s"] = round(self.mean_speed_m_s, 2)
        if self.mean_head_neck_angle_deg is not None:
            d["mean_head_neck_angle_deg"] = round(self.mean_head_neck_angle_deg, 1)
        if self.mean_forelimb_protraction_deg is not None:
            d["mean_forelimb_protraction_deg"] = round(self.mean_forelimb_protraction_deg, 1)
        if self.mean_hindlimb_engagement_deg is not None:
            d["mean_hindlimb_engagement_deg"] = round(self.mean_hindlimb_engagement_deg, 1)
        if self.mean_lateral_symmetry is not None:
            d["mean_lateral_symmetry_pct"] = round(self.mean_lateral_symmetry, 2)
        for limb, df in self.duty_factors.items():
            d[f"duty_factor_{limb}"] = round(df, 3)
        return d


def compute_metrics(
    keypoints_seq: np.ndarray,
    confidence_seq: np.ndarray,
    gait: GaitAnalysis,
    fps: float,
    limb_phases: dict[str, list[LimbPhase]] | None = None,
    px_per_meter: float | None = None,
) -> HorseMetrics:
    """Compute all metrics for one horse.

    Args:
        keypoints_seq: (T, K, 2) smoothed keypoints.
        confidence_seq: (T, K) confidence scores.
        gait: GaitAnalysis with detected strides.
        fps: Frame rate.
        limb_phases: Optional limb phase data.
        px_per_meter: Calibration factor (pixels per meter). None = uncalibrated.

    Returns:
        HorseMetrics with per-stride and aggregated values.
    """
    metrics = HorseMetrics(
        track_id=gait.track_id,
        num_strides=gait.stride_count,
    )

    if gait.stride_count == 0:
        return metrics

    stride_metrics_list = []

    for i, stride in enumerate(gait.strides):
        sm = _compute_stride_metrics(
            keypoints_seq, confidence_seq, stride, i, fps, px_per_meter
        )
        stride_metrics_list.append(sm)

    metrics.per_stride = stride_metrics_list

    # Aggregate
    lengths = [s.stride_length_px for s in stride_metrics_list if s.stride_length_px > 0]
    if lengths:
        metrics.mean_stride_length_px = float(np.mean(lengths))
        metrics.stride_length_cv = float(np.std(lengths) / np.mean(lengths)) if np.mean(lengths) > 0 else 0.0

    metrics.mean_stride_frequency_hz = gait.mean_stride_frequency
    metrics.mean_stride_duration_s = gait.mean_stride_duration_s

    displacements = [s.withers_vertical_displacement_px for s in stride_metrics_list]
    if displacements:
        metrics.mean_withers_displacement_px = float(np.mean(displacements))

    speeds = [s.estimated_speed_px_s for s in stride_metrics_list if s.estimated_speed_px_s > 0]
    if speeds:
        metrics.mean_speed_px_s = float(np.mean(speeds))
        metrics.peak_speed_px_s = float(np.max(speeds))

    # Calibrated speed
    if px_per_meter is not None and metrics.mean_speed_px_s > 0:
        metrics.mean_speed_m_s = metrics.mean_speed_px_s / px_per_meter

    # Angles
    angles = [s.head_neck_angle_deg for s in stride_metrics_list if s.head_neck_angle_deg is not None]
    if angles:
        metrics.mean_head_neck_angle_deg = float(np.mean(angles))

    protractions = [s.forelimb_protraction_angle_deg for s in stride_metrics_list if s.forelimb_protraction_angle_deg is not None]
    if protractions:
        metrics.mean_forelimb_protraction_deg = float(np.mean(protractions))

    engagements = [s.hindlimb_engagement_angle_deg for s in stride_metrics_list if s.hindlimb_engagement_angle_deg is not None]
    if engagements:
        metrics.mean_hindlimb_engagement_deg = float(np.mean(engagements))

    # Symmetry
    symmetries = [s.lateral_symmetry_index for s in stride_metrics_list if s.lateral_symmetry_index is not None]
    if symmetries:
        metrics.mean_lateral_symmetry = float(np.mean(symmetries))

    # Limb duty factors
    if limb_phases:
        for limb, phases in limb_phases.items():
            dfs = [p.duty_factor for p in phases if p.duty_factor > 0]
            if dfs:
                metrics.duty_factors[limb] = float(np.mean(dfs))

    return metrics


def _compute_stride_metrics(
    keypoints_seq: np.ndarray,
    confidence_seq: np.ndarray,
    stride: StrideCycle,
    stride_idx: int,
    fps: float,
    px_per_meter: float | None,
) -> StrideMetrics:
    """Compute metrics for a single stride."""
    sm = StrideMetrics(
        stride_index=stride_idx,
        stride_duration_s=stride.duration_s,
        stride_frequency_hz=stride.frequency_hz,
    )

    seg_kpts = keypoints_seq[stride.start_frame:stride.end_frame]
    seg_conf = confidence_seq[stride.start_frame:stride.end_frame]

    # --- Stride length (horizontal displacement of withers) ---
    withers_id = KEYPOINT_NAME_TO_ID["withers"]
    w_conf = seg_conf[:, withers_id]
    w_valid = w_conf >= 0.3

    if w_valid.sum() >= 2:
        wx = seg_kpts[w_valid, withers_id, 0]
        sm.stride_length_px = float(np.abs(wx[-1] - wx[0]))

        if px_per_meter is not None:
            sm.stride_length_m = sm.stride_length_px / px_per_meter

    # --- Withers vertical displacement ---
    if w_valid.sum() >= 2:
        wy = seg_kpts[w_valid, withers_id, 1]
        sm.withers_vertical_displacement_px = float(np.ptp(wy))

    # --- Speed ---
    if sm.stride_length_px > 0 and stride.duration_s > 0:
        sm.estimated_speed_px_s = sm.stride_length_px / stride.duration_s
        if px_per_meter is not None:
            sm.estimated_speed_m_s = sm.estimated_speed_px_s / px_per_meter

    # --- Head/neck angle ---
    sm.head_neck_angle_deg = _compute_head_neck_angle(seg_kpts, seg_conf)

    # --- Forelimb protraction angle ---
    sm.forelimb_protraction_angle_deg = _compute_forelimb_protraction(seg_kpts, seg_conf)

    # --- Hindlimb engagement angle ---
    sm.hindlimb_engagement_angle_deg = _compute_hindlimb_engagement(seg_kpts, seg_conf)

    # --- Lateral symmetry ---
    sm.lateral_symmetry_index = _compute_lateral_symmetry(seg_kpts, seg_conf)

    return sm


def _angle_3pt(a: np.ndarray, b: np.ndarray, c: np.ndarray) -> float:
    """Compute the angle at point b formed by segments ba and bc, in degrees."""
    ba = a - b
    bc = c - b
    cos_angle = np.dot(ba, bc) / (np.linalg.norm(ba) * np.linalg.norm(bc) + 1e-8)
    cos_angle = np.clip(cos_angle, -1.0, 1.0)
    return float(np.degrees(np.arccos(cos_angle)))


def _compute_head_neck_angle(kpts: np.ndarray, conf: np.ndarray) -> float | None:
    """Compute mean head/neck angle (poll-throat-withers) across a stride segment."""
    poll_id = KEYPOINT_NAME_TO_ID["poll"]
    throat_id = KEYPOINT_NAME_TO_ID["throat"]
    withers_id = KEYPOINT_NAME_TO_ID["withers"]

    angles = []
    for t in range(len(kpts)):
        if conf[t, poll_id] < 0.3 or conf[t, throat_id] < 0.3 or conf[t, withers_id] < 0.3:
            continue
        angle = _angle_3pt(kpts[t, poll_id], kpts[t, throat_id], kpts[t, withers_id])
        angles.append(angle)

    return float(np.mean(angles)) if angles else None


def _compute_forelimb_protraction(kpts: np.ndarray, conf: np.ndarray) -> float | None:
    """Compute forelimb protraction angle at maximum forward extension.

    Uses the angle at the shoulder (withers-shoulder-hoof) at the frame
    where the hoof is most forward (minimum x for left, maximum x for right).
    """
    # Try left forelimb first
    shoulder_id = KEYPOINT_NAME_TO_ID["l_shoulder"]
    hoof_id = KEYPOINT_NAME_TO_ID["l_fore_hoof"]
    withers_id = KEYPOINT_NAME_TO_ID["withers"]

    valid = (
        (conf[:, shoulder_id] >= 0.3)
        & (conf[:, hoof_id] >= 0.3)
        & (conf[:, withers_id] >= 0.3)
    )

    if valid.sum() < 3:
        # Fall back to right forelimb
        shoulder_id = KEYPOINT_NAME_TO_ID["r_shoulder"]
        hoof_id = KEYPOINT_NAME_TO_ID["r_fore_hoof"]
        valid = (
            (conf[:, shoulder_id] >= 0.3)
            & (conf[:, hoof_id] >= 0.3)
            & (conf[:, withers_id] >= 0.3)
        )

    if valid.sum() < 3:
        return None

    # Find frame of maximum forward extension (smallest x for hoof)
    hoof_x = kpts[valid, hoof_id, 0]
    best_frame_relative = int(np.argmin(hoof_x))
    valid_indices = np.where(valid)[0]
    best_frame = valid_indices[best_frame_relative]

    angle = _angle_3pt(
        kpts[best_frame, withers_id],
        kpts[best_frame, shoulder_id],
        kpts[best_frame, hoof_id],
    )
    return angle


def _compute_hindlimb_engagement(kpts: np.ndarray, conf: np.ndarray) -> float | None:
    """Compute hindlimb engagement angle at maximum forward placement.

    Measures the angle at the hip (croup-hip-hoof) when the hind hoof
    is at its most forward position.
    """
    hip_id = KEYPOINT_NAME_TO_ID["l_hip"]
    hoof_id = KEYPOINT_NAME_TO_ID["l_hind_hoof"]
    croup_id = KEYPOINT_NAME_TO_ID["croup"]

    valid = (
        (conf[:, hip_id] >= 0.3)
        & (conf[:, hoof_id] >= 0.3)
        & (conf[:, croup_id] >= 0.3)
    )

    if valid.sum() < 3:
        hip_id = KEYPOINT_NAME_TO_ID["r_hip"]
        hoof_id = KEYPOINT_NAME_TO_ID["r_hind_hoof"]
        valid = (
            (conf[:, hip_id] >= 0.3)
            & (conf[:, hoof_id] >= 0.3)
            & (conf[:, croup_id] >= 0.3)
        )

    if valid.sum() < 3:
        return None

    hoof_x = kpts[valid, hoof_id, 0]
    best_frame_relative = int(np.argmin(hoof_x))
    valid_indices = np.where(valid)[0]
    best_frame = valid_indices[best_frame_relative]

    angle = _angle_3pt(
        kpts[best_frame, croup_id],
        kpts[best_frame, hip_id],
        kpts[best_frame, hoof_id],
    )
    return angle


def _compute_lateral_symmetry(kpts: np.ndarray, conf: np.ndarray) -> float | None:
    """Compute lateral symmetry index as percentage difference between L/R limbs.

    Compares range of motion (vertical displacement) between left and right
    forelimb hooves across the stride segment.
    """
    l_hoof_id = KEYPOINT_NAME_TO_ID["l_fore_hoof"]
    r_hoof_id = KEYPOINT_NAME_TO_ID["r_fore_hoof"]

    l_valid = conf[:, l_hoof_id] >= 0.3
    r_valid = conf[:, r_hoof_id] >= 0.3

    if l_valid.sum() < 3 or r_valid.sum() < 3:
        return None

    l_range = float(np.ptp(kpts[l_valid, l_hoof_id, 1]))
    r_range = float(np.ptp(kpts[r_valid, r_hoof_id, 1]))

    avg_range = (l_range + r_range) / 2
    if avg_range < 1:
        return 0.0

    symmetry_pct = abs(l_range - r_range) / avg_range * 100
    return symmetry_pct
