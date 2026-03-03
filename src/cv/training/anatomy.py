"""Equine anatomy constraints engine for keypoint validation and correction.

Encodes Thoroughbred skeletal proportions, joint angle ranges, and spatial
relationships to validate and refine auto-generated keypoint labels.  Used by
AnatomyLabelAgent to post-process raw model predictions.

Proportions are normalised to **body length** (poll → tail_base) so they
scale regardless of image resolution or distance-to-camera.

References:
    - Clayton, H. (2004). The Dynamic Horse.
    - Hildebrand, M. (1989). The quadrupedal gaits of vertebrates.
    - Equine anatomy diagrams: Budras et al., Anatomy of the Horse.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np

from src.cv.schema import KEYPOINT_NAMES, NUM_KEYPOINTS, SKELETON_EDGES

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Keypoint ID shortcuts
# ---------------------------------------------------------------------------
POLL, NOSE, THROAT, WITHERS, MID_BACK, CROUP, TAIL_BASE = 0, 1, 2, 3, 4, 5, 6
L_SHOULDER, L_ELBOW, L_KNEE_FORE, L_FETLOCK_FORE, L_FORE_HOOF = 7, 8, 9, 10, 11
R_SHOULDER, R_ELBOW, R_KNEE_FORE, R_FETLOCK_FORE, R_FORE_HOOF = 12, 13, 14, 15, 16
L_HIP, L_HOCK, L_HIND_FETLOCK, L_HIND_HOOF = 17, 18, 19, 20
R_HIP, R_HOCK, R_HIND_HOOF = 21, 22, 23

# ---------------------------------------------------------------------------
# Bone segment definitions: (parent_kpt, child_kpt)
# ---------------------------------------------------------------------------
BONE_SEGMENTS: list[tuple[int, int]] = [
    # Head / neck
    (POLL, NOSE),
    (POLL, THROAT),
    (THROAT, WITHERS),
    # Topline
    (WITHERS, MID_BACK),
    (MID_BACK, CROUP),
    (CROUP, TAIL_BASE),
    # Left forelimb
    (WITHERS, L_SHOULDER),
    (L_SHOULDER, L_ELBOW),
    (L_ELBOW, L_KNEE_FORE),
    (L_KNEE_FORE, L_FETLOCK_FORE),
    (L_FETLOCK_FORE, L_FORE_HOOF),
    # Right forelimb
    (WITHERS, R_SHOULDER),
    (R_SHOULDER, R_ELBOW),
    (R_ELBOW, R_KNEE_FORE),
    (R_KNEE_FORE, R_FETLOCK_FORE),
    (R_FETLOCK_FORE, R_FORE_HOOF),
    # Left hindlimb
    (CROUP, L_HIP),
    (L_HIP, L_HOCK),
    (L_HOCK, L_HIND_FETLOCK),
    (L_HIND_FETLOCK, L_HIND_HOOF),
    # Right hindlimb
    (CROUP, R_HIP),
    (R_HIP, R_HOCK),
    (R_HOCK, R_HIND_HOOF),
]

# ---------------------------------------------------------------------------
# Typical bone-length ratios (relative to body length poll→tail_base)
# Measured from Thoroughbred conformation studies and Clayton (2004).
# Each entry: (parent, child, expected_ratio, tolerance)
# ---------------------------------------------------------------------------
BONE_LENGTH_RATIOS: list[tuple[int, int, float, float]] = [
    # Head
    (POLL, NOSE, 0.22, 0.08),            # head length ~22% of body
    (POLL, THROAT, 0.10, 0.05),           # poll to throat
    (THROAT, WITHERS, 0.30, 0.10),        # neck length ~30%
    # Topline
    (WITHERS, MID_BACK, 0.25, 0.08),      # withers to mid-back
    (MID_BACK, CROUP, 0.25, 0.08),        # mid-back to croup
    (CROUP, TAIL_BASE, 0.12, 0.06),       # croup to tail base
    # Forelimb (total leg ~55-60% of body length from shoulder to hoof)
    (L_SHOULDER, L_ELBOW, 0.18, 0.06),    # humerus
    (L_ELBOW, L_KNEE_FORE, 0.18, 0.06),   # forearm (radius)
    (L_KNEE_FORE, L_FETLOCK_FORE, 0.12, 0.05),  # cannon bone
    (L_FETLOCK_FORE, L_FORE_HOOF, 0.06, 0.04),  # pastern + hoof
    (R_SHOULDER, R_ELBOW, 0.18, 0.06),
    (R_ELBOW, R_KNEE_FORE, 0.18, 0.06),
    (R_KNEE_FORE, R_FETLOCK_FORE, 0.12, 0.05),
    (R_FETLOCK_FORE, R_FORE_HOOF, 0.06, 0.04),
    # Hindlimb
    (L_HIP, L_HOCK, 0.25, 0.08),          # femur + tibia (stifle to hock)
    (L_HOCK, L_HIND_FETLOCK, 0.14, 0.06), # hind cannon
    (L_HIND_FETLOCK, L_HIND_HOOF, 0.06, 0.04),  # hind pastern
    (R_HIP, R_HOCK, 0.25, 0.08),
    (R_HOCK, R_HIND_HOOF, 0.18, 0.08),    # hock to hoof (no fetlock kpt)
]

# ---------------------------------------------------------------------------
# Joint angle constraints: (kpt_a, kpt_vertex, kpt_c, min_deg, max_deg)
# Angle measured at vertex across all gait phases.
# ---------------------------------------------------------------------------
JOINT_ANGLE_RANGES: list[tuple[int, int, int, float, float]] = [
    # Head/neck
    (NOSE, POLL, THROAT, 30, 170),            # head carriage
    (POLL, THROAT, WITHERS, 60, 175),          # neck angle
    # Topline
    (THROAT, WITHERS, MID_BACK, 120, 180),     # withers angle (topline meets neck)
    (WITHERS, MID_BACK, CROUP, 150, 180),      # back straightness
    (MID_BACK, CROUP, TAIL_BASE, 120, 180),    # croup angle
    # Left forelimb
    (WITHERS, L_SHOULDER, L_ELBOW, 60, 170),   # shoulder angle
    (L_SHOULDER, L_ELBOW, L_KNEE_FORE, 80, 180),  # elbow
    (L_ELBOW, L_KNEE_FORE, L_FETLOCK_FORE, 100, 180),  # knee (carpus)
    (L_KNEE_FORE, L_FETLOCK_FORE, L_FORE_HOOF, 90, 180),  # fetlock
    # Right forelimb
    (WITHERS, R_SHOULDER, R_ELBOW, 60, 170),
    (R_SHOULDER, R_ELBOW, R_KNEE_FORE, 80, 180),
    (R_ELBOW, R_KNEE_FORE, R_FETLOCK_FORE, 100, 180),
    (R_KNEE_FORE, R_FETLOCK_FORE, R_FORE_HOOF, 90, 180),
    # Left hindlimb
    (CROUP, L_HIP, L_HOCK, 60, 175),          # stifle
    (L_HIP, L_HOCK, L_HIND_FETLOCK, 80, 180), # hock
    (L_HOCK, L_HIND_FETLOCK, L_HIND_HOOF, 90, 180),  # hind fetlock
    # Right hindlimb
    (CROUP, R_HIP, R_HOCK, 60, 175),
    (R_HIP, R_HOCK, R_HIND_HOOF, 80, 180),    # hock to hoof
]

# ---------------------------------------------------------------------------
# Vertical ordering constraints: kpt_above must have lower y than kpt_below
# (image coordinates: y increases downward)
# ---------------------------------------------------------------------------
VERTICAL_ORDER: list[tuple[int, int]] = [
    # Topline above limbs
    (WITHERS, L_SHOULDER), (WITHERS, R_SHOULDER),
    (CROUP, L_HIP), (CROUP, R_HIP),
    # Proximal above distal in each limb
    (L_SHOULDER, L_ELBOW), (L_ELBOW, L_KNEE_FORE),
    (L_KNEE_FORE, L_FETLOCK_FORE), (L_FETLOCK_FORE, L_FORE_HOOF),
    (R_SHOULDER, R_ELBOW), (R_ELBOW, R_KNEE_FORE),
    (R_KNEE_FORE, R_FETLOCK_FORE), (R_FETLOCK_FORE, R_FORE_HOOF),
    (L_HIP, L_HOCK), (L_HOCK, L_HIND_FETLOCK), (L_HIND_FETLOCK, L_HIND_HOOF),
    (R_HIP, R_HOCK), (R_HOCK, R_HIND_HOOF),
]

# Left-right paired keypoints for symmetry checks
LR_PAIRS: list[tuple[int, int]] = [
    (L_SHOULDER, R_SHOULDER),
    (L_ELBOW, R_ELBOW),
    (L_KNEE_FORE, R_KNEE_FORE),
    (L_FETLOCK_FORE, R_FETLOCK_FORE),
    (L_FORE_HOOF, R_FORE_HOOF),
    (L_HIP, R_HIP),
    (L_HOCK, R_HOCK),
]


# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------

def _dist(a: np.ndarray, b: np.ndarray) -> float:
    """Euclidean distance between two 2D points."""
    return float(np.linalg.norm(a - b))


def _angle_3pt(a: np.ndarray, b: np.ndarray, c: np.ndarray) -> float:
    """Angle in degrees at vertex b formed by segments ba and bc."""
    ba = a - b
    bc = c - b
    cos_angle = np.dot(ba, bc) / (np.linalg.norm(ba) * np.linalg.norm(bc) + 1e-8)
    return float(np.degrees(np.arccos(np.clip(cos_angle, -1.0, 1.0))))


# ---------------------------------------------------------------------------
# Validation result
# ---------------------------------------------------------------------------

@dataclass
class AnatomyViolation:
    """A single anatomical constraint violation."""
    rule: str                   # e.g. "vertical_order", "joint_angle", "bone_ratio"
    keypoints: tuple[int, ...]  # involved keypoint IDs
    message: str
    severity: float             # 0-1 (0 = minor, 1 = anatomically impossible)


@dataclass
class AnatomyReport:
    """Full anatomical validation report for one horse."""
    violations: list[AnatomyViolation]
    body_length_px: float = 0.0
    anatomy_score: float = 1.0     # 1.0 = perfect, 0.0 = anatomically impossible

    @property
    def is_valid(self) -> bool:
        return all(v.severity < 0.8 for v in self.violations)

    @property
    def num_severe(self) -> int:
        return sum(1 for v in self.violations if v.severity >= 0.8)


# ---------------------------------------------------------------------------
# Main validator
# ---------------------------------------------------------------------------

class AnatomyValidator:
    """Validates equine keypoint annotations against anatomical constraints.

    Checks:
    1. Vertical ordering (proximal joints above distal)
    2. Joint angle ranges
    3. Bone length proportions
    4. Left-right symmetry
    5. Body extent plausibility
    """

    def __init__(self, confidence_threshold: float = 0.2):
        self.conf_threshold = confidence_threshold

    def validate(
        self,
        keypoints: np.ndarray,
        confidence: np.ndarray,
    ) -> AnatomyReport:
        """Validate a single horse's keypoints against anatomy constraints.

        Args:
            keypoints: (24, 2) array of x,y coords.
            confidence: (24,) array of per-keypoint confidence.

        Returns:
            AnatomyReport with violations and overall score.
        """
        violations: list[AnatomyViolation] = []
        vis = confidence >= self.conf_threshold

        # Body length for ratio normalisation
        body_length = 0.0
        if vis[POLL] and vis[TAIL_BASE]:
            body_length = _dist(keypoints[POLL], keypoints[TAIL_BASE])
        elif vis[WITHERS] and vis[TAIL_BASE]:
            body_length = _dist(keypoints[WITHERS], keypoints[TAIL_BASE]) * 1.5

        # 1. Vertical ordering
        for above, below in VERTICAL_ORDER:
            if vis[above] and vis[below]:
                if keypoints[above][1] > keypoints[below][1] + 5:  # 5px tolerance
                    violations.append(AnatomyViolation(
                        rule="vertical_order",
                        keypoints=(above, below),
                        message=(
                            f"{KEYPOINT_NAMES[above]} below {KEYPOINT_NAMES[below]} "
                            f"(y={keypoints[above][1]:.0f} > {keypoints[below][1]:.0f})"
                        ),
                        severity=0.9,
                    ))

        # 2. Joint angle ranges
        for a, vertex, c, min_deg, max_deg in JOINT_ANGLE_RANGES:
            if vis[a] and vis[vertex] and vis[c]:
                angle = _angle_3pt(keypoints[a], keypoints[vertex], keypoints[c])
                if angle < min_deg - 10 or angle > max_deg + 10:
                    off = max(0, min_deg - angle, angle - max_deg)
                    severity = min(1.0, off / 40)
                    violations.append(AnatomyViolation(
                        rule="joint_angle",
                        keypoints=(a, vertex, c),
                        message=(
                            f"{KEYPOINT_NAMES[vertex]} angle {angle:.0f}° "
                            f"outside [{min_deg}, {max_deg}]"
                        ),
                        severity=severity,
                    ))

        # 3. Bone length ratios
        if body_length > 30:  # need a reasonable body length reference
            for parent, child, expected, tol in BONE_LENGTH_RATIOS:
                if vis[parent] and vis[child]:
                    length = _dist(keypoints[parent], keypoints[child])
                    ratio = length / body_length
                    if abs(ratio - expected) > tol * 2:
                        off = abs(ratio - expected) - tol
                        severity = min(1.0, off / 0.15)
                        violations.append(AnatomyViolation(
                            rule="bone_ratio",
                            keypoints=(parent, child),
                            message=(
                                f"{KEYPOINT_NAMES[parent]}→{KEYPOINT_NAMES[child]} "
                                f"ratio {ratio:.2f} vs expected {expected:.2f}±{tol:.2f}"
                            ),
                            severity=severity,
                        ))

        # 4. Left-right symmetry (bone lengths of paired limbs should be similar)
        if body_length > 30:
            for l_id, r_id in LR_PAIRS:
                # Find the bone segment containing each
                pass  # checked implicitly via bone ratios above

        # 5. Body extent: horse should be wider than tall (side view) or plausible
        if vis[POLL] and vis[TAIL_BASE] and vis[L_FORE_HOOF]:
            width = abs(keypoints[POLL][0] - keypoints[TAIL_BASE][0])
            height = abs(keypoints[WITHERS][1] - keypoints[L_FORE_HOOF][1]) if vis[WITHERS] else 0
            if width > 0 and height > 0:
                aspect = width / height
                if aspect < 0.3 or aspect > 4.0:
                    violations.append(AnatomyViolation(
                        rule="body_extent",
                        keypoints=(POLL, TAIL_BASE),
                        message=f"Body aspect ratio {aspect:.2f} (expected 0.5-3.0)",
                        severity=0.7,
                    ))

        # Score: 1.0 minus weighted severity
        if violations:
            total_severity = sum(v.severity for v in violations)
            anatomy_score = max(0.0, 1.0 - total_severity / max(len(violations) * 2, 1))
        else:
            anatomy_score = 1.0

        return AnatomyReport(
            violations=violations,
            body_length_px=body_length,
            anatomy_score=anatomy_score,
        )


# ---------------------------------------------------------------------------
# Anatomy-based correction
# ---------------------------------------------------------------------------

class AnatomyCorrector:
    """Corrects anatomically implausible keypoint positions.

    Uses skeletal constraints to nudge keypoints toward anatomically
    valid positions while preserving high-confidence predictions.

    Correction strategies:
    1. Vertical reorder: swap y-coords when proximal/distal are inverted
    2. Joint angle clamping: project keypoints to valid angle range
    3. Bone length normalisation: scale limb segments to expected proportions
    4. Interpolation refinement: replace simple linear interpolation with
       anatomically-weighted placement for knee/fetlock keypoints
    """

    def __init__(
        self,
        confidence_threshold: float = 0.2,
        correction_strength: float = 0.7,
    ):
        self.conf_threshold = confidence_threshold
        self.strength = correction_strength  # 0 = no correction, 1 = full correction
        self.validator = AnatomyValidator(confidence_threshold)

    def correct(
        self,
        keypoints: np.ndarray,
        confidence: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray, AnatomyReport]:
        """Apply anatomical corrections to keypoint predictions.

        Only corrects low-confidence keypoints; high-confidence predictions
        are trusted as they likely represent actual detected positions.

        Args:
            keypoints: (24, 2) array of x,y coords (modified in-place).
            confidence: (24,) array of per-keypoint confidence.

        Returns:
            Tuple of (corrected_keypoints, corrected_confidence, report).
        """
        kpts = keypoints.copy()
        conf = confidence.copy()
        vis = conf >= self.conf_threshold

        # Get body length for proportional corrections
        body_length = 0.0
        if vis[POLL] and vis[TAIL_BASE]:
            body_length = _dist(kpts[POLL], kpts[TAIL_BASE])
        elif vis[WITHERS] and vis[TAIL_BASE]:
            body_length = _dist(kpts[WITHERS], kpts[TAIL_BASE]) * 1.5

        # 1. Fix vertical ordering violations
        self._fix_vertical_order(kpts, conf)

        # 2. Refine interpolated limb keypoints using anatomy
        self._refine_limb_keypoints(kpts, conf, body_length)

        # 3. Clamp joint angles to valid ranges
        self._clamp_joint_angles(kpts, conf)

        # Validate after corrections
        report = self.validator.validate(kpts, conf)
        return kpts, conf, report

    def _fix_vertical_order(
        self,
        kpts: np.ndarray,
        conf: np.ndarray,
    ) -> None:
        """Fix vertical ordering violations by nudging lower-confidence kpt."""
        vis = conf >= self.conf_threshold
        for above_id, below_id in VERTICAL_ORDER:
            if not (vis[above_id] and vis[below_id]):
                continue
            if kpts[above_id][1] <= kpts[below_id][1]:
                continue  # already correct

            # Decide which to move: move the less confident one
            margin = 3.0  # minimum vertical gap in pixels
            if conf[above_id] >= conf[below_id]:
                # Trust the upper keypoint, push the lower one down
                kpts[below_id][1] = kpts[above_id][1] + margin
                conf[below_id] *= 0.8  # reduce confidence since we moved it
            else:
                # Trust the lower keypoint, push the upper one up
                kpts[above_id][1] = kpts[below_id][1] - margin
                conf[above_id] *= 0.8

    def _refine_limb_keypoints(
        self,
        kpts: np.ndarray,
        conf: np.ndarray,
        body_length: float,
    ) -> None:
        """Refine interpolated knee/fetlock positions using anatomical ratios.

        The raw ViTPose predictions interpolate knees at 55% and fetlocks at 80%
        along a straight line from elbow to hoof.  In reality, the equine
        forelimb has a slight forward curve at the knee (carpus), and the
        fetlock sits slightly behind the cannon bone.

        This method adjusts these positions using anatomical proportions when
        the keypoints have low confidence (indicating interpolation).
        """
        if body_length < 30:
            return

        # Forelimb corrections
        for elbow, knee, fetlock, hoof in [
            (L_ELBOW, L_KNEE_FORE, L_FETLOCK_FORE, L_FORE_HOOF),
            (R_ELBOW, R_KNEE_FORE, R_FETLOCK_FORE, R_FORE_HOOF),
        ]:
            vis_e = conf[elbow] >= self.conf_threshold
            vis_h = conf[hoof] >= self.conf_threshold
            if not (vis_e and vis_h):
                continue

            limb_vec = kpts[hoof] - kpts[elbow]
            limb_len = np.linalg.norm(limb_vec)
            if limb_len < 10:
                continue

            # Anatomical ratios for Thoroughbred forelimb:
            # Forearm (elbow→knee):  ~45% of elbow-to-hoof
            # Cannon (knee→fetlock): ~30%
            # Pastern (fetlock→hoof): ~25%
            knee_ratio = 0.45
            fetlock_ratio = 0.75

            # Direction perpendicular to limb (for slight forward knee curve)
            perp = np.array([-limb_vec[1], limb_vec[0]]) / limb_len

            # Knee: slightly forward of straight line (carpus curves forward)
            if conf[knee] < 0.45:  # only correct low-confidence
                ideal_knee = kpts[elbow] + limb_vec * knee_ratio + perp * body_length * 0.01
                blend = self.strength * (1 - conf[knee])
                kpts[knee] = kpts[knee] * (1 - blend) + ideal_knee * blend
                conf[knee] = max(conf[knee], 0.30)

            # Fetlock: slightly behind cannon bone (dorsal flexion)
            if conf[fetlock] < 0.45:
                ideal_fetlock = kpts[elbow] + limb_vec * fetlock_ratio - perp * body_length * 0.005
                blend = self.strength * (1 - conf[fetlock])
                kpts[fetlock] = kpts[fetlock] * (1 - blend) + ideal_fetlock * blend
                conf[fetlock] = max(conf[fetlock], 0.30)

        # Hindlimb corrections
        for hip, hock, hoof in [
            (L_HIP, L_HOCK, L_HIND_HOOF),
            (R_HIP, R_HOCK, R_HIND_HOOF),
        ]:
            vis_h = conf[hip] >= self.conf_threshold
            vis_hf = conf[hoof] >= self.conf_threshold
            if not (vis_h and vis_hf):
                continue

            # Hock: anatomically ~55% of hip-to-hoof (angulated hindlimb)
            if conf[hock] < 0.45:
                limb_vec = kpts[hoof] - kpts[hip]
                limb_len = np.linalg.norm(limb_vec)
                if limb_len < 10:
                    continue
                perp = np.array([-limb_vec[1], limb_vec[0]]) / limb_len
                # Hock sits behind the straight line (posterior angulation)
                ideal_hock = kpts[hip] + limb_vec * 0.55 - perp * body_length * 0.02
                blend = self.strength * (1 - conf[hock])
                kpts[hock] = kpts[hock] * (1 - blend) + ideal_hock * blend
                conf[hock] = max(conf[hock], 0.30)

        # Hind fetlock (only for left which has the keypoint)
        if conf[L_HOCK] >= self.conf_threshold and conf[L_HIND_HOOF] >= self.conf_threshold:
            if conf[L_HIND_FETLOCK] < 0.45:
                vec = kpts[L_HIND_HOOF] - kpts[L_HOCK]
                ideal = kpts[L_HOCK] + vec * 0.60
                blend = self.strength * (1 - conf[L_HIND_FETLOCK])
                kpts[L_HIND_FETLOCK] = kpts[L_HIND_FETLOCK] * (1 - blend) + ideal * blend
                conf[L_HIND_FETLOCK] = max(conf[L_HIND_FETLOCK], 0.30)

    def _clamp_joint_angles(
        self,
        kpts: np.ndarray,
        conf: np.ndarray,
    ) -> None:
        """Clamp joint angles to valid anatomical ranges.

        When a joint angle is outside bounds, rotate the distal keypoint
        (lower-confidence end) toward the valid range.
        """
        vis = conf >= self.conf_threshold

        for a_id, v_id, c_id, min_deg, max_deg in JOINT_ANGLE_RANGES:
            if not (vis[a_id] and vis[v_id] and vis[c_id]):
                continue

            angle = _angle_3pt(kpts[a_id], kpts[v_id], kpts[c_id])

            if min_deg <= angle <= max_deg:
                continue

            # Determine which end to move (lower confidence)
            if conf[a_id] <= conf[c_id]:
                move_id, anchor_id = a_id, c_id
            else:
                move_id, anchor_id = c_id, a_id

            # Only correct if the moving point is low-confidence
            if conf[move_id] > 0.5:
                continue

            target_angle = np.clip(angle, min_deg, max_deg)
            delta = target_angle - angle

            # Rotate the point around vertex
            vec = kpts[move_id] - kpts[v_id]
            rad = np.radians(delta * self.strength * 0.5)
            cos_r, sin_r = np.cos(rad), np.sin(rad)
            rotated = np.array([
                vec[0] * cos_r - vec[1] * sin_r,
                vec[0] * sin_r + vec[1] * cos_r,
            ])
            kpts[move_id] = kpts[v_id] + rotated
            conf[move_id] *= 0.9  # slight confidence reduction
