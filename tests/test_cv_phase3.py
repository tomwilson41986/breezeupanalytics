"""Tests for Phase 3 gait analysis enhancements.

Covers suspension phase detection, overreach measurement, speed profile,
acceleration, joint angles (topline, fetlock, hock), movement quality
composite score, per-stride detail export, and horse comparison.
"""

import numpy as np
import pytest

from src.cv.gait import (
    GaitAnalysis,
    StrideCycle,
    SuspensionPhase,
    OverreachEvent,
    detect_hoof_contacts,
    detect_overreach,
    detect_strides,
    detect_suspension_phases,
    compute_limb_phases,
    _find_stance_onsets,
    _find_stride_for_frame,
)
from src.cv.metrics import (
    HorseMetrics,
    MovementQuality,
    SpeedProfile,
    StrideMetrics,
    _compute_fetlock_extension,
    _compute_hock_flexion,
    _compute_movement_quality,
    _compute_speed_profile,
    _compute_topline_angle,
    compare_horses,
    compute_metrics,
)
from src.cv.schema import KEYPOINT_NAME_TO_ID, NUM_KEYPOINTS


# ---------- Fixtures ----------

def _make_gallop_data(
    n_frames: int = 120,
    fps: float = 60.0,
    stride_freq_hz: float = 2.0,
    amplitude_px: float = 30.0,
) -> tuple[np.ndarray, np.ndarray]:
    """Generate synthetic keypoint data simulating gallop with all limbs."""
    kpts = np.zeros((n_frames, NUM_KEYPOINTS, 2), dtype=np.float32)
    conf = np.ones((n_frames, NUM_KEYPOINTS), dtype=np.float32) * 0.8

    t = np.arange(n_frames) / fps
    w_id = KEYPOINT_NAME_TO_ID["withers"]
    kpts[:, w_id, 0] = 200 + t * 500
    kpts[:, w_id, 1] = 300 + amplitude_px * np.sin(2 * np.pi * stride_freq_hz * t)

    # Poll
    poll_id = KEYPOINT_NAME_TO_ID["poll"]
    kpts[:, poll_id, 0] = kpts[:, w_id, 0] - 80
    kpts[:, poll_id, 1] = kpts[:, w_id, 1] - 100

    # Throat
    throat_id = KEYPOINT_NAME_TO_ID["throat"]
    kpts[:, throat_id, 0] = kpts[:, w_id, 0] - 50
    kpts[:, throat_id, 1] = kpts[:, w_id, 1] - 60

    # Mid-back
    mid_back_id = KEYPOINT_NAME_TO_ID["mid_back"]
    kpts[:, mid_back_id, 0] = kpts[:, w_id, 0] + 100
    kpts[:, mid_back_id, 1] = kpts[:, w_id, 1] + 5

    # Croup
    croup_id = KEYPOINT_NAME_TO_ID["croup"]
    kpts[:, croup_id, 0] = kpts[:, w_id, 0] + 200
    kpts[:, croup_id, 1] = kpts[:, w_id, 1] + 10

    # Shoulders
    for prefix in ["l_shoulder", "r_shoulder"]:
        sid = KEYPOINT_NAME_TO_ID[prefix]
        kpts[:, sid, 0] = kpts[:, w_id, 0] + 20
        kpts[:, sid, 1] = kpts[:, w_id, 1] + 60

    # Elbows
    for prefix in ["l_elbow", "r_elbow"]:
        eid = KEYPOINT_NAME_TO_ID[prefix]
        kpts[:, eid, 0] = kpts[:, w_id, 0] + 25
        kpts[:, eid, 1] = kpts[:, w_id, 1] + 120

    # Knees
    for prefix in ["l_knee_fore", "r_knee_fore"]:
        kid = KEYPOINT_NAME_TO_ID[prefix]
        kpts[:, kid, 0] = kpts[:, w_id, 0] + 28
        kpts[:, kid, 1] = kpts[:, w_id, 1] + 180

    # Fetlocks
    for prefix in ["l_fetlock_fore", "r_fetlock_fore"]:
        fid = KEYPOINT_NAME_TO_ID[prefix]
        kpts[:, fid, 0] = kpts[:, w_id, 0] + 30
        kpts[:, fid, 1] = kpts[:, w_id, 1] + 220 + 10 * np.sin(2 * np.pi * stride_freq_hz * t)

    # Hooves with phase offsets
    hoof_names = ["l_fore_hoof", "r_fore_hoof", "l_hind_hoof", "r_hind_hoof"]
    phase_offsets = [0.0, 0.5, 0.25, 0.75]
    for hoof_name, phase in zip(hoof_names, phase_offsets):
        h_id = KEYPOINT_NAME_TO_ID[hoof_name]
        phase_rad = 2 * np.pi * stride_freq_hz * t + phase * 2 * np.pi
        kpts[:, h_id, 0] = kpts[:, w_id, 0] + 30
        kpts[:, h_id, 1] = 450 + 50 * np.cos(phase_rad)

    # Hips
    for prefix in ["l_hip", "r_hip"]:
        hip_id = KEYPOINT_NAME_TO_ID[prefix]
        kpts[:, hip_id, 0] = kpts[:, croup_id, 0] + 20
        kpts[:, hip_id, 1] = kpts[:, croup_id, 1] + 80

    # Hocks
    for prefix in ["l_hock", "r_hock"]:
        hock_id = KEYPOINT_NAME_TO_ID[prefix]
        kpts[:, hock_id, 0] = kpts[:, croup_id, 0] + 25
        kpts[:, hock_id, 1] = kpts[:, croup_id, 1] + 160

    # Hind fetlock
    hf_id = KEYPOINT_NAME_TO_ID["l_hind_fetlock"]
    kpts[:, hf_id, 0] = kpts[:, croup_id, 0] + 28
    kpts[:, hf_id, 1] = kpts[:, croup_id, 1] + 200

    return kpts, conf


