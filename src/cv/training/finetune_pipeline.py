"""End-to-end pipeline: auto-label with anatomy agent -> split -> fine-tune -> evaluate.

Usage:
    from src.cv.training.finetune_pipeline import run_finetune_pipeline

    result = run_finetune_pipeline(
        video_paths=["output/hip654/hip654_raw.mp4"],
        output_dir="runs/equine-v1",
        num_frames_per_video=100,
    )
    print(f"Model: {result.model_path}, Pose mAP50: {result.pose_map50:.3f}")

Or from CLI:
    python -m src.cv.training.finetune_pipeline \\
        output/hip654/hip654_raw.mp4 \\
        -o runs/equine-v1 \\
        --frames 100 --preset finetune
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path

from src.cv.schema import NUM_KEYPOINTS

logger = logging.getLogger(__name__)


@dataclass
class FinetuneResult:
    """Result of the full auto-label → finetune pipeline."""
    # Labeling
    total_frames_extracted: int = 0
    total_frames_labeled: int = 0
    total_horses_labeled: int = 0
    mean_quality: float = 0.0
    mean_anatomy_score: float = 0.0

    # Dataset
    train_images: int = 0
    val_images: int = 0
    test_images: int = 0
    dataset_dir: str = ""

    # Training
    model_path: str = ""
    epochs_completed: int = 0
    box_map50: float = 0.0
    pose_map50: float = 0.0
    pose_map50_95: float = 0.0
    training_time_s: float = 0.0

    # Evaluation
    eval_metrics: dict = field(default_factory=dict)

    # Pipeline
    total_time_s: float = 0.0


def run_finetune_pipeline(
    video_paths: list[str | Path],
    output_dir: str | Path = "runs/equine-finetune",
    num_frames_per_video: int = 100,
    frame_strategy: str = "uniform",
    source: str = "ensemble",
    vitpose_size: str = "base",
    base_model: str = "yolo11n-pose.pt",
    preset: str = "finetune",
    train_split: float = 0.75,
    val_split: float = 0.15,
    correction_strength: float = 0.7,
    skip_training: bool = False,
    **train_overrides,
) -> FinetuneResult:
    """Run the full auto-label → split → fine-tune → evaluate pipeline.

    Args:
        video_paths: List of video file paths to extract training data from.
        output_dir: Root output directory for all pipeline artifacts.
        num_frames_per_video: Frames to extract per video.
        frame_strategy: Frame selection strategy ("uniform", "random", "motion").
        source: Model source for auto-labeling ("vitpose", "ensemble", "coco").
        vitpose_size: ViTPose++ model size.
        base_model: Pretrained YOLO-Pose model to fine-tune from.
        preset: Training hyperparameter preset.
        train_split: Fraction for training set.
        val_split: Fraction for validation set.
        correction_strength: Anatomy correction strength (0-1).
        skip_training: If True, only do labeling and dataset prep (useful for QA).
        **train_overrides: Override any training hyperparameter.

    Returns:
        FinetuneResult with paths and metrics.
    """
    from src.cv.training.anatomy_label_agent import AnatomyLabelAgent
    from src.cv.training.dataset import split_dataset, validate_yolo_dataset
    from src.cv.training.config import generate_dataset_yaml

    t_start = time.time()
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    result = FinetuneResult()

    # ---- Phase 1: Auto-label with anatomy agent ----
    logger.info("=" * 60)
    logger.info("PHASE 1: Auto-labeling %d videos with AnatomyLabelAgent", len(video_paths))
    logger.info("=" * 60)

    agent = AnatomyLabelAgent(
        detection_confidence=0.25,
        keypoint_confidence=0.15,
        quality_threshold=0.3,
        min_confident_kpts=6,
        source=source,
        vitpose_size=vitpose_size,
        correction_strength=correction_strength,
    )

    raw_data_dir = output_dir / "raw_labels"
    all_image_dirs = []
    all_label_dirs = []

    for i, video_path in enumerate(video_paths):
        video_path = Path(video_path)
        video_name = video_path.stem
        video_out = raw_data_dir / video_name
        logger.info("Labeling video %d/%d: %s", i + 1, len(video_paths), video_name)

        label_result = agent.label_video(
            video_path,
            output_dir=video_out,
            num_frames=num_frames_per_video,
            strategy=frame_strategy,
        )

        result.total_frames_extracted += label_result.num_images
        result.total_frames_labeled += label_result.num_labeled
        result.total_horses_labeled += label_result.num_horses

        all_image_dirs.append(video_out / "images")
        all_label_dirs.append(video_out / "labels")

        logger.info(
            "  -> %d/%d labeled, quality=%.3f, anatomy=%.3f",
            label_result.num_labeled, label_result.num_images,
            label_result.mean_quality, label_result.mean_anatomy_score,
        )

    # Aggregate quality metrics
    if result.total_frames_labeled > 0:
        result.mean_quality = label_result.mean_quality
        result.mean_anatomy_score = label_result.mean_anatomy_score

    if result.total_frames_labeled == 0:
        logger.error("No frames were labeled. Cannot proceed with training.")
        result.total_time_s = time.time() - t_start
        return result

    # ---- Phase 2: Merge and split dataset ----
    logger.info("=" * 60)
    logger.info("PHASE 2: Merging and splitting dataset")
    logger.info("=" * 60)

    dataset_dir = output_dir / "dataset"
    _merge_label_dirs(all_image_dirs, all_label_dirs, dataset_dir)

    # Split into train/val/test
    split_dir = output_dir / "split"
    split_result = split_dataset(
        str(dataset_dir),
        str(split_dir),
        train_ratio=train_split,
        val_ratio=val_split,
    )

    result.train_images = split_result.get("train", 0)
    result.val_images = split_result.get("val", 0)
    result.test_images = split_result.get("test", 0)
    result.dataset_dir = str(split_dir)

    logger.info(
        "Dataset split: train=%d, val=%d, test=%d",
        result.train_images, result.val_images, result.test_images,
    )

    # Generate dataset YAML
    dataset_yaml = generate_dataset_yaml(split_dir)
    logger.info("Dataset YAML: %s", dataset_yaml)

    # Validate
    validation = validate_yolo_dataset(str(split_dir))
    logger.info("Dataset validation: %s", validation)

    if skip_training:
        logger.info("skip_training=True, stopping after dataset preparation")
        result.total_time_s = time.time() - t_start
        _save_pipeline_report(result, output_dir)
        return result

    # ---- Phase 3: Fine-tune YOLO-Pose ----
    logger.info("=" * 60)
    logger.info("PHASE 3: Fine-tuning YOLO-Pose (%s preset)", preset)
    logger.info("=" * 60)

    from src.cv.training.train import train

    t_train = time.time()
    train_result = train(
        dataset_dir=str(split_dir),
        output_dir=str(output_dir / "training"),
        base_model=base_model,
        preset=preset,
        **train_overrides,
    )
    result.training_time_s = time.time() - t_train

    result.model_path = train_result.model_path
    result.epochs_completed = train_result.epochs_completed
    result.box_map50 = train_result.best_map50
    result.pose_map50 = train_result.best_pose_map50
    result.pose_map50_95 = train_result.best_map50_95

    logger.info(
        "Training complete: %d epochs, Pose mAP50=%.3f, Box mAP50=%.3f",
        result.epochs_completed, result.pose_map50, result.box_map50,
    )

    # ---- Phase 4: Evaluate on test set ----
    if result.test_images > 0 and result.model_path:
        logger.info("=" * 60)
        logger.info("PHASE 4: Evaluating on test set")
        logger.info("=" * 60)

        from src.cv.training.train import evaluate

        result.eval_metrics = evaluate(
            model_path=result.model_path,
            dataset_yaml=str(dataset_yaml),
            split="test",
        )

    result.total_time_s = time.time() - t_start
    _save_pipeline_report(result, output_dir)

    logger.info("=" * 60)
    logger.info("PIPELINE COMPLETE in %.1fs", result.total_time_s)
    logger.info("Model: %s", result.model_path)
    logger.info("=" * 60)

    return result


def _merge_label_dirs(
    image_dirs: list[Path],
    label_dirs: list[Path],
    output_dir: Path,
) -> None:
    """Merge multiple image/label directories into one flat directory."""
    import shutil

    out_images = output_dir / "images"
    out_labels = output_dir / "labels"
    out_images.mkdir(parents=True, exist_ok=True)
    out_labels.mkdir(parents=True, exist_ok=True)

    for img_dir, lbl_dir in zip(image_dirs, label_dirs):
        if not img_dir.exists():
            continue
        for img_file in sorted(img_dir.glob("*")):
            if img_file.suffix.lower() in (".jpg", ".jpeg", ".png", ".bmp"):
                shutil.copy2(img_file, out_images / img_file.name)
                lbl_file = lbl_dir / f"{img_file.stem}.txt"
                if lbl_file.exists():
                    shutil.copy2(lbl_file, out_labels / lbl_file.name)
                else:
                    (out_labels / f"{img_file.stem}.txt").write_text("")


def _save_pipeline_report(result: FinetuneResult, output_dir: Path) -> None:
    """Save a JSON report of the pipeline run."""
    report = {
        "labeling": {
            "frames_extracted": result.total_frames_extracted,
            "frames_labeled": result.total_frames_labeled,
            "horses_labeled": result.total_horses_labeled,
            "mean_quality": round(result.mean_quality, 3),
            "mean_anatomy_score": round(result.mean_anatomy_score, 3),
        },
        "dataset": {
            "train": result.train_images,
            "val": result.val_images,
            "test": result.test_images,
            "dir": result.dataset_dir,
        },
        "training": {
            "model_path": result.model_path,
            "epochs": result.epochs_completed,
            "box_map50": round(result.box_map50, 3),
            "pose_map50": round(result.pose_map50, 3),
            "pose_map50_95": round(result.pose_map50_95, 3),
            "training_time_s": round(result.training_time_s, 1),
        },
        "evaluation": result.eval_metrics,
        "total_time_s": round(result.total_time_s, 1),
    }

    report_path = output_dir / "pipeline_report.json"
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)
    logger.info("Pipeline report: %s", report_path)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    parser = argparse.ArgumentParser(
        description="End-to-end: auto-label videos with anatomy agent -> fine-tune YOLO-Pose"
    )
    parser.add_argument("videos", nargs="+", help="Video file paths")
    parser.add_argument("-o", "--output", default="runs/equine-finetune", help="Output dir")
    parser.add_argument("--frames", type=int, default=100, help="Frames per video")
    parser.add_argument("--strategy", default="uniform", help="Frame strategy")
    parser.add_argument("--source", default="ensemble", help="Model source")
    parser.add_argument("--preset", default="finetune", help="Training preset")
    parser.add_argument("--base-model", default="yolo11n-pose.pt", help="Base model")
    parser.add_argument("--skip-training", action="store_true", help="Only label + prepare dataset")
    parser.add_argument("--epochs", type=int, help="Override epochs")
    parser.add_argument("--batch", type=int, help="Override batch size")

    args = parser.parse_args()

    overrides = {}
    if args.epochs:
        overrides["epochs"] = args.epochs
    if args.batch:
        overrides["batch"] = args.batch

    result = run_finetune_pipeline(
        video_paths=args.videos,
        output_dir=args.output,
        num_frames_per_video=args.frames,
        frame_strategy=args.strategy,
        source=args.source,
        preset=args.preset,
        base_model=args.base_model,
        skip_training=args.skip_training,
        **overrides,
    )

    print(f"\nPipeline complete in {result.total_time_s:.0f}s")
    print(f"  Labeled: {result.total_frames_labeled}/{result.total_frames_extracted} frames")
    print(f"  Dataset: train={result.train_images}, val={result.val_images}, test={result.test_images}")
    if result.model_path:
        print(f"  Model: {result.model_path}")
        print(f"  Pose mAP50: {result.pose_map50:.3f}")
