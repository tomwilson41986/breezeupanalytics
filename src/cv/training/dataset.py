"""Dataset format tools for equine keypoint training.

Handles conversion between annotation formats:
- COCO Keypoint JSON -> YOLO-Pose TXT
- Roboflow export -> YOLO-Pose TXT
- Frame extraction from video for annotation

YOLO-Pose label format (one line per object):
  class_id cx cy w h kp0_x kp0_y kp0_v kp1_x kp1_y kp1_v ... kpN_x kpN_y kpN_v

All coordinates are normalized to [0, 1] relative to image dimensions.
Visibility: 0=not labeled, 1=labeled but occluded, 2=labeled and visible.
"""

from __future__ import annotations

import json
import logging
import shutil
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

from src.cv.schema import NUM_KEYPOINTS, KEYPOINT_NAMES

logger = logging.getLogger(__name__)


@dataclass
class KeypointAnnotation:
    """A single keypoint annotation for one horse in one image."""
    image_path: str
    image_width: int
    image_height: int
    bbox: tuple[float, float, float, float]  # x1, y1, x2, y2 in pixels
    keypoints: list[tuple[float, float, int]]  # [(x, y, visibility), ...] for each kp
    category_id: int = 0  # 0 = horse


@dataclass
class AnnotationDataset:
    """A collection of keypoint annotations across images."""
    annotations: list[KeypointAnnotation] = field(default_factory=list)
    image_dir: str = ""
    num_keypoints: int = NUM_KEYPOINTS
    keypoint_names: list[str] = field(default_factory=lambda: list(KEYPOINT_NAMES))


def coco_to_yolo_pose(
    coco_json_path: str | Path,
    output_dir: str | Path,
    image_dir: str | Path | None = None,
    copy_images: bool = True,
) -> Path:
    """Convert COCO Keypoint format annotations to YOLO-Pose format.

    COCO format has a single JSON with all annotations.
    YOLO-Pose format has one .txt file per image, plus images organized in
    images/ and labels/ directories.

    Args:
        coco_json_path: Path to COCO keypoint annotation JSON.
        output_dir: Output directory for YOLO-Pose dataset.
        image_dir: Directory containing the images. If None, uses the
                   directory paths from the COCO JSON.
        copy_images: Whether to copy images to the output directory.

    Returns:
        Path to the output directory.
    """
    coco_path = Path(coco_json_path)
    out = Path(output_dir)

    with open(coco_path) as f:
        coco = json.load(f)

    # Build lookup maps
    images = {img["id"]: img for img in coco["images"]}
    categories = {cat["id"]: cat for cat in coco.get("categories", [])}

    # Group annotations by image
    anns_by_image: dict[int, list[dict]] = {}
    for ann in coco["annotations"]:
        img_id = ann["image_id"]
        anns_by_image.setdefault(img_id, []).append(ann)

    # Create output structure
    img_out = out / "images"
    lbl_out = out / "labels"
    img_out.mkdir(parents=True, exist_ok=True)
    lbl_out.mkdir(parents=True, exist_ok=True)

    converted = 0

    for img_id, img_info in images.items():
        filename = img_info["file_name"]
        w = img_info["width"]
        h = img_info["height"]

        # Copy image
        if copy_images and image_dir:
            src = Path(image_dir) / filename
            dst = img_out / Path(filename).name
            if src.exists() and not dst.exists():
                shutil.copy2(src, dst)

        # Convert annotations to YOLO-Pose format
        img_anns = anns_by_image.get(img_id, [])
        lines = []

        for ann in img_anns:
            # Bounding box: COCO uses [x, y, width, height], YOLO uses center
            bx, by, bw, bh = ann["bbox"]
            cx = (bx + bw / 2) / w
            cy = (by + bh / 2) / h
            nw = bw / w
            nh = bh / h

            # Keypoints: COCO stores as flat [x1, y1, v1, x2, y2, v2, ...]
            kpts_flat = ann.get("keypoints", [])
            num_kpts = ann.get("num_keypoints", len(kpts_flat) // 3)

            kpt_values = []
            for k in range(NUM_KEYPOINTS):
                idx = k * 3
                if idx + 2 < len(kpts_flat):
                    kx = kpts_flat[idx] / w      # normalize
                    ky = kpts_flat[idx + 1] / h
                    kv = kpts_flat[idx + 2]       # visibility
                else:
                    kx, ky, kv = 0.0, 0.0, 0

                kpt_values.extend([kx, ky, int(kv)])

            # Format: class cx cy w h kp0_x kp0_y kp0_v ...
            parts = [0, cx, cy, nw, nh] + kpt_values
            line = " ".join(f"{v:.6f}" if isinstance(v, float) else str(v) for v in parts)
            lines.append(line)

        # Write label file
        stem = Path(filename).stem
        label_path = lbl_out / f"{stem}.txt"
        with open(label_path, "w") as f:
            f.write("\n".join(lines))

        converted += 1

    logger.info("Converted %d images from COCO to YOLO-Pose format in %s", converted, out)
    return out


def extract_frames_for_labeling(
    video_path: str | Path,
    output_dir: str | Path,
    num_frames: int = 50,
    strategy: str = "uniform",
) -> list[Path]:
    """Extract frames from a video for manual annotation.

    Strategies:
    - "uniform": Evenly spaced across the video.
    - "random": Random selection.
    - "motion": Frames with highest inter-frame difference (most motion).

    Args:
        video_path: Path to the source video.
        output_dir: Directory to save extracted frames.
        num_frames: Number of frames to extract.
        strategy: Selection strategy.

    Returns:
        List of paths to extracted frame images.
    """
    video_path = Path(video_path)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {video_path}")

    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    num_frames = min(num_frames, total)

    if strategy == "uniform":
        indices = np.linspace(0, total - 1, num_frames, dtype=int)
    elif strategy == "random":
        rng = np.random.default_rng(42)
        indices = np.sort(rng.choice(total, size=num_frames, replace=False))
    elif strategy == "motion":
        indices = _select_high_motion_frames(cap, total, num_frames)
        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
    else:
        raise ValueError(f"Unknown strategy: {strategy}")

    saved = []
    stem = video_path.stem

    for idx in indices:
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(idx))
        ret, frame = cap.read()
        if not ret:
            continue

        fname = f"{stem}_frame{int(idx):06d}.jpg"
        path = out / fname
        cv2.imwrite(str(path), frame)
        saved.append(path)

    cap.release()
    logger.info("Extracted %d frames from %s (%s strategy)", len(saved), video_path.name, strategy)
    return saved