def _make_strides(n: int = 3, fps: float = 60.0) -> list[StrideCycle]:
    """Create synthetic stride cycles."""
    strides = []
    stride_frames = 30  # 0.5s at 60fps
    for i in range(n):
        start = i * stride_frames
        end = (i + 1) * stride_frames
        strides.append(StrideCycle(
            start_frame=start,
            end_frame=end,
            duration_frames=stride_frames,
            duration_s=stride_frames / fps,
            frequency_hz=fps / stride_frames,
        ))
    return strides


# ---------- Suspension phase tests ----------

class TestSuspensionPhase:
    def test_detect_suspension_basic(self):
        """Suspension phases should be detected when all hooves are off ground."""
        T = 90
        contacts = {
            "l_fore": np.ones(T, dtype=bool),
            "r_fore": np.ones(T, dtype=bool),
            "l_hind": np.ones(T, dtype=bool),
            "r_hind": np.ones(T, dtype=bool),
        }
        # Create an aerial window at frames 30-34
        for limb in contacts:
            contacts[limb][30:35] = False

        strides = _make_strides(n=3)
        phases = detect_suspension_phases(contacts, strides, fps=60.0)

        assert len(phases) == 1
        assert phases[0].start_frame == 30
        assert phases[0].end_frame == 35
        assert phases[0].duration_frames == 5
        assert phases[0].duration_s == pytest.approx(5 / 60.0)
        assert phases[0].stride_index == 1  # frames 30-35 are in stride 1 (30-60)

    def test_detect_suspension_multiple(self):
        """Multiple suspension phases should be detected."""
        T = 90
        contacts = {
            "l_fore": np.ones(T, dtype=bool),
            "r_fore": np.ones(T, dtype=bool),
            "l_hind": np.ones(T, dtype=bool),
            "r_hind": np.ones(T, dtype=bool),
        }
        # Two aerial windows
        for limb in contacts:
            contacts[limb][10:13] = False
            contacts[limb][50:54] = False

        strides = _make_strides(n=3)
        phases = detect_suspension_phases(contacts, strides, fps=60.0)

        assert len(phases) == 2

    def test_no_suspension_when_always_grounded(self):
        """No suspension if at least one hoof is always in stance."""
        T = 60
        contacts = {
            "l_fore": np.ones(T, dtype=bool),
            "r_fore": np.ones(T, dtype=bool),
            "l_hind": np.ones(T, dtype=bool),
            "r_hind": np.ones(T, dtype=bool),
        }
        # Only remove 3 limbs, keep 1 always grounded
        contacts["l_fore"][10:15] = False
        contacts["r_fore"][10:15] = False
        contacts["l_hind"][10:15] = False

        strides = _make_strides(n=2)
        phases = detect_suspension_phases(contacts, strides, fps=60.0)
        assert len(phases) == 0

    def test_suspension_with_synthetic_gallop(self):
        """Integration: detect suspension from full synthetic gallop data."""
        kpts, conf = _make_gallop_data(n_frames=120, fps=60.0)
        contacts = detect_hoof_contacts(kpts, conf, fps=60.0)
        gait = detect_strides(kpts, conf, fps=60.0)
        phases = detect_suspension_phases(contacts, gait.strides, fps=60.0)
        # With sinusoidal hooves, there may or may not be suspension
        # This just tests it doesn't crash
        assert isinstance(phases, list)


