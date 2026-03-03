"""Tests for the equine keypoint schema definition."""

import pytest

from src.cv.schema import (
    EQUINE_KEYPOINTS,
    FLIP_INDICES,
    KEYPOINT_NAME_TO_ID,
    KEYPOINT_NAMES,
    NUM_KEYPOINTS,
    SKELETON_EDGES,
    EquineKeypointSchema,
)


def test_keypoint_count():
    assert NUM_KEYPOINTS == 24
    assert len(EQUINE_KEYPOINTS) == 24


def test_keypoint_ids_sequential():
    """Keypoint IDs should be 0..23 in order."""
    for i, kp in enumerate(EQUINE_KEYPOINTS):
        assert kp.id == i, f"Keypoint {kp.name} has ID {kp.id}, expected {i}"


def test_keypoint_names_unique():
    assert len(KEYPOINT_NAMES) == len(set(KEYPOINT_NAMES))


def test_name_to_id_mapping():
    for kp in EQUINE_KEYPOINTS:
        assert KEYPOINT_NAME_TO_ID[kp.name] == kp.id


def test_flip_indices_length():
    """Flip indices array must have exactly NUM_KEYPOINTS entries."""
    assert len(FLIP_INDICES) == NUM_KEYPOINTS


def test_flip_indices_range():
    """All flip indices should reference valid keypoint IDs."""
    for i, flip_id in enumerate(FLIP_INDICES):
        assert 0 <= flip_id < NUM_KEYPOINTS, (
            f"Flip index {i} -> {flip_id} is out of range [0, {NUM_KEYPOINTS})"
        )


def test_flip_indices_topline_self_mapped():
    """Topline keypoints (0-6) should map to themselves (symmetric)."""
    for i in range(7):
        assert FLIP_INDICES[i] == i, f"Topline keypoint {i} should map to itself"


def test_flip_indices_lr_swap():
    """Left forelimb should swap with right forelimb."""
    # L shoulder (7) <-> R shoulder (12)
    assert FLIP_INDICES[7] == 12
    assert FLIP_INDICES[12] == 7


def test_flip_indices_hind_hoof_swap():
    """L hind hoof (20) should swap with R hind hoof (23)."""
    assert FLIP_INDICES[20] == 23
    assert FLIP_INDICES[23] == 20


def test_flip_indices_hind_hip_swap():
    """L hip (17) should swap with R hip (21)."""
    assert FLIP_INDICES[17] == 21
    assert FLIP_INDICES[21] == 17


def test_flip_indices_hind_hock_swap():
    """L hock (18) should swap with R hock (22)."""
    assert FLIP_INDICES[18] == 22
    assert FLIP_INDICES[22] == 18


def test_flip_indices_hind_fetlock_self_mapped():
    """L hind fetlock (19) has no R counterpart and should self-map."""
    assert FLIP_INDICES[19] == 19


def test_skeleton_edges_valid():
    """All skeleton edge endpoints should reference valid keypoint IDs."""
    for a, b in SKELETON_EDGES:
        assert 0 <= a < NUM_KEYPOINTS, f"Edge start {a} out of range"
        assert 0 <= b < NUM_KEYPOINTS, f"Edge end {b} out of range"


def test_skeleton_edges_no_self_loops():
    for a, b in SKELETON_EDGES:
        assert a != b, f"Self-loop edge ({a}, {b})"


def test_limb_groups_cover_all_keypoints():
    """Every keypoint should belong to at least one limb group."""
    all_ids = set()
    for ids in EquineKeypointSchema.limb_groups.values():
        all_ids.update(ids)
    for kp in EQUINE_KEYPOINTS:
        assert kp.id in all_ids, f"Keypoint {kp.name} ({kp.id}) not in any limb group"


def test_keypoint_color_returns_bgr():
    for i in range(NUM_KEYPOINTS):
        color = EquineKeypointSchema.keypoint_color(i)
        assert len(color) == 3
        assert all(0 <= c <= 255 for c in color)