def _select_high_motion_frames(
    cap: cv2.VideoCapture,
    total: int,
    num_frames: int,
) -> np.ndarray:
    """Select frames with the highest inter-frame motion (pixel difference)."""
    # Sample a subset for efficiency
    sample_step = max(1, total // 500)
    diffs = []
    prev_gray = None

    for i in range(0, total, sample_step):
        cap.set(cv2.CAP_PROP_POS_FRAMES, i)
        ret, frame = cap.read()
        if not ret:
            break

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        if prev_gray is not None:
            diff = np.mean(np.abs(gray.astype(float) - prev_gray.astype(float)))
            diffs.append((i, diff))

        prev_gray = gray

    # Sort by motion, take top N
    diffs.sort(key=lambda x: x[1], reverse=True)
    selected = sorted([d[0] for d in diffs[:num_frames]])
    return np.array(selected, dtype=int)


def create_empty_labels(
    image_dir: str | Path,
    labels_dir: str | Path,
) -> int:
    """Create empty label files for all images in a directory.

    Useful as a starting point before annotation — pre-creates the
    label files so annotators only need to add detections.

    Returns:
        Number of label files created.
    """
    image_dir = Path(image_dir)
    labels_dir = Path(labels_dir)
    labels_dir.mkdir(parents=True, exist_ok=True)

    count = 0
    for ext in ("*.jpg", "*.jpeg", "*.png", "*.bmp"):
        for img_path in image_dir.glob(ext):
            label_path = labels_dir / f"{img_path.stem}.txt"
            if not label_path.exists():
                label_path.touch()
                count += 1

    return count


def validate_yolo_dataset(dataset_dir: str | Path) -> dict:
    """Validate a YOLO-Pose dataset directory structure and labels.

    Checks:
    - images/ and labels/ directories exist
    - Each image has a corresponding label file
    - Label format is valid
    - Keypoint counts are consistent

    Returns:
        Validation report dict with counts and any issues found.
    """
    dataset_dir = Path(dataset_dir)
    images_dir = dataset_dir / "images"
    labels_dir = dataset_dir / "labels"

    report = {
        "valid": True,
        "num_images": 0,
        "num_labels": 0,
        "num_annotations": 0,
        "missing_labels": [],
        "missing_images": [],
        "format_errors": [],
        "keypoint_counts": {},
    }

    if not images_dir.exists():
        report["valid"] = False
        report["format_errors"].append("images/ directory not found")
        return report

    if not labels_dir.exists():
        report["valid"] = False
        report["format_errors"].append("labels/ directory not found")
        return report

    # Check images
    image_stems = set()
    for ext in ("*.jpg", "*.jpeg", "*.png", "*.bmp"):
        for img in images_dir.glob(ext):
            image_stems.add(img.stem)
    report["num_images"] = len(image_stems)

    # Check labels
    label_stems = set()
    for lbl in labels_dir.glob("*.txt"):
        label_stems.add(lbl.stem)

        # Validate label content
        with open(lbl) as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue

                parts = line.split()
                report["num_annotations"] += 1

                # Minimum: class + 4 bbox values = 5
                if len(parts) < 5:
                    report["format_errors"].append(f"{lbl.name}:{line_num}: too few values ({len(parts)})")
                    continue

                # Expected: 5 (bbox) + num_kpts * 3 (x, y, v)
                kpt_values = len(parts) - 5
                num_kpts = kpt_values // 3
                report["keypoint_counts"][num_kpts] = report["keypoint_counts"].get(num_kpts, 0) + 1

    report["num_labels"] = len(label_stems)

    # Cross-check
    report["missing_labels"] = sorted(image_stems - label_stems)
    report["missing_images"] = sorted(label_stems - image_stems)

    if report["format_errors"] or report["missing_labels"]:
        report["valid"] = False

    return report


def split_dataset(
    dataset_dir: str | Path,
    output_dir: str | Path,
    train_ratio: float = 0.8,
    val_ratio: float = 0.15,
    test_ratio: float = 0.05,
    seed: int = 42,
) -> dict[str, int]:
    """Split a YOLO-Pose dataset into train/val/test sets.

    Creates the standard YOLO directory structure:
      output_dir/
        train/images/ train/labels/
        val/images/   val/labels/
        test/images/  test/labels/

    Args:
        dataset_dir: Source dataset with images/ and labels/.
        output_dir: Output directory for the split dataset.
        train_ratio: Fraction for training.
        val_ratio: Fraction for validation.
        test_ratio: Fraction for testing.
        seed: Random seed for reproducibility.

    Returns:
        Dict with counts per split.
    """
    dataset_dir = Path(dataset_dir)
    output_dir = Path(output_dir)

    images_dir = dataset_dir / "images"
    labels_dir = dataset_dir / "labels"

    # Collect all image stems that have labels
    stems = []
    for ext in ("*.jpg", "*.jpeg", "*.png", "*.bmp"):
        for img in images_dir.glob(ext):
            if (labels_dir / f"{img.stem}.txt").exists():
                stems.append((img.stem, img.suffix))

    rng = np.random.default_rng(seed)
    rng.shuffle(stems)

    n = len(stems)
    n_train = int(n * train_ratio)
    n_val = int(n * val_ratio)

    splits = {
        "train": stems[:n_train],
        "val": stems[n_train:n_train + n_val],
        "test": stems[n_train + n_val:],
    }

    counts = {}
    for split_name, split_stems in splits.items():
        split_img = output_dir / split_name / "images"
        split_lbl = output_dir / split_name / "labels"
        split_img.mkdir(parents=True, exist_ok=True)
        split_lbl.mkdir(parents=True, exist_ok=True)

        for stem, ext in split_stems:
            src_img = images_dir / f"{stem}{ext}"
            src_lbl = labels_dir / f"{stem}.txt"

            if src_img.exists():
                shutil.copy2(src_img, split_img / f"{stem}{ext}")
            if src_lbl.exists():
                shutil.copy2(src_lbl, split_lbl / f"{stem}.txt")

        counts[split_name] = len(split_stems)

    logger.info("Dataset split: %s", counts)
    return counts