# ---------- Overreach tests ----------

class TestOverreach:
    def test_detect_overreach_basic(self):
        """Overreach should be detected at hind hoof stance onsets."""
        T = 90
        kpts = np.zeros((T, NUM_KEYPOINTS, 2), dtype=np.float32)
        conf = np.ones((T, NUM_KEYPOINTS), dtype=np.float32) * 0.8

        # Setup withers moving left to right
        w_id = KEYPOINT_NAME_TO_ID["withers"]
        kpts[:, w_id, 0] = np.linspace(100, 400, T)
        kpts[:, w_id, 1] = 300

        # Left fore hoof at x=200 during stance
        lf_id = KEYPOINT_NAME_TO_ID["l_fore_hoof"]
        kpts[:, lf_id, 0] = 200
        kpts[:, lf_id, 1] = 500

        # Left hind hoof at x=230 (ahead of fore) during stance
        lh_id = KEYPOINT_NAME_TO_ID["l_hind_hoof"]
        kpts[:, lh_id, 0] = 230
        kpts[:, lh_id, 1] = 500

        contacts = {
            "l_fore": np.zeros(T, dtype=bool),
            "r_fore": np.zeros(T, dtype=bool),
            "l_hind": np.zeros(T, dtype=bool),
            "r_hind": np.zeros(T, dtype=bool),
        }
        # Fore stance at frames 10-20, hind stance at frames 25-35
        contacts["l_fore"][10:20] = True
        contacts["l_hind"][25:35] = True

        strides = _make_strides(n=3)
        events = detect_overreach(kpts, conf, contacts, strides)

        assert len(events) >= 1
        # Hind is ahead (x=230 vs x=200), positive overreach
        assert events[0].overreach_px > 0

    def test_detect_overreach_with_calibration(self):
        """Overreach should include meter values when calibrated."""
        T = 90
        kpts = np.zeros((T, NUM_KEYPOINTS, 2), dtype=np.float32)
        conf = np.ones((T, NUM_KEYPOINTS), dtype=np.float32) * 0.8

        w_id = KEYPOINT_NAME_TO_ID["withers"]
        kpts[:, w_id, 0] = np.linspace(100, 400, T)

        lf_id = KEYPOINT_NAME_TO_ID["l_fore_hoof"]
        kpts[:, lf_id, 0] = 200
        kpts[:, lf_id, 1] = 500

        lh_id = KEYPOINT_NAME_TO_ID["l_hind_hoof"]
        kpts[:, lh_id, 0] = 250
        kpts[:, lh_id, 1] = 500

        contacts = {
            "l_fore": np.zeros(T, dtype=bool),
            "r_fore": np.zeros(T, dtype=bool),
            "l_hind": np.zeros(T, dtype=bool),
            "r_hind": np.zeros(T, dtype=bool),
        }
        contacts["l_fore"][10:20] = True
        contacts["l_hind"][25:35] = True

        strides = _make_strides(n=3)
        events = detect_overreach(kpts, conf, contacts, strides, px_per_meter=100.0)

        if events:
            assert events[0].overreach_m is not None
            assert events[0].overreach_m == pytest.approx(events[0].overreach_px / 100.0)


