"""Tests for gait cycle detection and metric computation."""

import numpy as np
import pytest

from src.cv.gait import detect_strides, detect_hoof_contacts, compute_limb_phases
from src.cv.metrics import compute_metrics, _angle_3pt
from src.cv.schema import KEYPOINT_NAME_TO_ID, NUM_KEYPOINTS
from src.cv.smoothing import smooth_trajectory_savgol, _interpolate_gaps


# ---------- Fixtures: synthetic keypoint data ----------

def _make_gallop_data(
    n_frames: int = 120,
    fps: float = 60.0,
    stride_freq_hz: float = 2.0,
    amplitude_px: float = 30.0,
) -> tuple[np.ndarray, np.ndarray]:
    """Generate synthetic keypoint data simulating gallop.

    Creates a withers keypoint with sinusoidal vertical oscillation
    and forward motion, plus hooves with phase-shifted oscillation.
    """
    kpts = np.zeros((n_frames, NUM_KEYPOINTS, 2), dtype=np.float32)
    conf = np.ones((n_frames, NUM_KEYPOINTS), dtype=np.float32) * 0.8

    t = np.arange(n_frames) / fps
    stride_period = 1.0 / stride_freq_hz

    # Withers: moves forward + oscillates vertically
    w_id = KEYPOINT_NAME_TO_ID["withers"]
    kpts[:, w_id, 0] = 200 + t * 500  # forward at ~500 px/s
    kpts[:, w_id, 1] = 300 + amplitude_px * np.sin(2 * np.pi * stride_freq_hz * t)

    # Poll
    poll_id = KEYPOINT_NAME_TO_ID["poll"]
    kpts[:, poll_id, 0] = kpts[:, w_id, 0] - 80
    kpts[:, poll_id, 1] = kpts[:, w_id, 1] - 100

    # Throat
    throat_id = KEYPOINT_NAME_TO_ID["throat"]
    kpts[:, throat_id, 0] = kpts[:, w_id, 0] - 50
    kpts[:, throat_id, 1] = kpts[:, w_id, 1] - 60

    # Croup
    croup_id = KEYPOINT_NAME_TO_ID["croup"]
    kpts[:, croup_id, 0] = kpts[:, w_id, 0] + 200
    kpts[:, croup_id, 1] = kpts[:, w_id, 1] + 10

    # Shoulders
    for side, prefix in [("l", "l_shoulder"), ("r", "r_shoulder")]:
        sid = KEYPOINT_NAME_TO_ID[prefix]
        kpts[:, sid, 0] = kpts[:, w_id, 0] + 20
        kpts[:, sid, 1] = kpts[:, w_id, 1] + 60

    # Hooves: oscillate vertically with phase offset, touching "ground" at y=500
    hoof_names = ["l_fore_hoof", "r_fore_hoof", "l_hind_hoof", "r_hind_hoof"]
    phase_offsets = [0.0, 0.5, 0.25, 0.75]  # phase offsets in fractions of stride

    for hoof_name, phase in zip(hoof_names, phase_offsets):
        h_id = KEYPOINT_NAME_TO_ID[hoof_name]
        phase_rad = 2 * np.pi * stride_freq_hz * t + phase * 2 * np.pi
        # Hoof goes between ground (y=500) and up (y=400)
        kpts[:, h_id, 0] = kpts[:, w_id, 0] + 30
        kpts[:, h_id, 1] = 450 + 50 * np.cos(phase_rad)  # oscillates 400-500

    # Hip and hock for hindlimb
    for side_prefix in ["l", "r"]:
        hip_id = KEYPOINT_NAME_TO_ID[f"{side_prefix}_hip"]
        kpts[:, hip_id, 0] = kpts[:, croup_id, 0] + 20
        kpts[:, hip_id, 1] = kpts[:, croup_id, 1] + 80

        if f"{side_prefix}_hock" in KEYPOINT_NAME_TO_ID:
            hock_id = KEYPOINT_NAME_TO_ID[f"{side_prefix}_hock"]
            kpts[:, hock_id, 0] = kpts[:, hip_id, 0] + 10
            kpts[:, hock_id, 1] = kpts[:, hip_id, 1] + 80

    return kpts, conf


# ---------- Smoothing tests ----------

class TestSmoothing:
    def test_savgol_basic(self):
        t = np.linspace(0, 2 * np.pi, 100)
        trajectory = np.column_stack([t, np.sin(t) + np.random.randn(100) * 0.1])
        smoothed = smooth_trajectory_savgol(trajectory, window_length=11, polyorder=2)
        # Smoothed should be closer to true sine than noisy input
        true_y = np.sin(t)
        noisy_err = np.mean(np.abs(trajectory[:, 1] - true_y))
        smooth_err = np.mean(np.abs(smoothed[:, 1] - true_y))
        assert smooth_err < noisy_err

    def test_savgol_short_trajectory(self):
        short = np.array([[1, 2], [3, 4], [5, 6]], dtype=np.float32)
        result = smooth_trajectory_savgol(short, window_length=7)
        np.testing.assert_array_equal(result, short)

    def test_interpolate_gaps(self):
        traj = np.array([[0, 0], [0, 0], [2, 2], [0, 0], [4, 4]], dtype=np.float32)
        visible = np.array([False, False, True, False, True])
        result = _interpolate_gaps(traj, visible)
        # Frame 3 (between frame 2 and 4) should be interpolated
        assert result[3, 0] == pytest.approx(3.0, abs=0.1)


