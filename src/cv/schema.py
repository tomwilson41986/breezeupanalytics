"""24-keypoint equine skeleton schema for gallop gait analysis.

Defines keypoint names, IDs, skeleton connectivity, and YOLO-Pose flip indices.
Compatible with YOLO-Pose, DeepLabCut, and COCO keypoint annotation formats.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Keypoint:
    id: int
    name: str
    description: str


# ---------- 24-keypoint equine schema ----------

EQUINE_KEYPOINTS: list[Keypoint] = [
    # Head / topline
    Keypoint(0, "poll", "Top of head between ears"),
    Keypoint(1, "nose", "Tip of muzzle"),
    Keypoint(2, "throat", "Throatlatch junction"),
    Keypoint(3, "withers", "Highest point of shoulder"),
    Keypoint(4, "mid_back", "Midpoint of thoracolumbar spine"),
    Keypoint(5, "croup", "Highest point of hindquarters (tuber sacrale)"),
    Keypoint(6, "tail_base", "Dock / base of tail"),
    # Left forelimb
    Keypoint(7, "l_shoulder", "Left scapulohumeral joint"),
    Keypoint(8, "l_elbow", "Left elbow"),
    Keypoint(9, "l_knee_fore", "Left carpus (knee)"),
    Keypoint(10, "l_fetlock_fore", "Left fore fetlock"),
    Keypoint(11, "l_fore_hoof", "Left fore hoof"),
    # Right forelimb
    Keypoint(12, "r_shoulder", "Right scapulohumeral joint"),
    Keypoint(13, "r_elbow", "Right elbow"),
    Keypoint(14, "r_knee_fore", "Right carpus (knee)"),
    Keypoint(15, "r_fetlock_fore", "Right fore fetlock"),
    Keypoint(16, "r_fore_hoof", "Right fore hoof"),
    # Left hindlimb
    Keypoint(17, "l_hip", "Left stifle joint"),
    Keypoint(18, "l_hock", "Left hock (tarsus)"),
    Keypoint(19, "l_hind_fetlock", "Left hind fetlock"),
    Keypoint(20, "l_hind_hoof", "Left hind hoof"),
    # Right hindlimb
    Keypoint(21, "r_hip", "Right stifle joint"),
    Keypoint(22, "r_hock", "Right hock"),
    Keypoint(23, "r_hind_hoof", "Right hind hoof"),
]

NUM_KEYPOINTS = len(EQUINE_KEYPOINTS)

KEYPOINT_NAMES: list[str] = [kp.name for kp in EQUINE_KEYPOINTS]

KEYPOINT_NAME_TO_ID: dict[str, int] = {kp.name: kp.id for kp in EQUINE_KEYPOINTS}

# Skeleton edges for drawing — each tuple is (keypoint_id_a, keypoint_id_b).
SKELETON_EDGES: list[tuple[int, int]] = [
    # Topline
    (0, 2), (2, 3), (3, 4), (4, 5), (5, 6),
    # Head
    (0, 1),
    # Left forelimb
    (3, 7), (7, 8), (8, 9), (9, 10), (10, 11),
    # Right forelimb
    (3, 12), (12, 13), (13, 14), (14, 15), (15, 16),
    # Left hindlimb
    (5, 17), (17, 18), (18, 19), (19, 20),
    # Right hindlimb
    (5, 21), (21, 22), (22, 23),
]

# YOLO-Pose horizontal flip indices: maps keypoint[i] -> keypoint[flip[i]].
# Symmetric keypoints (topline) map to themselves; L/R pairs swap.
FLIP_INDICES: list[int] = [
    0, 1, 2, 3, 4, 5, 6,          # topline: self-mapped
    12, 13, 14, 15, 16,            # L fore -> R fore
    7, 8, 9, 10, 11,               # R fore -> L fore
    21, 22, 23,                    # L hind -> R hind (17->21, 18->22, 19->23)
    20,                            # L hind hoof (20) -> itself (no R hind fetlock pair)
    17, 18, 19,                    # R hind -> L hind (21->17, 22->18, 23->19)
]

# Colors for visualization (BGR for OpenCV).
KEYPOINT_COLORS: dict[str, tuple[int, int, int]] = {
    "topline": (0, 255, 255),       # yellow
    "head": (255, 200, 0),          # cyan
    "l_fore": (255, 0, 0),          # blue
    "r_fore": (0, 0, 255),          # red
    "l_hind": (255, 128, 0),        # orange-blue
    "r_hind": (0, 128, 255),        # orange-red
}

LIMB_GROUPS: dict[str, list[int]] = {
    "topline": [0, 2, 3, 4, 5, 6],
    "head": [0, 1],
    "l_fore": [7, 8, 9, 10, 11],
    "r_fore": [12, 13, 14, 15, 16],
    "l_hind": [17, 18, 19, 20],
    "r_hind": [21, 22, 23],
}


class EquineKeypointSchema:
    """Utility wrapper around the keypoint schema constants."""

    keypoints = EQUINE_KEYPOINTS
    num_keypoints = NUM_KEYPOINTS
    names = KEYPOINT_NAMES
    name_to_id = KEYPOINT_NAME_TO_ID
    skeleton = SKELETON_EDGES
    flip_indices = FLIP_INDICES
    limb_groups = LIMB_GROUPS

    @classmethod
    def keypoint_color(cls, kp_id: int) -> tuple[int, int, int]:
        """Return BGR color for a keypoint based on its limb group."""
        for group, ids in cls.limb_groups.items():
            if kp_id in ids:
                return KEYPOINT_COLORS.get(group, (200, 200, 200))
        return (200, 200, 200)
