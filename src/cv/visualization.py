"""Visualization utilities for equine gait analysis.

Draws keypoints, skeleton, bounding boxes, and metric overlays on video frames.
Also generates summary charts for gait analysis reports.
"""

from __future__ import annotations

import numpy as np
import cv2

from src.cv.detection import Detection
from src.cv.keypoints import KeypointResult
from src.cv.schema import SKELETON_EDGES, EquineKeypointSchema


def draw_detections(
    frame: np.ndarray,
    detections: list[Detection],
    color: tuple[int, int, int] = (0, 255, 0),
    thickness: int = 2,
) -> np.ndarray:
    """Draw bounding boxes for horse detections on a frame."""
    vis = frame.copy()
    for det in detections:
        x1, y1, x2, y2 = det.bbox.astype(int)
        cv2.rectangle(vis, (x1, y1), (x2, y2), color, thickness)

        label = f"horse {det.confidence:.2f}"
        if det.track_id is not None:
            label = f"#{det.track_id} {det.confidence:.2f}"

        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 1)
        cv2.rectangle(vis, (x1, y1 - th - 8), (x1 + tw + 4, y1), color, -1)
        cv2.putText(vis, label, (x1 + 2, y1 - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 1)

    return vis


def draw_keypoints(
    frame: np.ndarray,
    keypoint_result: KeypointResult,
    confidence_threshold: float = 0.3,
    radius: int = 5,
    draw_skeleton: bool = True,
    skeleton_thickness: int = 2,
) -> np.ndarray:
    """Draw keypoints and skeleton on a frame for a single horse.

    Args:
        frame: BGR image to annotate.
        keypoint_result: Keypoint predictions for one horse.
        confidence_threshold: Only draw keypoints above this confidence.
        radius: Circle radius for keypoints.
        draw_skeleton: Whether to draw skeleton edges.
        skeleton_thickness: Line thickness for skeleton.

    Returns:
        Annotated BGR image.
    """
    vis = frame.copy()
    kpts = keypoint_result.keypoints
    conf = keypoint_result.confidence

    # Draw skeleton edges first (behind keypoints)
    if draw_skeleton:
        for a, b in SKELETON_EDGES:
            if a >= len(conf) or b >= len(conf):
                continue
            if conf[a] < confidence_threshold or conf[b] < confidence_threshold:
                continue

            pt_a = (int(kpts[a, 0]), int(kpts[a, 1]))
            pt_b = (int(kpts[b, 0]), int(kpts[b, 1]))

            # Use color of the first keypoint's group
            color = EquineKeypointSchema.keypoint_color(a)
            cv2.line(vis, pt_a, pt_b, color, skeleton_thickness)

    # Draw keypoints
    for i in range(len(conf)):
        if conf[i] < confidence_threshold:
            continue

        pt = (int(kpts[i, 0]), int(kpts[i, 1]))
        color = EquineKeypointSchema.keypoint_color(i)
        cv2.circle(vis, pt, radius, color, -1)
        cv2.circle(vis, pt, radius, (0, 0, 0), 1)  # outline

    return vis


def draw_frame_overlay(
    frame: np.ndarray,
    detections: list[Detection],
    keypoint_results: list[KeypointResult],
    frame_idx: int,
    confidence_threshold: float = 0.3,
) -> np.ndarray:
    """Draw complete overlay on a frame: boxes, keypoints, skeleton, and frame info."""
    vis = draw_detections(frame, detections)

    for kr in keypoint_results:
        vis = draw_keypoints(vis, kr, confidence_threshold=confidence_threshold)

    # Frame counter
    cv2.putText(
        vis,
        f"Frame: {frame_idx}",
        (10, 30),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.8,
        (255, 255, 255),
        2,
    )
    cv2.putText(
        vis,
        f"Horses: {len(detections)}",
        (10, 60),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        (255, 255, 255),
        2,
    )

    return vis


def draw_metrics_panel(
    frame: np.ndarray,
    stride_freq: float | None = None,
    stride_length_px: float | None = None,
    speed_px_s: float | None = None,
    symmetry: float | None = None,
) -> np.ndarray:
    """Draw a semi-transparent metrics panel in the top-right corner."""
    vis = frame.copy()
    h, w = vis.shape[:2]

    panel_w = 300
    panel_h = 140
    x1 = w - panel_w - 10
    y1 = 10
    x2 = w - 10
    y2 = y1 + panel_h

    # Semi-transparent background
    overlay = vis.copy()
    cv2.rectangle(overlay, (x1, y1), (x2, y2), (0, 0, 0), -1)
    cv2.addWeighted(overlay, 0.6, vis, 0.4, 0, vis)

    # Metrics text
    y_pos = y1 + 25
    font = cv2.FONT_HERSHEY_SIMPLEX
    scale = 0.55
    color = (0, 255, 200)

    if stride_freq is not None:
        cv2.putText(vis, f"Stride Freq: {stride_freq:.2f} Hz", (x1 + 10, y_pos), font, scale, color, 1)
        y_pos += 28

    if stride_length_px is not None:
        cv2.putText(vis, f"Stride Length: {stride_length_px:.0f} px", (x1 + 10, y_pos), font, scale, color, 1)
        y_pos += 28

    if speed_px_s is not None:
        cv2.putText(vis, f"Speed: {speed_px_s:.0f} px/s", (x1 + 10, y_pos), font, scale, color, 1)
        y_pos += 28

    if symmetry is not None:
        sym_color = (0, 255, 0) if symmetry < 8.0 else (0, 165, 255)
        cv2.putText(vis, f"Symmetry: {symmetry:.1f}%", (x1 + 10, y_pos), font, scale, sym_color, 1)

    return vis
