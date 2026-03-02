"""Pixel-to-real-world calibration for distance and speed measurements.

Supports:
- Manual calibration via known reference distances (rail height, track markers).
- Homography-based perspective correction from 4+ point correspondences.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import cv2
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class Calibration:
    """Calibration parameters for pixel-to-metric conversion."""
    px_per_meter: float
    method: str  # "reference_distance" or "homography"
    homography_matrix: np.ndarray | None = None

    def px_to_meters(self, px_distance: float) -> float:
        return px_distance / self.px_per_meter

    def meters_to_px(self, meters: float) -> float:
        return meters * self.px_per_meter


def calibrate_from_reference(
    point_a: tuple[float, float],
    point_b: tuple[float, float],
    known_distance_m: float,
) -> Calibration:
    """Calibrate using two points with a known real-world distance.

    Common references:
    - Standard rail height: ~1.07m (42 inches)
    - Track width: varies by venue
    - Horse height at withers: ~1.55-1.70m for Thoroughbreds

    Args:
        point_a: (x, y) pixel coordinates of reference point A.
        point_b: (x, y) pixel coordinates of reference point B.
        known_distance_m: Real-world distance between A and B in meters.

    Returns:
        Calibration with computed px_per_meter.
    """
    px_distance = np.sqrt(
        (point_b[0] - point_a[0]) ** 2 + (point_b[1] - point_a[1]) ** 2
    )

    if px_distance < 1 or known_distance_m <= 0:
        raise ValueError("Invalid reference points or distance")

    px_per_meter = px_distance / known_distance_m
    logger.info("Calibrated: %.2f px/m from reference distance %.2fm", px_per_meter, known_distance_m)

    return Calibration(px_per_meter=px_per_meter, method="reference_distance")


def calibrate_from_homography(
    image_points: np.ndarray,
    world_points: np.ndarray,
) -> Calibration:
    """Calibrate using a homography from 4+ point correspondences.

    Maps image plane to ground plane for perspective correction.
    Useful when the camera is at an angle to the track.

    Args:
        image_points: (N, 2) pixel coordinates of reference points.
        world_points: (N, 2) real-world coordinates in meters.

    Returns:
        Calibration with homography matrix and estimated px_per_meter.
    """
    if len(image_points) < 4 or len(world_points) < 4:
        raise ValueError("At least 4 point correspondences required for homography")

    H, mask = cv2.findHomography(
        image_points.astype(np.float64),
        world_points.astype(np.float64),
        cv2.RANSAC,
        5.0,
    )

    if H is None:
        raise RuntimeError("Failed to compute homography")

    # Estimate px_per_meter from the homography scale
    # Use the first two points as a reference
    p1_img = image_points[0]
    p2_img = image_points[1]
    p1_world = world_points[0]
    p2_world = world_points[1]

    px_dist = np.linalg.norm(p2_img - p1_img)
    world_dist = np.linalg.norm(p2_world - p1_world)
    px_per_meter = px_dist / world_dist if world_dist > 0 else 1.0

    logger.info("Homography calibrated: %.2f px/m", px_per_meter)

    return Calibration(
        px_per_meter=px_per_meter,
        method="homography",
        homography_matrix=H,
    )


def transform_point(
    calibration: Calibration,
    point: tuple[float, float],
) -> tuple[float, float]:
    """Transform a pixel coordinate to real-world coordinates using homography.

    Args:
        calibration: Must have been created with calibrate_from_homography.
        point: (x, y) pixel coordinates.

    Returns:
        (x, y) real-world coordinates in meters.
    """
    if calibration.homography_matrix is None:
        raise ValueError("Calibration does not have a homography matrix")

    pt = np.array([[[point[0], point[1]]]], dtype=np.float64)
    transformed = cv2.perspectiveTransform(pt, calibration.homography_matrix)
    return (float(transformed[0, 0, 0]), float(transformed[0, 0, 1]))