# ---------- Stance onset helper tests ----------

class TestStanceHelpers:
    def test_find_stance_onsets(self):
        stance = np.array([False, False, True, True, True, False, False, True, True], dtype=bool)
        onsets = _find_stance_onsets(stance)
        np.testing.assert_array_equal(onsets, [2, 7])

    def test_find_stance_onsets_empty(self):
        stance = np.array([True, True, True], dtype=bool)
        onsets = _find_stance_onsets(stance)
        assert len(onsets) == 0  # no transitions, already in stance

    def test_find_stride_for_frame(self):
        strides = _make_strides(n=3)
        assert _find_stride_for_frame(15, strides) == 0
        assert _find_stride_for_frame(45, strides) == 1
        assert _find_stride_for_frame(75, strides) == 2
        assert _find_stride_for_frame(100, strides) is None


# ---------- Topline angle tests ----------

class TestToplineAngle:
    def test_flat_topline(self):
        """A flat topline (withers, mid_back, croup in a line) should give ~180 deg."""
        kpts = np.zeros((10, NUM_KEYPOINTS, 2), dtype=np.float32)
        conf = np.ones((10, NUM_KEYPOINTS), dtype=np.float32) * 0.8

        w_id = KEYPOINT_NAME_TO_ID["withers"]
        m_id = KEYPOINT_NAME_TO_ID["mid_back"]
        c_id = KEYPOINT_NAME_TO_ID["croup"]

        for t in range(10):
            kpts[t, w_id] = [100, 300]
            kpts[t, m_id] = [200, 300]  # same y = straight line
            kpts[t, c_id] = [300, 300]

        angle = _compute_topline_angle(kpts, conf)
        assert angle is not None
        assert angle == pytest.approx(180.0, abs=1.0)

    def test_curved_topline(self):
        """A curved topline should give angle < 180."""
        kpts = np.zeros((10, NUM_KEYPOINTS, 2), dtype=np.float32)
        conf = np.ones((10, NUM_KEYPOINTS), dtype=np.float32) * 0.8

        w_id = KEYPOINT_NAME_TO_ID["withers"]
        m_id = KEYPOINT_NAME_TO_ID["mid_back"]
        c_id = KEYPOINT_NAME_TO_ID["croup"]

        for t in range(10):
            kpts[t, w_id] = [100, 300]
            kpts[t, m_id] = [200, 330]  # drops below → angle < 180
            kpts[t, c_id] = [300, 300]

        angle = _compute_topline_angle(kpts, conf)
        assert angle is not None
        assert angle < 180.0


# ---------- Fetlock extension tests ----------

class TestFetlockExtension:
    def test_fetlock_extension_computed(self):
        """Fetlock extension angle should be computed when keypoints are available."""
        kpts = np.zeros((10, NUM_KEYPOINTS, 2), dtype=np.float32)
        conf = np.ones((10, NUM_KEYPOINTS), dtype=np.float32) * 0.8

        knee_id = KEYPOINT_NAME_TO_ID["l_knee_fore"]
        fetlock_id = KEYPOINT_NAME_TO_ID["l_fetlock_fore"]
        hoof_id = KEYPOINT_NAME_TO_ID["l_fore_hoof"]

        for t in range(10):
            kpts[t, knee_id] = [200, 300]
            kpts[t, fetlock_id] = [200, 400]
            kpts[t, hoof_id] = [200, 450]

        angle = _compute_fetlock_extension(kpts, conf)
        assert angle is not None
        assert 0 < angle < 200

    def test_fetlock_extension_low_confidence(self):
        """Should return None when confidence is too low."""
        kpts = np.zeros((5, NUM_KEYPOINTS, 2), dtype=np.float32)
        conf = np.ones((5, NUM_KEYPOINTS), dtype=np.float32) * 0.1  # all low

        angle = _compute_fetlock_extension(kpts, conf)
        assert angle is None


