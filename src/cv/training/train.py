"""Training script for fine-tuning YOLO-Pose on equine keypoints.

Supports:
- Fine-tuning from pretrained YOLO-Pose weights
- Training with custom hyperparameters
- Automatic evaluation and model selection
- ONNX export for production deployment
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from src.cv.schema import NUM_KEYPOINTS
from src.cv.training.config import generate_dataset_yaml, get_training_hyperparams

logger = logging.getLogger(__name__)


@dataclass
class TrainingResult:
    """Result of a training run."""
    model_path: str = ""           # path to best weights
    last_model_path: str = ""      # path to last epoch weights
    metrics: dict = field(default_factory=dict)
    epochs_completed: int = 0
    best_epoch: int = 0
    best_map50: float = 0.0
    best_map50_95: float = 0.0
    best_pose_map50: float = 0.0


def train(
    dataset_dir: str | Path,
    output_dir: str | Path = "runs/equine-pose",
    base_model: str = "yolo11n-pose.pt",
    preset: str = "finetune",
    resume: bool = False,
    **override_params,
) -> TrainingResult:
    """Fine-tune YOLO-Pose on the equine keypoint dataset.

    Args:
        dataset_dir: Path to the dataset directory (with train/val/test splits).
        output_dir: Directory for training outputs (weights, logs, plots).
        base_model: Pretrained model to fine-tune from.
        preset: Hyperparameter preset ("finetune", "scratch", "active_learning").
        resume: Resume from a previous training run.
        **override_params: Override any hyperparameter from the preset.

    Returns:
        TrainingResult with paths to trained model and evaluation metrics.
    """
    from ultralytics import YOLO

    dataset_dir = Path(dataset_dir)
    output_dir = Path(output_dir)

    # Generate dataset YAML if not present
    dataset_yaml = dataset_dir / "equine.yaml"
    if not dataset_yaml.exists():
        dataset_yaml = generate_dataset_yaml(dataset_dir)

    # Get hyperparameters
    params = get_training_hyperparams(preset)
    params.update(override_params)

    logger.info("Starting training with preset '%s'", preset)
    logger.info("Base model: %s", base_model)
    logger.info("Dataset: %s", dataset_yaml)
    logger.info("Output: %s", output_dir)

    # Load model
    model = YOLO(base_model)

    # Extract YOLO-specific training args
    epochs = params.pop("epochs", 100)
    batch = params.pop("batch", 16)
    imgsz = params.pop("imgsz", 640)
    patience = params.pop("patience", 20)
    freeze = params.pop("freeze", None)

    # Train
    train_kwargs = {
        "data": str(dataset_yaml),
        "epochs": epochs,
        "batch": batch,
        "imgsz": imgsz,
        "patience": patience,
        "project": str(output_dir.parent),
        "name": output_dir.name,
        "exist_ok": True,
        "verbose": True,
        "save": True,
        "plots": True,
        "resume": resume,
    }

    if freeze is not None:
        train_kwargs["freeze"] = freeze

    # Pass augmentation params
    aug_keys = [
        "hsv_h", "hsv_s", "hsv_v", "degrees", "translate", "scale",
        "shear", "perspective", "flipud", "fliplr", "mosaic", "mixup",
        "erasing",
    ]
    for key in aug_keys:
        if key in params:
            train_kwargs[key] = params[key]

    # Pass loss weights
    for key in ["pose", "box", "cls"]:
        if key in params:
            train_kwargs[key] = params[key]

    # Pass LR params
    for key in ["lr0", "lrf", "warmup_epochs", "warmup_momentum", "weight_decay"]:
        if key in params:
            train_kwargs[key] = params[key]

    results = model.train(**train_kwargs)

    # Build training result
    best_path = output_dir / "weights" / "best.pt"
    last_path = output_dir / "weights" / "last.pt"

    result = TrainingResult(
        model_path=str(best_path) if best_path.exists() else "",
        last_model_path=str(last_path) if last_path.exists() else "",
    )

    # Extract metrics from results
    if results and hasattr(results, "results_dict"):
        rd = results.results_dict
        result.metrics = dict(rd)
        result.best_map50 = rd.get("metrics/mAP50(B)", 0.0)
        result.best_map50_95 = rd.get("metrics/mAP50-95(B)", 0.0)
        result.best_pose_map50 = rd.get("metrics/mAP50(P)", 0.0)

    logger.info("Training complete. Best model: %s", result.model_path)
    logger.info("Box mAP50: %.3f, Pose mAP50: %.3f", result.best_map50, result.best_pose_map50)

    return result


def evaluate(
    model_path: str | Path,
    dataset_yaml: str | Path,
    split: str = "val",
    imgsz: int = 640,
) -> dict:
    """Evaluate a trained model on a dataset split.

    Args:
        model_path: Path to the trained model weights (.pt).
        dataset_yaml: Path to the dataset YAML config.
        split: Dataset split to evaluate on ("val" or "test").
        imgsz: Image size for evaluation.

    Returns:
        Dict of evaluation metrics.
    """
    from ultralytics import YOLO

    model = YOLO(str(model_path))
    results = model.val(
        data=str(dataset_yaml),
        split=split,
        imgsz=imgsz,
        verbose=True,
    )

    metrics = {}
    if results and hasattr(results, "results_dict"):
        metrics = dict(results.results_dict)

    logger.info("Evaluation on '%s' split complete", split)
    return metrics


def export_model(
    model_path: str | Path,
    format: str = "onnx",
    imgsz: int = 640,
    simplify: bool = True,
    dynamic: bool = False,
) -> Path:
    """Export a trained model for production deployment.

    Supported formats: onnx, torchscript, openvino, tflite, coreml.

    Args:
        model_path: Path to the trained model weights (.pt).
        format: Export format.
        imgsz: Image size for the exported model.
        simplify: Simplify ONNX graph (onnx format only).
        dynamic: Use dynamic input shapes (onnx format only).

    Returns:
        Path to the exported model file.
    """
    from ultralytics import YOLO

    model = YOLO(str(model_path))
    export_path = model.export(
        format=format,
        imgsz=imgsz,
        simplify=simplify,
        dynamic=dynamic,
    )

    logger.info("Exported model to %s format: %s", format, export_path)
    return Path(export_path)
