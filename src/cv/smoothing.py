"""Temporal smoothing for keypoint trajectories.

Applies Savitzky-Golay filtering and Kalman filtering to reduce jitter
in keypoint detections across video frames.
"""

from __future__ import annotations

import numpy as np
from scipy.signal import savgol_filter


def smooth_trajectory_savgol(
    trajectory: np.ndarray,
    window_length: int = 7,
    polyorder: int = 2,
) -> np.ndarray:
    """Smooth a keypoint trajectory using Savitzky-Golay filter.

    Args:
        trajectory: (T, 2) array of x,y positions across T frames.
        window_length: Filter window size (must be odd). Larger = smoother.
        polyorder: Polynomial order for the filter.

    Returns:
        Smoothed (T, 2) trajectory.
    """
    if len(trajectory) < window_length:
        return trajectory.copy()

    if window_length % 2 == 0:
        window_length += 1

    smoothed = np.empty_like(trajectory)
    for dim in range(trajectory.shape[1]):
        smoothed[:, dim] = savgol_filter(trajectory[:, dim], window_length, polyorder)
    return smoothed


def smooth_all_keypoints(
    keypoints_seq: np.ndarray,
    confidence_seq: np.ndarray,
    window_length: int = 7,
    polyorder: int = 2,
    min_confidence: float = 0.3,
) -> np.ndarray:
    """Smooth all keypoint trajectories for a single horse across frames.

    Only smooths keypoints that are visible (above confidence threshold)
    in a sufficient number of frames. Missing keypoints are interpolated
    before smoothing.

    Args:
        keypoints_seq: (T, K, 2) array — T frames, K keypoints, x/y.
        confidence_seq: (T, K) array — per-frame per-keypoint confidence.
        window_length: Savitzky-Golay window size.
        polyorder: Polynomial order.
        min_confidence: Minimum confidence to consider a keypoint visible.

    Returns:
        Smoothed (T, K, 2) keypoint array.
    """
    T, K, _ = keypoints_seq.shape
    smoothed = keypoints_seq.copy()

    for k in range(K):
        visible = confidence_seq[:, k] >= min_confidence
        n_visible = visible.sum()

        if n_visible < window_length:
            continue

        traj = keypoints_seq[:, k, :]  # (T, 2)

        # Interpolate missing frames
        interp_traj = _interpolate_gaps(traj, visible)

        # Apply Savitzky-Golay smoothing
        interp_traj = smooth_trajectory_savgol(interp_traj, window_length, polyorder)

        smoothed[:, k, :] = interp_traj

    return smoothed


def _interpolate_gaps(trajectory: np.ndarray, visible: np.ndarray) -> np.ndarray:
    """Linearly interpolate keypoint positions in gaps where confidence is low.

    Args:
        trajectory: (T, 2) x,y positions.
        visible: (T,) boolean mask of which frames have valid keypoints.

    Returns:
        (T, 2) trajectory with gaps filled by linear interpolation.
    """
    result = trajectory.copy()
    indices = np.arange(len(trajectory))

    for dim in range(2):
        if visible.sum() >= 2:
            result[:, dim] = np.interp(
                indices,
                indices[visible],
                trajectory[visible, dim],
            )

    return result


def median_filter_keypoints(
    keypoints_seq: np.ndarray,
    kernel_size: int = 3,
) -> np.ndarray:
    """Apply temporal median filtering to keypoint trajectories.

    A simple but effective approach for removing single-frame outliers.

    Args:
        keypoints_seq: (T, K, 2) keypoint array.
        kernel_size: Median filter window size.

    Returns:
        Filtered (T, K, 2) keypoint array.
    """
    from scipy.ndimage import median_filter as _mf

    T, K, _ = keypoints_seq.shape
    result = np.empty_like(keypoints_seq)

    for k in range(K):
        for dim in range(2):
            result[:, k, dim] = _mf(keypoints_seq[:, k, dim], size=kernel_size)

    return result
