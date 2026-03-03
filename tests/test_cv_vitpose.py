"""Tests for ViTPose++ keypoint estimation and AP-10K → equine mapping."""

import numpy as np
import pytest

from src.cv.schema import NUM_KEYPOINTS, KEYPOINT_NAMES
from src.cv.vitpose import (
    _map_ap10k_to_equine,
    _DIRECT_MAP,
    VITPOSE_MODELS,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def ap10k_keypoints():
    """Realistic AP-10K keypoints for a horse facing right."""
    kpts = np.array([
        [300, 100],  # 0: left_eye
        [320, 100],  # 1: right_eye
        [310, 120],  # 2: nose
        [250, 130],  # 3: neck
        [100, 140],  # 4: root_of_tail
        [230, 170],  # 5: left_shoulder
        [220, 230],  # 6: left_elbow
        [215, 320],  # 7: left_front_paw
        [240, 165],  # 8: right_shoulder
        [230, 225],  # 9: right_elbow
        [225, 315],  # 10: right_front_paw
        [120, 160],  # 11: left_hip
        [115, 230],  # 12: left_knee
        [110, 320],  # 13: left_back_paw
        [130, 155],  # 14: right_hip
        [125, 225],  # 15: right_knee
        [120, 315],  # 16: right_back_paw
    ], dtype=np.float32)
    scores = np.full(17, 0.9, dtype=np.float32)
    return kpts, scores


# ---------------------------------------------------------------------------
# Mapping tests
# ---------------------------------------------------------------------------

class TestAP10KToEquineMapping:
    """Tests for the AP-10K → 24-keypoint equine mapping."""

    def test_output_shape(self, ap10k_keypoints):
        kpts, scores = ap10k_keypoints
        equine_kpts, equine_conf = _map_ap10k_to_equine(kpts, scores)
        assert equine_kpts.shape == (NUM_KEYPOINTS, 2)
        assert equine_conf.shape == (NUM_KEYPOINTS,)

    def test_all_keypoints_filled(self, ap10k_keypoints):
        """With all 17 AP-10K keypoints visible, all 24 equine slots should be populated."""
        kpts, scores = ap10k_keypoints
        equine_kpts, equine_conf = _map_ap10k_to_equine(kpts, scores)
        assert (equine_conf > 0).all(), (
            f"Missing keypoints: {[KEYPOINT_NAMES[i] for i in range(24) if equine_conf[i] == 0]}"
        )

    def test_direct_mappings_preserve_coordinates(self, ap10k_keypoints):
        """Direct-mapped keypoints should have the exact same coordinates."""
        kpts, scores = ap10k_keypoints
        equine_kpts, equine_conf = _map_ap10k_to_equine(kpts, scores)

        for ap_idx, eq_idx in _DIRECT_MAP.items():
            np.testing.assert_allclose(
                equine_kpts[eq_idx], kpts[ap_idx],
                err_msg=f"Direct mapping AP-10K[{ap_idx}] → equine[{eq_idx}] ({KEYPOINT_NAMES[eq_idx]})"
            )

    def test_direct_mappings_preserve_confidence(self, ap10k_keypoints):
        """Direct-mapped keypoints should keep their original confidence."""
        kpts, scores = ap10k_keypoints
        _, equine_conf = _map_ap10k_to_equine(kpts, scores)

        for ap_idx, eq_idx in _DIRECT_MAP.items():
            assert equine_conf[eq_idx] == scores[ap_idx], (
                f"Confidence mismatch at equine[{eq_idx}] ({KEYPOINT_NAMES[eq_idx]})"
            )

    def test_interpolated_confidence_lower_than_source(self, ap10k_keypoints):
        """Interpolated keypoints should have lower confidence than their sources."""
        kpts, scores = ap10k_keypoints
        _, equine_conf = _map_ap10k_to_equine(kpts, scores)

        interpolated_ids = [0, 2, 4, 5, 9, 10, 14, 15, 19]
        for eq_id in interpolated_ids:
            assert equine_conf[eq_id] < 0.9, (
                f"Interpolated keypoint {KEYPOINT_NAMES[eq_id]} (id={eq_id}) "
                f"should have reduced confidence, got {equine_conf[eq_id]}"
            )

    def test_poll_is_eye_midpoint(self, ap10k_keypoints):
        kpts, scores = ap10k_keypoints
        equine_kpts, _ = _map_ap10k_to_equine(kpts, scores)
        expected = (kpts[0] + kpts[1]) / 2
        np.testing.assert_allclose(equine_kpts[0], expected)

    def test_mid_back_between_withers_and_tail(self, ap10k_keypoints):
        kpts, scores = ap10k_keypoints
        equine_kpts, _ = _map_ap10k_to_equine(kpts, scores)

        withers = equine_kpts[3]  # = AP-10K neck
        tail = equine_kpts[6]    # = AP-10K root_of_tail
        mid_back = equine_kpts[4]

        # mid_back.x should be between withers.x and tail.x
        assert min(withers[0], tail[0]) <= mid_back[0] <= max(withers[0], tail[0])

    def test_croup_closer_to_tail_than_withers(self, ap10k_keypoints):
        kpts, scores = ap10k_keypoints
        equine_kpts, _ = _map_ap10k_to_equine(kpts, scores)

        withers = equine_kpts[3]
        croup = equine_kpts[5]
        tail = equine_kpts[6]

        dist_to_withers = np.linalg.norm(croup - withers)
        dist_to_tail = np.linalg.norm(croup - tail)
        assert dist_to_tail < dist_to_withers, "Croup should be closer to tail than to withers"

    def test_fore_joints_ordered_top_to_bottom(self, ap10k_keypoints):
        """Shoulder → elbow → knee → fetlock → hoof should be ordered by y-coordinate."""
        kpts, scores = ap10k_keypoints
        equine_kpts, _ = _map_ap10k_to_equine(kpts, scores)

        for limb_ids in [[7, 8, 9, 10, 11], [12, 13, 14, 15, 16]]:
            y_values = [equine_kpts[i, 1] for i in limb_ids]
            assert y_values == sorted(y_values), (
                f"Forelimb joints not ordered top-to-bottom: "
                f"{[KEYPOINT_NAMES[i] for i in limb_ids]} y={y_values}"
            )

    def test_hind_joints_ordered_top_to_bottom(self, ap10k_keypoints):
        kpts, scores = ap10k_keypoints
        equine_kpts, _ = _map_ap10k_to_equine(kpts, scores)

        for limb_ids in [[17, 18, 19, 20], [21, 22, 23]]:
            y_values = [equine_kpts[i, 1] for i in limb_ids]
            assert y_values == sorted(y_values), (
                f"Hindlimb joints not ordered top-to-bottom: "
                f"{[KEYPOINT_NAMES[i] for i in limb_ids]} y={y_values}"
            )

    def test_partial_visibility(self):
        """When some AP-10K keypoints are invisible, mapping should gracefully degrade."""
        kpts = np.zeros((17, 2), dtype=np.float32)
        scores = np.zeros(17, dtype=np.float32)

        # Only nose and neck visible
        kpts[2] = [310, 120]
        scores[2] = 0.8
        kpts[3] = [250, 130]
        scores[3] = 0.85

        equine_kpts, equine_conf = _map_ap10k_to_equine(kpts, scores)

        # Nose should be mapped
        assert equine_conf[1] == 0.8
        np.testing.assert_allclose(equine_kpts[1], [310, 120])

        # Withers should be mapped (from neck)
        assert equine_conf[3] == 0.85

        # Poll should be zero (no eyes visible)
        assert equine_conf[0] == 0.0

        # Limbs should be zero (no limb keypoints visible)
        for i in range(7, 24):
            assert equine_conf[i] == 0.0

    def test_single_eye_fallback(self):
        """If only one eye is visible, poll should still be estimated."""
        kpts = np.zeros((17, 2), dtype=np.float32)
        scores = np.zeros(17, dtype=np.float32)

        kpts[0] = [300, 100]  # Only left eye
        scores[0] = 0.9

        equine_kpts, equine_conf = _map_ap10k_to_equine(kpts, scores)

        assert equine_conf[0] > 0, "Poll should be estimated from single eye"
        np.testing.assert_allclose(equine_kpts[0], [300, 100])


# ---------------------------------------------------------------------------
# Model registry tests
# ---------------------------------------------------------------------------

class TestViTPoseModels:

    def test_model_sizes(self):
        assert set(VITPOSE_MODELS.keys()) == {"small", "base", "large", "huge"}

    def test_model_ids_are_huggingface_format(self):
        for size, model_id in VITPOSE_MODELS.items():
            assert "/" in model_id, f"Model ID for '{size}' should be org/model format"
            assert model_id.startswith("usyd-community/vitpose-plus-")
