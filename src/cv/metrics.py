"""Biomechanical and performance metric computation.

Computes all gait cycle, biomechanical, and performance metrics from
smoothed keypoint trajectories and detected stride cycles.

Reference: equine_gait_analysis_spec.md Section 5.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import numpy as np

from src.cv.gait import (
    GaitAnalysis, LimbPhase, OverreachEvent, StrideCycle, SuspensionPhase,
)
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

    # Phase 3: new per-stride metrics
    topline_angle_deg: float | None = None
    knee_flexion_deg: float | None = None
    fetlock_extension_deg: float | None = None
    hock_flexion_deg: float | None = None
    suspension_duration_s: float = 0.0
    overreach_px: float | None = None
    overreach_m: float | None = None
    acceleration_px_s2: float | None = None
    speed_efficiency: float | None = None  # speed / stride_frequency ratio
    ground_cover_px: float = 0.0           # centroid horizontal displacement per stride
    ground_cover_m: float | None = None


@dataclass
class SpeedProfile:
    """Speed across successive strides — tracks acceleration and deceleration."""
    speeds_px_s: list[float] = field(default_factory=list)
    speeds_m_s: list[float] = field(default_factory=list)
    accelerations_px_s2: list[float] = field(default_factory=list)
    peak_speed_px_s: float = 0.0
    peak_speed_m_s: float | None = None
    mean_acceleration_px_s2: float = 0.0
    max_acceleration_px_s2: float = 0.0
    min_acceleration_px_s2: float = 0.0  # deceleration


@dataclass
class MovementQuality:
    """Composite movement quality score (0-100).

    Combines multiple biomechanical indicators into a single quality rating
    for quick comparison between horses.
    """
    overall_score: float = 0.0
    stride_regularity: float = 0.0     # based on stride length CV (lower = better)
    symmetry_score: float = 0.0        # based on lateral symmetry
    reach_score: float = 0.0           # based on overreach distance
    suspension_score: float = 0.0      # based on suspension phase duration
    engagement_score: float = 0.0      # based on hindlimb engagement angle
    components: dict[str, float] = field(default_factory=dict)


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

    # Phase 3: new angle averages
    mean_topline_angle_deg: float | None = None
    mean_knee_flexion_deg: float | None = None
    mean_fetlock_extension_deg: float | None = None
    mean_hock_flexion_deg: float | None = None

    # Performance
    mean_speed_px_s: float = 0.0
    mean_speed_m_s: float | None = None
    peak_speed_px_s: float = 0.0

    # Phase 3: speed profile and efficiency
    speed_profile: SpeedProfile | None = None
    speed_efficiency_index: float | None = None  # mean_speed / mean_frequency

    # Phase 3: suspension and overreach
    mean_suspension_duration_s: float = 0.0
    suspension_ratio: float = 0.0         # suspension time / stride time
    mean_overreach_px: float = 0.0
    mean_overreach_m: float | None = None

    # Ground cover per stride (centroid displacement)
    mean_ground_cover_px: float = 0.0
    mean_ground_cover_m: float | None = None

    # Phase 3: movement quality
    movement_quality: MovementQuality | None = None

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
        # Phase 3 additions
        if self.mean_topline_angle_deg is not None:
            d["mean_topline_angle_deg"] = round(self.mean_topline_angle_deg, 1)
        if self.mean_knee_flexion_deg is not None:
            d["mean_knee_flexion_deg"] = round(self.mean_knee_flexion_deg, 1)
        if self.mean_fetlock_extension_deg is not None:
            d["mean_fetlock_extension_deg"] = round(self.mean_fetlock_extension_deg, 1)
        if self.mean_hock_flexion_deg is not None:
            d["mean_hock_flexion_deg"] = round(self.mean_hock_flexion_deg, 1)
        if self.mean_suspension_duration_s > 0:
            d["mean_suspension_duration_s"] = round(self.mean_suspension_duration_s, 4)
            d["suspension_ratio"] = round(self.suspension_ratio, 3)
        if self.mean_overreach_px != 0:
            d["mean_overreach_px"] = round(self.mean_overreach_px, 2)
        if self.mean_overreach_m is not None:
            d["mean_overreach_m"] = round(self.mean_overreach_m, 3)
        if self.mean_ground_cover_px > 0:
            d["mean_ground_cover_px"] = round(self.mean_ground_cover_px, 2)
        if self.mean_ground_cover_m is not None:
            d["mean_ground_cover_m"] = round(self.mean_ground_cover_m, 3)
        if self.speed_efficiency_index is not None:
            d["speed_efficiency_index"] = round(self.speed_efficiency_index, 2)
        if self.speed_profile is not None:
            d["mean_acceleration_px_s2"] = round(self.speed_profile.mean_acceleration_px_s2, 2)
        if self.movement_quality is not None:
            d["movement_quality_score"] = round(self.movement_quality.overall_score, 1)
        for limb, df in self.duty_factors.items():
            d[f"duty_factor_{limb}"] = round(df, 3)
        return d

    def to_detail_dict(self) -> dict:
        """Export full per-stride detail for JSON analysis."""
        d = self.to_dict()
        d["per_stride"] = []
        for sm in self.per_stride:
            sd = {
                "stride_index": sm.stride_index,
                "stride_length_px": round(sm.stride_length_px, 2),
                "stride_duration_s": round(sm.stride_duration_s, 4),
                "stride_frequency_hz": round(sm.stride_frequency_hz, 3),
                "estimated_speed_px_s": round(sm.estimated_speed_px_s, 2),
                "withers_vertical_displacement_px": round(sm.withers_vertical_displacement_px, 2),
            }
            if sm.stride_length_m is not None:
                sd["stride_length_m"] = round(sm.stride_length_m, 3)
            if sm.estimated_speed_m_s is not None:
                sd["estimated_speed_m_s"] = round(sm.estimated_speed_m_s, 2)
            if sm.head_neck_angle_deg is not None:
                sd["head_neck_angle_deg"] = round(sm.head_neck_angle_deg, 1)
            if sm.forelimb_protraction_angle_deg is not None:
                sd["forelimb_protraction_angle_deg"] = round(sm.forelimb_protraction_angle_deg, 1)
            if sm.hindlimb_engagement_angle_deg is not None:
                sd["hindlimb_engagement_angle_deg"] = round(sm.hindlimb_engagement_angle_deg, 1)
            if sm.lateral_symmetry_index is not None:
                sd["lateral_symmetry_index"] = round(sm.lateral_symmetry_index, 2)
            if sm.topline_angle_deg is not None:
                sd["topline_angle_deg"] = round(sm.topline_angle_deg, 1)
            if sm.knee_flexion_deg is not None:
                sd["knee_flexion_deg"] = round(sm.knee_flexion_deg, 1)
            if sm.fetlock_extension_deg is not None:
                sd["fetlock_extension_deg"] = round(sm.fetlock_extension_deg, 1)
            if sm.hock_flexion_deg is not None:
                sd["hock_flexion_deg"] = round(sm.hock_flexion_deg, 1)
            if sm.suspension_duration_s > 0:
                sd["suspension_duration_s"] = round(sm.suspension_duration_s, 4)
            if sm.overreach_px is not None:
                sd["overreach_px"] = round(sm.overreach_px, 2)
            if sm.acceleration_px_s2 is not None:
                sd["acceleration_px_s2"] = round(sm.acceleration_px_s2, 2)
            if sm.speed_efficiency is not None:
                sd["speed_efficiency"] = round(sm.speed_efficiency, 2)
            if sm.ground_cover_px > 0:
                sd["ground_cover_px"] = round(sm.ground_cover_px, 2)
            if sm.ground_cover_m is not None:
                sd["ground_cover_m"] = round(sm.ground_cover_m, 3)
            d["per_stride"].append(sd)

        if self.speed_profile is not None:
            d["speed_profile"] = {
                "speeds_px_s": [round(s, 2) for s in self.speed_profile.speeds_px_s],
                "accelerations_px_s2": [round(a, 2) for a in self.speed_profile.accelerations_px_s2],
                "peak_speed_px_s": round(self.speed_profile.peak_speed_px_s, 2),
                "mean_acceleration_px_s2": round(self.speed_profile.mean_acceleration_px_s2, 2),
            }
        if self.movement_quality is not None:
            d["movement_quality"] = {
                "overall_score": round(self.movement_quality.overall_score, 1),
                "stride_regularity": round(self.movement_quality.stride_regularity, 1),
                "symmetry_score": round(self.movement_quality.symmetry_score, 1),
                "reach_score": round(self.movement_quality.reach_score, 1),
                "suspension_score": round(self.movement_quality.suspension_score, 1),
                "engagement_score": round(self.movement_quality.engagement_score, 1),
            }
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

    # Assign suspension durations per stride
    for sp in gait.suspension_phases:
        if sp.stride_index is not None and sp.stride_index < len(stride_metrics_list):
            stride_metrics_list[sp.stride_index].suspension_duration_s += sp.duration_s

    # Assign overreach per stride
    for oe in gait.overreach_events:
        if oe.stride_index is not None and oe.stride_index < len(stride_metrics_list):
            sm = stride_metrics_list[oe.stride_index]
            if sm.overreach_px is None:
                sm.overreach_px = oe.overreach_px
                sm.overreach_m = oe.overreach_m

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

    # Phase 3: new angle aggregations
    topline_angles = [s.topline_angle_deg for s in stride_metrics_list if s.topline_angle_deg is not None]
    if topline_angles:
        metrics.mean_topline_angle_deg = float(np.mean(topline_angles))

    knee_angles = [s.knee_flexion_deg for s in stride_metrics_list if s.knee_flexion_deg is not None]
    if knee_angles:
        metrics.mean_knee_flexion_deg = float(np.mean(knee_angles))

    fetlock_angles = [s.fetlock_extension_deg for s in stride_metrics_list if s.fetlock_extension_deg is not None]
    if fetlock_angles:
        metrics.mean_fetlock_extension_deg = float(np.mean(fetlock_angles))

    hock_angles = [s.hock_flexion_deg for s in stride_metrics_list if s.hock_flexion_deg is not None]
    if hock_angles:
        metrics.mean_hock_flexion_deg = float(np.mean(hock_angles))

    # Symmetry
    symmetries = [s.lateral_symmetry_index for s in stride_metrics_list if s.lateral_symmetry_index is not None]
    if symmetries:
        metrics.mean_lateral_symmetry = float(np.mean(symmetries))

    # Phase 3: suspension
    susp_durs = [s.suspension_duration_s for s in stride_metrics_list if s.suspension_duration_s > 0]
    if susp_durs:
        metrics.mean_suspension_duration_s = float(np.mean(susp_durs))
        if metrics.mean_stride_duration_s > 0:
            metrics.suspension_ratio = metrics.mean_suspension_duration_s / metrics.mean_stride_duration_s
    gait.total_suspension_frames = sum(sp.duration_frames for sp in gait.suspension_phases)

    # Phase 3: overreach
    overreach_vals = [oe.overreach_px for oe in gait.overreach_events]
    if overreach_vals:
        metrics.mean_overreach_px = float(np.mean(overreach_vals))
        if px_per_meter is not None:
            metrics.mean_overreach_m = metrics.mean_overreach_px / px_per_meter

    # Ground cover per stride
    ground_covers = [s.ground_cover_px for s in stride_metrics_list if s.ground_cover_px > 0]
    if ground_covers:
        metrics.mean_ground_cover_px = float(np.mean(ground_covers))
        if px_per_meter is not None:
            metrics.mean_ground_cover_m = metrics.mean_ground_cover_px / px_per_meter

    # Phase 3: speed profile and acceleration
    metrics.speed_profile = _compute_speed_profile(stride_metrics_list, px_per_meter)

    # Phase 3: speed efficiency index
    if metrics.mean_speed_px_s > 0 and metrics.mean_stride_frequency_hz > 0:
        metrics.speed_efficiency_index = metrics.mean_speed_px_s / metrics.mean_stride_frequency_hz

    # Compute per-stride acceleration and efficiency
    for i, sm in enumerate(stride_metrics_list):
        if i > 0 and stride_metrics_list[i - 1].estimated_speed_px_s > 0:
            dt = sm.stride_duration_s
            if dt > 0:
                sm.acceleration_px_s2 = (sm.estimated_speed_px_s - stride_metrics_list[i - 1].estimated_speed_px_s) / dt
        if sm.stride_frequency_hz > 0:
            sm.speed_efficiency = sm.estimated_speed_px_s / sm.stride_frequency_hz

    # Phase 3: movement quality composite score
    metrics.movement_quality = _compute_movement_quality(metrics)

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

    # --- Phase 3: Topline angle ---
    sm.topline_angle_deg = _compute_topline_angle(seg_kpts, seg_conf)

    # --- Knee flexion (fore) ---
    sm.knee_flexion_deg = _compute_knee_flexion(seg_kpts, seg_conf)

    # --- Phase 3: Fetlock extension ---
    sm.fetlock_extension_deg = _compute_fetlock_extension(seg_kpts, seg_conf)

    # --- Phase 3: Hock flexion ---
    sm.hock_flexion_deg = _compute_hock_flexion(seg_kpts, seg_conf)

    # --- Ground cover per stride (centroid horizontal displacement) ---
    sm.ground_cover_px = _compute_ground_cover(seg_kpts, seg_conf)
    if px_per_meter is not None and sm.ground_cover_px > 0:
        sm.ground_cover_m = sm.ground_cover_px / px_per_meter

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


# ---------- Phase 3: new angle metrics ----------


def _compute_topline_angle(kpts: np.ndarray, conf: np.ndarray) -> float | None:
    """Compute mean topline angle (withers-mid_back-croup) across a stride.

    Measures the straightness of the back. Angles near 180 = flat back,
    lower angles indicate more curvature.
    """
    withers_id = KEYPOINT_NAME_TO_ID["withers"]
    mid_back_id = KEYPOINT_NAME_TO_ID["mid_back"]
    croup_id = KEYPOINT_NAME_TO_ID["croup"]

    angles = []
    for t in range(len(kpts)):
        if conf[t, withers_id] < 0.3 or conf[t, mid_back_id] < 0.3 or conf[t, croup_id] < 0.3:
            continue
        angle = _angle_3pt(kpts[t, withers_id], kpts[t, mid_back_id], kpts[t, croup_id])
        angles.append(angle)

    return float(np.mean(angles)) if angles else None


def _compute_knee_flexion(kpts: np.ndarray, conf: np.ndarray) -> float | None:
    """Compute fore knee (carpus) flexion at maximum flexion during swing phase.

    Measures the angle at the carpus (elbow-knee-fetlock) at the frame where
    the knee angle is smallest (peak flexion). Lower angles indicate more
    knee lift — associated with limb clearance and action quality.
    """
    elbow_id = KEYPOINT_NAME_TO_ID["l_elbow"]
    knee_id = KEYPOINT_NAME_TO_ID["l_knee_fore"]
    fetlock_id = KEYPOINT_NAME_TO_ID["l_fetlock_fore"]

    valid = (
        (conf[:, elbow_id] >= 0.3)
        & (conf[:, knee_id] >= 0.3)
        & (conf[:, fetlock_id] >= 0.3)
    )

    if valid.sum() < 3:
        elbow_id = KEYPOINT_NAME_TO_ID["r_elbow"]
        knee_id = KEYPOINT_NAME_TO_ID["r_knee_fore"]
        fetlock_id = KEYPOINT_NAME_TO_ID["r_fetlock_fore"]
        valid = (
            (conf[:, elbow_id] >= 0.3)
            & (conf[:, knee_id] >= 0.3)
            & (conf[:, fetlock_id] >= 0.3)
        )

    if valid.sum() < 3:
        return None

    # Compute angle at each valid frame, return minimum (peak flexion)
    angles = []
    valid_indices = np.where(valid)[0]
    for fi in valid_indices:
        a = _angle_3pt(kpts[fi, elbow_id], kpts[fi, knee_id], kpts[fi, fetlock_id])
        angles.append(a)

    return float(min(angles))


def _compute_fetlock_extension(kpts: np.ndarray, conf: np.ndarray) -> float | None:
    """Compute fetlock extension angle at maximum extension.

    Measures the angle at the fetlock (knee-fetlock-hoof) at the frame
    where the fetlock is at its lowest point (maximum dorsiflexion / extension).
    Lower angles indicate more fetlock drop — associated with soft tissue compliance.
    """
    # Try left fore first
    knee_id = KEYPOINT_NAME_TO_ID["l_knee_fore"]
    fetlock_id = KEYPOINT_NAME_TO_ID["l_fetlock_fore"]
    hoof_id = KEYPOINT_NAME_TO_ID["l_fore_hoof"]

    valid = (
        (conf[:, knee_id] >= 0.3)
        & (conf[:, fetlock_id] >= 0.3)
        & (conf[:, hoof_id] >= 0.3)
    )

    if valid.sum() < 3:
        knee_id = KEYPOINT_NAME_TO_ID["r_knee_fore"]
        fetlock_id = KEYPOINT_NAME_TO_ID["r_fetlock_fore"]
        hoof_id = KEYPOINT_NAME_TO_ID["r_fore_hoof"]
        valid = (
            (conf[:, knee_id] >= 0.3)
            & (conf[:, fetlock_id] >= 0.3)
            & (conf[:, hoof_id] >= 0.3)
        )

    if valid.sum() < 3:
        return None

    # Find frame of maximum fetlock drop (highest y = lowest position)
    fetlock_y = kpts[valid, fetlock_id, 1]
    best_frame_relative = int(np.argmax(fetlock_y))
    valid_indices = np.where(valid)[0]
    best_frame = valid_indices[best_frame_relative]

    angle = _angle_3pt(
        kpts[best_frame, knee_id],
        kpts[best_frame, fetlock_id],
        kpts[best_frame, hoof_id],
    )
    return angle


def _compute_hock_flexion(kpts: np.ndarray, conf: np.ndarray) -> float | None:
    """Compute hock flexion angle at maximum flexion.

    Measures the angle at the hock (hip-hock-hind_hoof) at the frame where
    the hock is most flexed (smallest angle). Lower hock angles during
    swing phase indicate better joint flexibility.
    """
    hip_id = KEYPOINT_NAME_TO_ID["l_hip"]
    hock_id = KEYPOINT_NAME_TO_ID["l_hock"]
    hoof_id = KEYPOINT_NAME_TO_ID["l_hind_hoof"]

    valid = (
        (conf[:, hip_id] >= 0.3)
        & (conf[:, hock_id] >= 0.3)
        & (conf[:, hoof_id] >= 0.3)
    )

    if valid.sum() < 3:
        hip_id = KEYPOINT_NAME_TO_ID["r_hip"]
        hock_id = KEYPOINT_NAME_TO_ID["r_hock"]
        hoof_id = KEYPOINT_NAME_TO_ID["r_hind_hoof"]
        valid = (
            (conf[:, hip_id] >= 0.3)
            & (conf[:, hock_id] >= 0.3)
            & (conf[:, hoof_id] >= 0.3)
        )

    if valid.sum() < 3:
        return None

    # Find frame of minimum hock angle (maximum flexion)
    angles = []
    valid_indices = np.where(valid)[0]
    for fi in valid_indices:
        a = _angle_3pt(kpts[fi, hip_id], kpts[fi, hock_id], kpts[fi, hoof_id])
        angles.append(a)

    return float(min(angles))


def _compute_ground_cover(kpts: np.ndarray, conf: np.ndarray) -> float:
    """Compute horizontal displacement of the horse centroid across a stride.

    Uses the mean x-position of all visible keypoints as the centroid,
    and measures horizontal displacement from stride start to stride end.
    This differs from stride_length (withers-only) by using the full body centroid.
    """
    T = len(kpts)
    if T < 2:
        return 0.0

    # Compute centroid x at first and last frame from all visible keypoints
    def _centroid_x(frame_idx: int) -> float | None:
        visible = conf[frame_idx] >= 0.3
        if visible.sum() < 3:
            return None
        return float(np.mean(kpts[frame_idx, visible, 0]))

    x_start = _centroid_x(0)
    x_end = _centroid_x(T - 1)

    if x_start is None or x_end is None:
        return 0.0

    return abs(x_end - x_start)


# ---------- Phase 3: speed profile ----------


def _compute_speed_profile(
    stride_metrics: list[StrideMetrics],
    px_per_meter: float | None = None,
) -> SpeedProfile:
    """Build a speed profile across successive strides."""
    profile = SpeedProfile()
    speeds = [sm.estimated_speed_px_s for sm in stride_metrics]
    profile.speeds_px_s = speeds

    if px_per_meter is not None:
        profile.speeds_m_s = [s / px_per_meter for s in speeds]
        if profile.speeds_m_s:
            profile.peak_speed_m_s = max(profile.speeds_m_s)

    if speeds:
        profile.peak_speed_px_s = max(speeds)

    # Acceleration between consecutive strides
    accels = []
    for i in range(1, len(stride_metrics)):
        dt = stride_metrics[i].stride_duration_s
        if dt > 0:
            accel = (speeds[i] - speeds[i - 1]) / dt
            accels.append(accel)

    profile.accelerations_px_s2 = accels
    if accels:
        profile.mean_acceleration_px_s2 = float(np.mean(accels))
        profile.max_acceleration_px_s2 = float(max(accels))
        profile.min_acceleration_px_s2 = float(min(accels))

    return profile


# ---------- Phase 3: movement quality composite score ----------


def _compute_movement_quality(metrics: HorseMetrics) -> MovementQuality:
    """Compute a composite movement quality score (0-100).

    Components (all scored 0-100, then weighted):
    - Stride regularity (25%): from stride_length_cv (lower CV = higher score)
    - Symmetry (20%): from lateral symmetry (lower diff = higher score)
    - Reach (20%): from overreach distance (more positive = higher score)
    - Suspension (15%): from suspension ratio (higher = higher score, up to ~15%)
    - Engagement (20%): from hindlimb engagement angle (lower = more engaged)
    """
    mq = MovementQuality()

    # Stride regularity: CV of 0 = perfect (100), CV of 0.3+ = poor (0)
    if metrics.stride_length_cv >= 0:
        mq.stride_regularity = max(0.0, 100.0 * (1.0 - metrics.stride_length_cv / 0.3))
    else:
        mq.stride_regularity = 50.0

    # Symmetry: 0% diff = perfect (100), 30%+ diff = poor (0)
    if metrics.mean_lateral_symmetry is not None:
        mq.symmetry_score = max(0.0, 100.0 * (1.0 - metrics.mean_lateral_symmetry / 30.0))
    else:
        mq.symmetry_score = 50.0  # no data, neutral

    # Reach: overreach of 50+ px = excellent (100), 0 or negative = poor (0)
    if metrics.mean_overreach_px > 0:
        mq.reach_score = min(100.0, metrics.mean_overreach_px * 2.0)
    else:
        mq.reach_score = max(0.0, 50.0 + metrics.mean_overreach_px * 2.0)

    # Suspension: ratio of 0.10-0.15 = excellent (100), 0 = none (0)
    if metrics.suspension_ratio > 0:
        mq.suspension_score = min(100.0, metrics.suspension_ratio / 0.12 * 100.0)
    else:
        mq.suspension_score = 0.0

    # Engagement: lower angle = more engaged. 40-60 deg = excellent (100), 120+ = poor (0)
    if metrics.mean_hindlimb_engagement_deg is not None:
        eng = metrics.mean_hindlimb_engagement_deg
        mq.engagement_score = max(0.0, min(100.0, (120.0 - eng) / 80.0 * 100.0))
    else:
        mq.engagement_score = 50.0

    # Weighted composite
    weights = {
        "stride_regularity": 0.25,
        "symmetry": 0.20,
        "reach": 0.20,
        "suspension": 0.15,
        "engagement": 0.20,
    }

    mq.overall_score = (
        mq.stride_regularity * weights["stride_regularity"]
        + mq.symmetry_score * weights["symmetry"]
        + mq.reach_score * weights["reach"]
        + mq.suspension_score * weights["suspension"]
        + mq.engagement_score * weights["engagement"]
    )

    mq.components = {
        "stride_regularity": round(mq.stride_regularity, 1),
        "symmetry": round(mq.symmetry_score, 1),
        "reach": round(mq.reach_score, 1),
        "suspension": round(mq.suspension_score, 1),
        "engagement": round(mq.engagement_score, 1),
    }

    return mq


# ---------- Phase 3: horse-to-horse comparison ----------


def compare_horses(horses: list[HorseMetrics]) -> dict:
    """Compare metrics across multiple horses for side-by-side analysis.

    Returns a structured comparison with rankings per metric.
    """
    if len(horses) < 2:
        return {"error": "Need at least 2 horses to compare", "horses": []}

    comparison = {
        "num_horses": len(horses),
        "horses": [],
        "rankings": {},
    }

    metric_keys = [
        ("mean_stride_length_px", "higher"),
        ("mean_stride_frequency_hz", "higher"),
        ("mean_speed_px_s", "higher"),
        ("stride_length_cv", "lower"),
        ("mean_withers_displacement_px", "info"),
        ("mean_overreach_px", "higher"),
        ("mean_suspension_duration_s", "higher"),
        ("suspension_ratio", "higher"),
    ]

    # Collect per-horse summaries
    for h in horses:
        summary = h.to_dict()
        if h.movement_quality is not None:
            summary["movement_quality_score"] = round(h.movement_quality.overall_score, 1)
        comparison["horses"].append(summary)

    # Rank horses per metric
    for key, direction in metric_keys:
        values = []
        for i, h in enumerate(horses):
            val = getattr(h, key, None)
            if val is None:
                d = h.to_dict()
                val = d.get(key)
            values.append((i, val if val is not None else 0.0))

        reverse = direction == "higher"
        ranked = sorted(values, key=lambda x: x[1], reverse=reverse)
        comparison["rankings"][key] = [
            {"horse_index": idx, "value": round(val, 3), "rank": rank + 1}
            for rank, (idx, val) in enumerate(ranked)
        ]

    # Overall movement quality ranking
    quality_vals = []
    for i, h in enumerate(horses):
        score = h.movement_quality.overall_score if h.movement_quality else 0.0
        quality_vals.append((i, score))
    quality_ranked = sorted(quality_vals, key=lambda x: x[1], reverse=True)
    comparison["rankings"]["movement_quality"] = [
        {"horse_index": idx, "value": round(val, 1), "rank": rank + 1}
        for rank, (idx, val) in enumerate(quality_ranked)
    ]

    return comparison