# ---------- Hock flexion tests ----------

class TestHockFlexion:
    def test_hock_flexion_computed(self):
        """Hock flexion angle should be computed when keypoints are available."""
        kpts = np.zeros((10, NUM_KEYPOINTS, 2), dtype=np.float32)
        conf = np.ones((10, NUM_KEYPOINTS), dtype=np.float32) * 0.8

        hip_id = KEYPOINT_NAME_TO_ID["l_hip"]
        hock_id = KEYPOINT_NAME_TO_ID["l_hock"]
        hoof_id = KEYPOINT_NAME_TO_ID["l_hind_hoof"]

        for t in range(10):
            kpts[t, hip_id] = [200, 200]
            kpts[t, hock_id] = [200, 300]
            kpts[t, hoof_id] = [200, 400]

        angle = _compute_hock_flexion(kpts, conf)
        assert angle is not None
        # Straight leg = 180
        assert angle == pytest.approx(180.0, abs=1.0)

    def test_hock_flexion_bent(self):
        """Flexed hock should give angle < 180."""
        kpts = np.zeros((10, NUM_KEYPOINTS, 2), dtype=np.float32)
        conf = np.ones((10, NUM_KEYPOINTS), dtype=np.float32) * 0.8

        hip_id = KEYPOINT_NAME_TO_ID["l_hip"]
        hock_id = KEYPOINT_NAME_TO_ID["l_hock"]
        hoof_id = KEYPOINT_NAME_TO_ID["l_hind_hoof"]

        for t in range(10):
            kpts[t, hip_id] = [200, 200]
            kpts[t, hock_id] = [200, 300]
            kpts[t, hoof_id] = [250, 400]  # offset = bent

        angle = _compute_hock_flexion(kpts, conf)
        assert angle is not None
        assert angle < 180.0


# ---------- Speed profile tests ----------

class TestSpeedProfile:
    def test_speed_profile_basic(self):
        """Speed profile should track speeds across strides."""
        stride_metrics = [
            StrideMetrics(stride_index=0, estimated_speed_px_s=100.0, stride_duration_s=0.5),
            StrideMetrics(stride_index=1, estimated_speed_px_s=120.0, stride_duration_s=0.5),
            StrideMetrics(stride_index=2, estimated_speed_px_s=115.0, stride_duration_s=0.5),
        ]

        profile = _compute_speed_profile(stride_metrics)

        assert profile.speeds_px_s == [100.0, 120.0, 115.0]
        assert profile.peak_speed_px_s == 120.0
        assert len(profile.accelerations_px_s2) == 2
        # Acceleration from stride 0->1: (120-100)/0.5 = 40
        assert profile.accelerations_px_s2[0] == pytest.approx(40.0)
        # Deceleration from stride 1->2: (115-120)/0.5 = -10
        assert profile.accelerations_px_s2[1] == pytest.approx(-10.0)

    def test_speed_profile_with_calibration(self):
        stride_metrics = [
            StrideMetrics(stride_index=0, estimated_speed_px_s=100.0, stride_duration_s=0.5),
        ]
        profile = _compute_speed_profile(stride_metrics, px_per_meter=50.0)
        assert profile.speeds_m_s == [2.0]
        assert profile.peak_speed_m_s == 2.0

    def test_speed_profile_single_stride(self):
        stride_metrics = [
            StrideMetrics(stride_index=0, estimated_speed_px_s=100.0, stride_duration_s=0.5),
        ]
        profile = _compute_speed_profile(stride_metrics)
        assert len(profile.accelerations_px_s2) == 0
        assert profile.mean_acceleration_px_s2 == 0.0


# ---------- Movement quality tests ----------

