"""CLI for training and dataset management.

Usage:
    python -m src.cv.training.cli prepare <video_paths...> --output <dir> [options]
    python -m src.cv.training.cli convert <coco_json> --output <dir>
    python -m src.cv.training.cli split <dataset_dir> --output <dir>
    python -m src.cv.training.cli train <dataset_dir> [options]
    python -m src.cv.training.cli evaluate <model_path> <dataset_yaml>
    python -m src.cv.training.cli export <model_path> [--format onnx]
    python -m src.cv.training.cli active-learn <video> <model> --output <dir>
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path


def setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def cmd_prepare(args: argparse.Namespace) -> int:
    """Extract frames from videos for annotation."""
    from src.cv.training.dataset import extract_frames_for_labeling, create_empty_labels

    output_dir = Path(args.output)
    images_dir = output_dir / "images"
    labels_dir = output_dir / "labels"

    all_paths = []
    for video in args.videos:
        paths = extract_frames_for_labeling(
            video,
            output_dir=images_dir,
            num_frames=args.num_frames,
            strategy=args.strategy,
        )
        all_paths.extend(paths)

    n_labels = create_empty_labels(images_dir, labels_dir)

    print(f"Extracted {len(all_paths)} frames to {images_dir}")
    print(f"Created {n_labels} empty label files in {labels_dir}")
    print(f"\nNext steps:")
    print(f"  1. Open images in Roboflow or DLC labeling tool")
    print(f"  2. Annotate 24 equine keypoints per horse")
    print(f"  3. Export in COCO Keypoint JSON format")
    print(f"  4. Run: python -m src.cv.training.cli convert <coco.json> --output {output_dir}")
    return 0


def cmd_convert(args: argparse.Namespace) -> int:
    """Convert COCO annotations to YOLO-Pose format."""
    from src.cv.training.dataset import coco_to_yolo_pose

    out = coco_to_yolo_pose(
        args.coco_json,
        output_dir=args.output,
        image_dir=args.image_dir,
        copy_images=not args.no_copy,
    )
    print(f"Converted to YOLO-Pose format in {out}")
    return 0


def cmd_split(args: argparse.Namespace) -> int:
    """Split dataset into train/val/test."""
    from src.cv.training.dataset import split_dataset

    counts = split_dataset(
        args.dataset_dir,
        output_dir=args.output,
        train_ratio=args.train_ratio,
        val_ratio=args.val_ratio,
        test_ratio=1.0 - args.train_ratio - args.val_ratio,
        seed=args.seed,
    )
    print(f"Dataset split: {counts}")
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    """Validate a YOLO-Pose dataset."""
    from src.cv.training.dataset import validate_yolo_dataset

    report = validate_yolo_dataset(args.dataset_dir)
    print(f"Dataset: {args.dataset_dir}")
    print(f"Valid: {report['valid']}")
    print(f"Images: {report['num_images']}")
    print(f"Labels: {report['num_labels']}")
    print(f"Annotations: {report['num_annotations']}")
    print(f"Keypoint counts: {report['keypoint_counts']}")

    if report["missing_labels"]:
        print(f"\nMissing labels ({len(report['missing_labels'])}):")
        for s in report["missing_labels"][:10]:
            print(f"  {s}")

    if report["format_errors"]:
        print(f"\nFormat errors ({len(report['format_errors'])}):")
        for e in report["format_errors"][:10]:
            print(f"  {e}")

    return 0 if report["valid"] else 1


def cmd_train(args: argparse.Namespace) -> int:
    """Train YOLO-Pose on equine dataset."""
    from src.cv.training.train import train

    result = train(
        dataset_dir=args.dataset_dir,
        output_dir=args.output or "runs/equine-pose",
        base_model=args.model,
        preset=args.preset,
        resume=args.resume,
    )

    print(f"\nTraining complete!")
    print(f"Best model: {result.model_path}")
    print(f"Box mAP50: {result.best_map50:.3f}")
    print(f"Pose mAP50: {result.best_pose_map50:.3f}")
    return 0


def cmd_evaluate(args: argparse.Namespace) -> int:
    """Evaluate a trained model."""
    from src.cv.training.train import evaluate

    metrics = evaluate(
        model_path=args.model,
        dataset_yaml=args.dataset_yaml,
        split=args.split,
    )

    print(f"\nEvaluation results ({args.split} split):")
    for k, v in sorted(metrics.items()):
        if isinstance(v, float):
            print(f"  {k}: {v:.4f}")
        else:
            print(f"  {k}: {v}")
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    """Export model for production."""
    from src.cv.training.train import export_model

    path = export_model(
        model_path=args.model,
        format=args.format,
        imgsz=args.imgsz,
        simplify=not args.no_simplify,
        dynamic=args.dynamic,
    )
    print(f"Exported model to: {path}")
    return 0


def cmd_active_learn(args: argparse.Namespace) -> int:
    """Run active learning: identify uncertain frames for labeling."""
    from src.cv.detection import HorseDetector
    from src.cv.keypoints import EquineKeypointEstimator
    from src.cv.training.active_learning import select_uncertain_frames, export_uncertain_frames
    from src.cv.video import extract_frames

    import numpy as np

    print(f"Processing video: {args.video}")

    batch = extract_frames(args.video, stride=args.stride, max_frames=args.max_frames)

    detector = HorseDetector(confidence_threshold=0.4)
    estimator = EquineKeypointEstimator(model_path=args.model, confidence_threshold=0.2)

    # Run inference and collect confidences
    all_confs = []
    for frame in batch.frames:
        dets = detector.detect(frame)
        kpts = estimator.estimate(frame, dets)
        if kpts:
            all_confs.append(kpts[0].confidence)
        else:
            all_confs.append(np.zeros(24, dtype=np.float32))

    conf_array = np.array(all_confs)

    # Select uncertain frames
    uncertain = select_uncertain_frames(
        conf_array,
        n_select=args.num_frames,
        strategy=args.strategy,
    )

    # Export
    saved = export_uncertain_frames(args.video, uncertain, args.output)

    print(f"\nSelected {len(uncertain)} uncertain frames")
    print(f"Exported to: {args.output}")
    print(f"\nTop uncertain frames:")
    for uf in uncertain[:10]:
        print(f"  Frame {uf.frame_idx}: score={uf.uncertainty_score:.3f}, "
              f"mean_conf={uf.mean_confidence:.3f}, "
              f"low_kpts={uf.num_low_conf_keypoints}/24")

    return 0


def cmd_auto_label_dir(args: argparse.Namespace) -> int:
    """Auto-label images in a directory using pretrained models."""
    from src.cv.training.auto_label import AutoLabelAgent

    agent = AutoLabelAgent(
        detection_confidence=args.det_conf,
        keypoint_confidence=args.kpt_conf,
        quality_threshold=args.quality_threshold,
        min_confident_kpts=args.min_kpts,
        source=args.source,
        vitpose_size=args.vitpose_size,
    )

    review_dir = Path(args.output) / "review" if not args.no_review else None
    result = agent.label_directory(args.image_dir, args.output, review_dir=review_dir)

    print(f"\nAuto-Labeling Complete")
    print(f"{'=' * 50}")
    print(f"Images processed:    {result.num_images}")
    print(f"Images labeled:      {result.num_labeled}")
    print(f"Total horses:        {result.num_horses}")
    print(f"Flagged for review:  {result.num_flagged}")
    print(f"Mean quality:        {result.mean_quality:.3f}")
    print(f"Mean confident kpts: {result.mean_confident_kpts:.1f}/24")
    print(f"\nLabels:  {result.labels_dir}")
    if result.review_manifest:
        print(f"Review:  {result.review_manifest}")
    return 0


def cmd_auto_label_video(args: argparse.Namespace) -> int:
    """Extract frames from a video and auto-label them."""
    from src.cv.training.auto_label import AutoLabelAgent

    agent = AutoLabelAgent(
        detection_confidence=args.det_conf,
        keypoint_confidence=args.kpt_conf,
        quality_threshold=args.quality_threshold,
        min_confident_kpts=args.min_kpts,
        source=args.source,
        vitpose_size=args.vitpose_size,
    )

    result = agent.label_video(
        args.video,
        output_dir=args.output,
        num_frames=args.num_frames,
        strategy=args.strategy,
    )

    print(f"\nAuto-Labeling from Video Complete")
    print(f"{'=' * 50}")
    print(f"Frames extracted:    {result.num_images}")
    print(f"Frames labeled:      {result.num_labeled}")
    print(f"Total horses:        {result.num_horses}")
    print(f"Flagged for review:  {result.num_flagged}")
    print(f"Mean quality:        {result.mean_quality:.3f}")
    print(f"Mean confident kpts: {result.mean_confident_kpts:.1f}/24")
    print(f"\nLabels:  {result.labels_dir}")
    if result.review_manifest:
        print(f"Review:  {result.review_manifest}")

    print(f"\nNext steps:")
    print(f"  1. Review flagged images in {Path(args.output) / 'review'}")
    print(f"  2. Correct labels with Roboflow or DLC GUI")
    print(f"  3. Run: equine-train split {args.output} -o {args.output}_split")
    print(f"  4. Run: equine-train train {args.output}_split")
    return 0


def cmd_label_sale(args: argparse.Namespace) -> int:
    """Fetch OBS sale videos and auto-label them end-to-end."""
    from src.cv.training.video_pipeline import SaleVideoLabelPipeline

    pipeline = SaleVideoLabelPipeline(
        sale_id=args.sale_id,
        frames_per_video=args.frames_per_video,
        frame_strategy=args.strategy,
        detection_confidence=args.det_conf,
        keypoint_confidence=args.kpt_conf,
        quality_threshold=args.quality_threshold,
        min_confident_kpts=args.min_kpts,
        max_hips=args.max_hips,
    )

    result = pipeline.run(output_dir=args.output)

    print(f"\nSale Auto-Labeling Complete")
    print(f"{'=' * 55}")
    print(f"Sale:                {result.sale_name} (ID: {result.sale_id})")
    print(f"Hips with video:     {result.num_hips_with_video}")
    print(f"Videos downloaded:    {result.num_videos_downloaded}")
    print(f"Download errors:     {result.num_download_errors}")
    print(f"Frames extracted:    {result.num_frames_extracted}")
    print(f"Frames labeled:      {result.num_frames_labeled}")
    print(f"Horses detected:     {result.num_horses_detected}")
    print(f"Flagged for review:  {result.num_flagged_for_review}")
    print(f"Mean quality:        {result.mean_quality:.3f}")
    print(f"\nOutput:   {result.output_dir}")

    print(f"\nNext steps:")
    print(f"  1. Review flagged images in {Path(args.output) / 'review'}")
    print(f"  2. Correct labels in Roboflow / DLC GUI")
    print(f"  3. equine-train split {args.output} -o {args.output}_split")
    print(f"  4. equine-train train {args.output}_split --preset finetune")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="equine-train",
        description="Training & dataset tools for equine keypoint YOLO-Pose",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="command")

    # prepare
    p = sub.add_parser("prepare", help="Extract frames from videos for annotation")
    p.add_argument("videos", nargs="+", help="Video files to extract from")
    p.add_argument("-o", "--output", required=True, help="Output directory")
    p.add_argument("-n", "--num-frames", type=int, default=50, help="Frames per video")
    p.add_argument("--strategy", default="uniform", choices=["uniform", "random", "motion"])

    # convert
    p = sub.add_parser("convert", help="Convert COCO annotations to YOLO-Pose")
    p.add_argument("coco_json", help="Path to COCO keypoint JSON")
    p.add_argument("-o", "--output", required=True, help="Output directory")
    p.add_argument("--image-dir", help="Image directory (if different from COCO paths)")
    p.add_argument("--no-copy", action="store_true", help="Don't copy images")

    # split
    p = sub.add_parser("split", help="Split dataset into train/val/test")
    p.add_argument("dataset_dir", help="Source dataset directory")
    p.add_argument("-o", "--output", required=True, help="Output directory")
    p.add_argument("--train-ratio", type=float, default=0.8)
    p.add_argument("--val-ratio", type=float, default=0.15)
    p.add_argument("--seed", type=int, default=42)

    # validate
    p = sub.add_parser("validate", help="Validate a YOLO-Pose dataset")
    p.add_argument("dataset_dir", help="Dataset directory to validate")

    # train
    p = sub.add_parser("train", help="Train YOLO-Pose on equine dataset")
    p.add_argument("dataset_dir", help="Dataset directory (with train/val splits)")
    p.add_argument("-o", "--output", help="Output directory for training run")
    p.add_argument("--model", default="yolo11n-pose.pt", help="Base model")
    p.add_argument("--preset", default="finetune", choices=["finetune", "scratch", "active_learning"])
    p.add_argument("--resume", action="store_true", help="Resume previous training")

    # evaluate
    p = sub.add_parser("evaluate", help="Evaluate a trained model")
    p.add_argument("model", help="Path to model weights")
    p.add_argument("dataset_yaml", help="Path to dataset YAML")
    p.add_argument("--split", default="val", choices=["val", "test"])

    # export
    p = sub.add_parser("export", help="Export model for production")
    p.add_argument("model", help="Path to model weights")
    p.add_argument("--format", default="onnx", choices=["onnx", "torchscript", "openvino"])
    p.add_argument("--imgsz", type=int, default=640)
    p.add_argument("--no-simplify", action="store_true")
    p.add_argument("--dynamic", action="store_true", help="Dynamic input shapes")

    # active-learn
    p = sub.add_parser("active-learn", help="Select uncertain frames for labeling")
    p.add_argument("video", help="Video to analyze")
    p.add_argument("--model", default="yolo11n-pose.pt", help="Model for inference")
    p.add_argument("-o", "--output", required=True, help="Output directory for frames")
    p.add_argument("-n", "--num-frames", type=int, default=50)
    p.add_argument("--stride", type=int, default=2, help="Process every Nth frame")
    p.add_argument("--max-frames", type=int, default=500)
    p.add_argument("--strategy", default="combined", choices=["low_confidence", "high_variance", "combined"])

    # auto-label (directory)
    p = sub.add_parser("auto-label", help="Auto-label images using pretrained models")
    p.add_argument("image_dir", help="Directory of images to label")
    p.add_argument("-o", "--output", required=True, help="Output labels directory")
    p.add_argument("--source", default="vitpose", choices=["coco", "vitpose", "ensemble"],
                   help="Keypoint source: coco (YOLO human-pose), vitpose (AP-10K animal), "
                        "ensemble (both, confidence-weighted)")
    p.add_argument("--vitpose-size", default="base", choices=["small", "base", "large", "huge"],
                   help="ViTPose++ model size (default: base)")
    p.add_argument("--det-conf", type=float, default=0.4, help="Detection confidence")
    p.add_argument("--kpt-conf", type=float, default=0.2, help="Keypoint confidence")
    p.add_argument("--quality-threshold", type=float, default=0.4, help="Min quality to accept")
    p.add_argument("--min-kpts", type=int, default=8, help="Min confident keypoints")
    p.add_argument("--no-review", action="store_true", help="Skip review flagging")

    # auto-label-video
    p = sub.add_parser("auto-label-video", help="Extract frames from video and auto-label")
    p.add_argument("video", help="Video file")
    p.add_argument("-o", "--output", required=True, help="Output directory")
    p.add_argument("-n", "--num-frames", type=int, default=100, help="Frames to extract")
    p.add_argument("--strategy", default="uniform", choices=["uniform", "random", "motion"])
    p.add_argument("--source", default="vitpose", choices=["coco", "vitpose", "ensemble"],
                   help="Keypoint source model")
    p.add_argument("--vitpose-size", default="base", choices=["small", "base", "large", "huge"])
    p.add_argument("--det-conf", type=float, default=0.4)
    p.add_argument("--kpt-conf", type=float, default=0.2)
    p.add_argument("--quality-threshold", type=float, default=0.4)
    p.add_argument("--min-kpts", type=int, default=8)

    # label-sale (end-to-end: fetch OBS sale -> download videos -> auto-label)
    p = sub.add_parser("label-sale", help="Fetch OBS sale videos and auto-label them")
    p.add_argument("sale_id", help="OBS sale ID (e.g. 149 for 2026 March)")
    p.add_argument("-o", "--output", required=True, help="Output directory")
    p.add_argument("-n", "--frames-per-video", type=int, default=30, help="Frames per video")
    p.add_argument("--strategy", default="motion", choices=["uniform", "random", "motion"])
    p.add_argument("--max-hips", type=int, default=None, help="Max hips to process")
    p.add_argument("--det-conf", type=float, default=0.4)
    p.add_argument("--kpt-conf", type=float, default=0.2)
    p.add_argument("--quality-threshold", type=float, default=0.4)
    p.add_argument("--min-kpts", type=int, default=8)

    args = parser.parse_args()
    setup_logging(args.verbose)

    commands = {
        "prepare": cmd_prepare,
        "convert": cmd_convert,
        "split": cmd_split,
        "validate": cmd_validate,
        "train": cmd_train,
        "evaluate": cmd_evaluate,
        "export": cmd_export,
        "active-learn": cmd_active_learn,
        "auto-label": cmd_auto_label_dir,
        "auto-label-video": cmd_auto_label_video,
        "label-sale": cmd_label_sale,
    }

    if args.command in commands:
        return commands[args.command](args)
    else:
        parser.print_help()
        return 0


if __name__ == "__main__":
    sys.exit(main())
