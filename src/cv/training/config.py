"""Training configuration for fine-tuning YOLO-Pose on equine keypoints.

Generates YAML config files required by Ultralytics YOLO training:
- Dataset YAML (paths, class names, keypoint schema)
- Augmentation parameters tuned for gallop footage
"""

from __future__ import annotations

import logging
from pathlib import Path

import yaml

from src.cv.schema import (
    FLIP_INDICES,
    KEYPOINT_NAMES,
    NUM_KEYPOINTS,
    SKELETON_EDGES,
)

logger = logging.getLogger(__name__)


def generate_dataset_yaml(
    dataset_dir: str | Path,
    output_path: str | Path | None = None,
    train_subdir: str = "train",
    val_subdir: str = "val",
    test_subdir: str | None = "test",
) -> Path:
    """Generate the dataset YAML config for YOLO-Pose training.

    This YAML tells Ultralytics where to find images/labels and
    defines the keypoint schema (names, skeleton, flip indices).

    Args:
        dataset_dir: Root directory of the split dataset.
        output_path: Where to write the YAML. Defaults to dataset_dir/equine.yaml.
        train_subdir: Training set subdirectory name.
        val_subdir: Validation set subdirectory name.
        test_subdir: Test set subdirectory name (optional).

    Returns:
        Path to the generated YAML file.
    """
    dataset_dir = Path(dataset_dir)
    if output_path is None:
        output_path = dataset_dir / "equine.yaml"
    output_path = Path(output_path)

    config = {
        "path": str(dataset_dir.resolve()),
        "train": f"{train_subdir}/images",
        "val": f"{val_subdir}/images",
    }

    if test_subdir:
        config["test"] = f"{test_subdir}/images"

    # Single class: horse
    config["names"] = {0: "horse"}

    # Keypoint schema
    config["kpt_shape"] = [NUM_KEYPOINTS, 3]  # 24 keypoints, (x, y, visibility)

    # Flip indices for horizontal augmentation
    config["flip_idx"] = FLIP_INDICES

    # Skeleton connectivity for visualization
    config["skeleton"] = [list(edge) for edge in SKELETON_EDGES]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False)

    logger.info("Generated dataset YAML at %s", output_path)
    return output_path


def get_training_hyperparams(
    preset: str = "finetune",
) -> dict:
    """Return training hyperparameters tuned for equine gallop footage.

    Presets:
    - "finetune": Fine-tuning from pretrained YOLO-Pose weights.
      Moderate augmentation, lower learning rate.
    - "scratch": Training from scratch. Full augmentation, higher LR.
    - "active_learning": Quick fine-tuning on newly labeled data.
      Minimal epochs, light augmentation.

    Args:
        preset: One of "finetune", "scratch", "active_learning".

    Returns:
        Dict of training hyperparameters for Ultralytics YOLO.
    """
    base = {
        # Image size
        "imgsz": 640,

        # Augmentation — tuned for equine gallop scenarios
        "hsv_h": 0.015,         # hue jitter (horses have uniform coat colors)
        "hsv_s": 0.5,           # saturation (varied lighting at tracks)
        "hsv_v": 0.4,           # value/brightness
        "degrees": 5.0,         # rotation (camera tilt, max ±5°)
        "translate": 0.1,       # translation
        "scale": 0.3,           # scale (0.7x to 1.3x — horses at varying distances)
        "shear": 2.0,           # shear
        "perspective": 0.0005,  # perspective distortion
        "flipud": 0.0,          # no vertical flip (horses don't gallop upside down)
        "fliplr": 0.5,          # horizontal flip (left-to-right vs right-to-left)
        "mosaic": 0.5,          # mosaic augmentation (reduced — context matters)
        "mixup": 0.1,           # mixup augmentation

        # Motion blur — critical for gallop footage
        "erasing": 0.1,         # random erasing (simulates partial occlusion)
    }

    if preset == "finetune":
        return {
            **base,
            "epochs": 100,
            "batch": 16,
            "lr0": 0.001,           # lower initial LR for fine-tuning
            "lrf": 0.01,            # final LR factor
            "warmup_epochs": 3,
            "warmup_momentum": 0.8,
            "weight_decay": 0.0005,
            "patience": 20,         # early stopping patience
            "pose": 12.0,           # keypoint loss weight (high — our primary task)
            "box": 7.5,             # box loss weight
            "cls": 0.5,             # classification loss weight (low — single class)
            "freeze": 10,           # freeze first 10 layers (backbone)
        }
    elif preset == "scratch":
        return {
            **base,
            "epochs": 300,
            "batch": 16,
            "lr0": 0.01,
            "lrf": 0.01,
            "warmup_epochs": 5,
            "warmup_momentum": 0.8,
            "weight_decay": 0.0005,
            "patience": 50,
            "pose": 12.0,
            "box": 7.5,
            "cls": 0.5,
            "mosaic": 1.0,          # full mosaic for training from scratch
            "mixup": 0.2,
        }
    elif preset == "active_learning":
        return {
            **base,
            "epochs": 30,
            "batch": 8,
            "lr0": 0.0005,          # very low LR for incremental fine-tuning
            "lrf": 0.1,
            "warmup_epochs": 1,
            "warmup_momentum": 0.8,
            "weight_decay": 0.0005,
            "patience": 10,
            "pose": 12.0,
            "box": 7.5,
            "cls": 0.5,
            "freeze": 15,           # freeze more layers for small data updates
            "mosaic": 0.3,
            "mixup": 0.0,
        }
    else:
        raise ValueError(f"Unknown preset: {preset}. Use 'finetune', 'scratch', or 'active_learning'.")


def generate_model_yaml(
    output_path: str | Path,
    base_model: str = "yolo11n-pose",
) -> Path:
    """Generate a YOLO-Pose model config YAML for 24 equine keypoints.

    Modifies the base YOLO-Pose architecture to output 24 keypoints
    instead of the default 17 (COCO human pose).

    Args:
        output_path: Where to write the model YAML.
        base_model: Base model architecture (e.g., "yolo11n-pose", "yolo11m-pose").

    Returns:
        Path to the generated YAML file.
    """
    output_path = Path(output_path)

    # Model config that tells YOLO to use 24 keypoints
    config = {
        "nc": 1,                                    # number of classes (horse only)
        "kpt_shape": [NUM_KEYPOINTS, 3],            # 24 keypoints, (x, y, visibility)
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False)

    logger.info("Generated model YAML at %s (base: %s, %d keypoints)", output_path, base_model, NUM_KEYPOINTS)
    return output_path