class TestMovementQuality:
    def test_movement_quality_perfect(self):
        """A horse with excellent metrics should score high."""
        metrics = HorseMetrics(
            stride_length_cv=0.02,              # very regular
            mean_lateral_symmetry=2.0,           # very symmetric
            mean_overreach_px=60.0,              # good reach
            suspension_ratio=0.12,               # good suspension
            mean_hindlimb_engagement_deg=50.0,   # well engaged
        )
        mq = _compute_movement_quality(metrics)
        assert mq.overall_score > 70
        assert mq.stride_regularity > 80
        assert mq.symmetry_score > 80

    def test_movement_quality_poor(self):
        """A horse with poor metrics should score low."""
        metrics = HorseMetrics(
            stride_length_cv=0.35,
            mean_lateral_symmetry=35.0,
            mean_overreach_px=-10.0,
            suspension_ratio=0.0,
            mean_hindlimb_engagement_deg=130.0,
        )
        mq = _compute_movement_quality(metrics)
        assert mq.overall_score < 30

    def test_movement_quality_neutral_defaults(self):
        """Missing data should give neutral (mid-range) scores."""
        metrics = HorseMetrics()
        mq = _compute_movement_quality(metrics)
        assert 0 <= mq.overall_score <= 100
        assert mq.symmetry_score == 50.0  # default when no data

    def test_movement_quality_components(self):
        """All component keys should be present."""
        metrics = HorseMetrics(stride_length_cv=0.1)
        mq = _compute_movement_quality(metrics)
        assert "stride_regularity" in mq.components
        assert "symmetry" in mq.components
        assert "reach" in mq.components
        assert "suspension" in mq.components
        assert "engagement" in mq.components


# ---------- Horse comparison tests ----------

class TestHorseComparison:
    def test_compare_two_horses(self):
        """Comparison should rank horses per metric."""
        h1 = HorseMetrics(
            track_id=1, num_strides=5,
            mean_stride_length_px=250.0, mean_stride_frequency_hz=2.0,
            mean_speed_px_s=500.0, stride_length_cv=0.05,
        )
        h1.movement_quality = MovementQuality(overall_score=75.0)

        h2 = HorseMetrics(
            track_id=2, num_strides=5,
            mean_stride_length_px=280.0, mean_stride_frequency_hz=2.1,
            mean_speed_px_s=550.0, stride_length_cv=0.10,
        )
        h2.movement_quality = MovementQuality(overall_score=68.0)

        result = compare_horses([h1, h2])

        assert result["num_horses"] == 2
        assert len(result["horses"]) == 2

        # Horse 2 has higher speed, should be ranked #1 for speed
        speed_ranking = result["rankings"]["mean_speed_px_s"]
        assert speed_ranking[0]["horse_index"] == 1  # h2 index
        assert speed_ranking[0]["rank"] == 1

        # Horse 1 has lower CV (better), should be ranked #1 for regularity
        cv_ranking = result["rankings"]["stride_length_cv"]
        assert cv_ranking[0]["horse_index"] == 0  # h1 index

    def test_compare_needs_two(self):
        """Should return error with fewer than 2 horses."""
        result = compare_horses([HorseMetrics()])
        assert "error" in result

    def test_compare_three_horses(self):
        """Should handle 3+ horses."""
        horses = [
            HorseMetrics(track_id=i, mean_speed_px_s=100 + i * 50)
            for i in range(3)
        ]
        for h in horses:
            h.movement_quality = MovementQuality(overall_score=50 + h.track_id * 10)

        result = compare_horses(horses)
        assert result["num_horses"] == 3
        assert "movement_quality" in result["rankings"]


# ---------- Per-stride detail export tests ----------