# ---------- Gait detection tests ----------

class TestGaitDetection:
    def test_detect_strides_synthetic(self):
        kpts, conf = _make_gallop_data(n_frames=120, fps=60.0, stride_freq_hz=2.0)
        gait = detect_strides(kpts, conf, fps=60.0)

        # At 2 Hz stride frequency over 2 seconds, expect ~3-4 strides
        assert gait.stride_count >= 2
        assert gait.mean_stride_frequency > 0
        assert gait.mean_stride_duration_s > 0

    def test_detect_strides_insufficient_data(self):
        """Should handle very short sequences gracefully."""
        kpts = np.zeros((5, NUM_KEYPOINTS, 2), dtype=np.float32)
        conf = np.ones((5, NUM_KEYPOINTS), dtype=np.float32)
        gait = detect_strides(kpts, conf, fps=60.0)
        assert gait.stride_count == 0

    def test_hoof_contacts_synthetic(self):
        kpts, conf = _make_gallop_data(n_frames=120, fps=60.0)
        contacts = detect_hoof_contacts(kpts, conf, fps=60.0)

        assert "l_fore" in contacts
        assert "r_fore" in contacts
        assert "l_hind" in contacts
        assert "r_hind" in contacts

        # Each hoof should have some stance frames
        for limb, stance_mask in contacts.items():
            assert len(stance_mask) == 120
            # With synthetic oscillating data, should have some stance and some swing
            assert stance_mask.sum() > 0, f"{limb} has no stance frames"
            assert (~stance_mask).sum() > 0, f"{limb} has no swing frames"


# ---------- Metric tests ----------

class TestMetrics:
    def test_angle_3pt_right_angle(self):
        a = np.array([1.0, 0.0])
        b = np.array([0.0, 0.0])
        c = np.array([0.0, 1.0])
        angle = _angle_3pt(a, b, c)
        assert angle == pytest.approx(90.0, abs=1.0)

    def test_angle_3pt_straight(self):
        a = np.array([0.0, 0.0])
        b = np.array([1.0, 0.0])
        c = np.array([2.0, 0.0])
        angle = _angle_3pt(a, b, c)
        assert angle == pytest.approx(180.0, abs=1.0)

    def test_compute_metrics_synthetic(self):
        kpts, conf = _make_gallop_data(n_frames=120, fps=60.0, stride_freq_hz=2.0)
        gait = detect_strides(kpts, conf, fps=60.0)
        contacts = detect_hoof_contacts(kpts, conf, fps=60.0)
        phases = compute_limb_phases(contacts, gait.strides, fps=60.0)

        metrics = compute_metrics(kpts, conf, gait, fps=60.0, limb_phases=phases)

        assert metrics.num_strides >= 2
        assert metrics.mean_stride_frequency_hz > 0
        assert metrics.mean_stride_length_px > 0
        assert metrics.mean_speed_px_s > 0
        assert metrics.mean_withers_displacement_px > 0

    def test_compute_metrics_with_calibration(self):
        kpts, conf = _make_gallop_data(n_frames=120, fps=60.0)
        gait = detect_strides(kpts, conf, fps=60.0)

        # 100 px per meter
        metrics = compute_metrics(kpts, conf, gait, fps=60.0, px_per_meter=100.0)

        if metrics.num_strides > 0 and metrics.mean_speed_px_s > 0:
            assert metrics.mean_speed_m_s is not None
            assert metrics.mean_speed_m_s > 0

    def test_metrics_to_dict(self):
        kpts, conf = _make_gallop_data(n_frames=120, fps=60.0)
        gait = detect_strides(kpts, conf, fps=60.0)
        metrics = compute_metrics(kpts, conf, gait, fps=60.0)

        d = metrics.to_dict()
        assert isinstance(d, dict)
        assert "num_strides" in d
        assert "mean_stride_frequency_hz" in d
        assert "mean_speed_px_s" in d


# ---------- Calibration tests ----------

class TestCalibration:
    def test_reference_calibration(self):
        from src.cv.calibration import calibrate_from_reference

        cal = calibrate_from_reference(
            point_a=(100.0, 200.0),
            point_b=(200.0, 200.0),
            known_distance_m=1.07,  # rail height
        )
        assert cal.px_per_meter == pytest.approx(100.0 / 1.07, rel=0.01)
        assert cal.px_to_meters(100.0) == pytest.approx(1.07, rel=0.01)
        assert cal.method == "reference_distance"

    def test_reference_calibration_invalid(self):
        from src.cv.calibration import calibrate_from_reference

        with pytest.raises(ValueError):
            calibrate_from_reference((0, 0), (0, 0), 1.0)
