"""CLI entry point for equine gait analysis pipeline.

Usage:
    python -m src.cv.cli analyze <video_path> [options]
    python -m src.cv.cli info <video_path>
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from src.cv.pipeline import GaitAnalysisPipeline, PipelineConfig
from src.cv.video import get_video_meta


def setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def cmd_analyze(args: argparse.Namespace) -> int:
    """Run the full gait analysis pipeline on a video."""
    video_path = Path(args.video)
    if not video_path.exists():
        print(f"Error: Video not found: {video_path}", file=sys.stderr)
        return 1

    config = PipelineConfig(
        detection_model=args.detection_model,
        detection_confidence=args.det_conf,
        keypoint_model=args.keypoint_model,
        keypoint_confidence=args.kpt_conf,
        use_vitpose=args.vitpose,
        vitpose_size=args.vitpose_size,
        use_sam=args.sam,
        sam_model_size=args.sam_size,
        enable_anatomy_correction=args.anatomy_correction,
        anatomy_correction_strength=args.anatomy_strength,
        enable_tracking=not args.no_tracking,
        output_video=not args.no_video,
        output_csv=not args.no_csv,
        output_json=not args.no_json,
        frame_stride=args.stride,
        max_frames=args.max_frames,
        px_per_meter=args.px_per_meter,
        smoothing_window=args.smooth_window,
    )

    pipeline = GaitAnalysisPipeline(config)
    output_dir = Path(args.output) if args.output else None
    result = pipeline.process_video(video_path, output_dir)

    # Print summary
    print(f"\n{'=' * 60}")
    print(f"Equine Gait Analysis Complete")
    print(f"{'=' * 60}")
    print(f"Video:            {result.video_path}")
    print(f"Duration:         {result.duration_s:.1f}s")
    print(f"Frames processed: {result.frames_processed}")
    print(f"Horses detected:  {result.horses_detected}")
    print(f"Processing time:  {result.processing_time_s:.1f}s")

    for m in result.horse_metrics:
        print(f"\n--- Horse #{m.track_id} ---")
        print(f"  Strides:          {m.num_strides}")
        print(f"  Stride frequency: {m.mean_stride_frequency_hz:.2f} Hz")
        print(f"  Stride duration:  {m.mean_stride_duration_s:.3f} s")
        print(f"  Stride length:    {m.mean_stride_length_px:.0f} px")
        print(f"  Speed:            {m.mean_speed_px_s:.0f} px/s")
        if m.mean_speed_m_s is not None:
            print(f"  Speed:            {m.mean_speed_m_s:.1f} m/s")
        if m.mean_lateral_symmetry is not None:
            print(f"  Symmetry index:   {m.mean_lateral_symmetry:.1f}%")
        for limb, df in m.duty_factors.items():
            print(f"  Duty factor ({limb}): {df:.3f}")

    if result.output_video_path:
        print(f"\nAnnotated video:  {result.output_video_path}")
    if result.output_csv_path:
        print(f"Metrics CSV:      {result.output_csv_path}")
    if result.output_json_path:
        print(f"Metrics JSON:     {result.output_json_path}")

    return 0


def cmd_info(args: argparse.Namespace) -> int:
    """Print video metadata."""
    video_path = Path(args.video)
    if not video_path.exists():
        print(f"Error: Video not found: {video_path}", file=sys.stderr)
        return 1

    meta = get_video_meta(video_path)
    print(f"Path:       {meta.path}")
    print(f"Resolution: {meta.width}x{meta.height}")
    print(f"FPS:        {meta.fps}")
    print(f"Frames:     {meta.frame_count}")
    print(f"Duration:   {meta.duration_s:.2f}s")
    print(f"Codec:      {meta.codec}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="equine-gait",
        description="Equine gait analysis & keypoint tracking from video",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose logging")
    sub = parser.add_subparsers(dest="command")

    # analyze
    p_analyze = sub.add_parser("analyze", help="Run gait analysis on a video")
    p_analyze.add_argument("video", help="Path to input video")
    p_analyze.add_argument("-o", "--output", help="Output directory")
    p_analyze.add_argument("--detection-model", default="yolo11n.pt", help="YOLO detection model")
    p_analyze.add_argument("--keypoint-model", default="yolo11n-pose.pt", help="YOLO pose model")
    p_analyze.add_argument("--vitpose", action="store_true",
                           help="Use ViTPose++ (AP-10K animal head) instead of YOLO-Pose for keypoints")
    p_analyze.add_argument("--vitpose-size", default="base", choices=["small", "base", "large", "huge"],
                           help="ViTPose++ model size (default: base)")
    p_analyze.add_argument("--det-conf", type=float, default=0.5, help="Detection confidence threshold")
    p_analyze.add_argument("--kpt-conf", type=float, default=0.3, help="Keypoint confidence threshold")
    p_analyze.add_argument("--no-tracking", action="store_true", help="Disable multi-object tracking")
    p_analyze.add_argument("--no-video", action="store_true", help="Skip annotated video output")
    p_analyze.add_argument("--no-csv", action="store_true", help="Skip CSV output")
    p_analyze.add_argument("--no-json", action="store_true", help="Skip JSON output")
    p_analyze.add_argument("--stride", type=int, default=1, help="Process every Nth frame")
    p_analyze.add_argument("--max-frames", type=int, default=None, help="Max frames to process")
    p_analyze.add_argument("--px-per-meter", type=float, default=None, help="Pixels per meter for calibration")
    p_analyze.add_argument("--smooth-window", type=int, default=7, help="Smoothing window size")
    p_analyze.add_argument("--sam", action="store_true",
                           help="Use Grounding DINO + SAM 2 for horse detection/segmentation")
    p_analyze.add_argument("--sam-size", default="tiny", choices=["tiny", "small", "base", "large"],
                           help="SAM 2 model size (default: tiny)")
    p_analyze.add_argument("--anatomy-correction", action="store_true",
                           help="Apply equine anatomy corrections to keypoints")
    p_analyze.add_argument("--anatomy-strength", type=float, default=0.7,
                           help="Anatomy correction strength 0-1 (default: 0.7)")

    # info
    p_info = sub.add_parser("info", help="Print video metadata")
    p_info.add_argument("video", help="Path to video file")

    args = parser.parse_args()
    setup_logging(args.verbose)

    if args.command == "analyze":
        return cmd_analyze(args)
    elif args.command == "info":
        return cmd_info(args)
    else:
        parser.print_help()
        return 0


if __name__ == "__main__":
    sys.exit(main())