class TestDetailExport:
    def test_to_detail_dict_has_per_stride(self):
        """Detail export should include per_stride array."""
        metrics = HorseMetrics(
            track_id=1,
            num_strides=2,
            per_stride=[
                StrideMetrics(stride_index=0, stride_length_px=200.0, stride_duration_s=0.5,
                              stride_frequency_hz=2.0, estimated_speed_px_s=400.0),
                StrideMetrics(stride_index=1, stride_length_px=220.0, stride_duration_s=0.48,
                              stride_frequency_hz=2.08, estimated_speed_px_s=458.3),
            ],
        )
        metrics.speed_profile = SpeedProfile(
            speeds_px_s=[400.0, 458.3],
            accelerations_px_s2=[116.6],
            peak_speed_px_s=458.3,
            mean_acceleration_px_s2=116.6,
        )
        metrics.movement_quality = MovementQuality(
            overall_score=72.5,
            stride_regularity=85.0,
            symmetry_score=70.0,
            reach_score=60.0,
            suspension_score=40.0,
            engagement_score=80.0,
        )

        d = metrics.to_detail_dict()

        assert "per_stride" in d
        assert len(d["per_stride"]) == 2
        assert d["per_stride"][0]["stride_length_px"] == 200.0
        assert d["per_stride"][1]["estimated_speed_px_s"] == 458.3

        assert "speed_profile" in d
        assert d["speed_profile"]["peak_speed_px_s"] == 458.3

        assert "movement_quality" in d
        assert d["movement_quality"]["overall_score"] == 72.5

    def test_to_detail_dict_optional_fields(self):
        """Optional fields should only appear if present."""
        sm = StrideMetrics(stride_index=0, estimated_speed_px_s=100.0)
        metrics = HorseMetrics(num_strides=1, per_stride=[sm])
        d = metrics.to_detail_dict()

        stride_d = d["per_stride"][0]
        assert "stride_length_m" not in stride_d
        assert "topline_angle_deg" not in stride_d

    def test_to_dict_includes_phase3_fields(self):
        """The summary to_dict should include phase 3 fields when set."""
        metrics = HorseMetrics(
            mean_topline_angle_deg=175.0,
            mean_fetlock_extension_deg=140.0,
            mean_hock_flexion_deg=155.0,
            mean_suspension_duration_s=0.05,
            suspension_ratio=0.10,
            mean_overreach_px=25.0,
            speed_efficiency_index=250.0,
        )
        metrics.speed_profile = SpeedProfile(mean_acceleration_px_s2=15.0)
        metrics.movement_quality = MovementQuality(overall_score=65.0)

        d = metrics.to_dict()
        assert d["mean_topline_angle_deg"] == 175.0
        assert d["mean_fetlock_extension_deg"] == 140.0
        assert d["mean_hock_flexion_deg"] == 155.0
        assert d["mean_suspension_duration_s"] == 0.05
        assert d["suspension_ratio"] == 0.1
        assert d["mean_overreach_px"] == 25.0
        assert d["speed_efficiency_index"] == 250.0
        assert d["mean_acceleration_px_s2"] == 15.0
        assert d["movement_quality_score"] == 65.0


# ---------- Full integration test ----------

class TestPhase3Integration:
    def test_full_metrics_with_phase3(self):
        """Full pipeline: synthetic data -> all Phase 3 metrics computed."""
        kpts, conf = _make_gallop_data(n_frames=120, fps=60.0, stride_freq_hz=2.0)
        gait = detect_strides(kpts, conf, fps=60.0)
        contacts = detect_hoof_contacts(kpts, conf, fps=60.0)
        limb_phases = compute_limb_phases(contacts, gait.strides, fps=60.0)

        # Suspension and overreach
        gait.suspension_phases = detect_suspension_phases(contacts, gait.strides, fps=60.0)
        gait.overreach_events = detect_overreach(kpts, conf, contacts, gait.strides)

        metrics = compute_metrics(
            kpts, conf, gait, fps=60.0, limb_phases=limb_phases,
        )

        assert metrics.num_strides >= 2
        assert metrics.speed_profile is not None
        assert len(metrics.speed_profile.speeds_px_s) == metrics.num_strides
        assert metrics.movement_quality is not None
        assert 0 <= metrics.movement_quality.overall_score <= 100
        assert metrics.speed_efficiency_index is not None

        # New angle metrics should be computed (we set all keypoints)
        assert metrics.mean_topline_angle_deg is not None
        assert metrics.mean_fetlock_extension_deg is not None
        assert metrics.mean_hock_flexion_deg is not None

        # Detail export should work
        detail = metrics.to_detail_dict()
        assert len(detail["per_stride"]) == metrics.num_strides
        assert "speed_profile" in detail
        assert "movement_quality" in detail
