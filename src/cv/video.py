"""Video I/O utilities for equine gait analysis.

Handles frame extraction from video files, frame preprocessing,
and writing annotated output videos.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class VideoMeta:
    """Metadata extracted from a video file."""
    path: Path
    width: int
    height: int
    fps: float
    frame_count: int
    duration_s: float
    codec: str


@dataclass
class FrameBatch:
    """A batch of frames extracted from a video with their indices."""
    frames: list[np.ndarray]
    indices: list[int]
    fps: float
    source: Path = field(default_factory=lambda: Path("."))


def get_video_meta(video_path: str | Path) -> VideoMeta:
    """Read metadata from a video file without loading frames."""
    path = Path(video_path)
    if not path.exists():
        raise FileNotFoundError(f"Video not found: {path}")

    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise RuntimeError(f"Failed to open video: {path}")

    try:
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = cap.get(cv2.CAP_PROP_FPS)
        n_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fourcc = int(cap.get(cv2.CAP_PROP_FOURCC))
        codec = "".join(chr((fourcc >> 8 * i) & 0xFF) for i in range(4))
        duration = n_frames / fps if fps > 0 else 0.0

        return VideoMeta(
            path=path,
            width=w,
            height=h,
            fps=fps,
            frame_count=n_frames,
            duration_s=duration,
            codec=codec,
        )
    finally:
        cap.release()


def extract_frames(
    video_path: str | Path,
    *,
    start_frame: int = 0,
    end_frame: int | None = None,
    stride: int = 1,
    max_frames: int | None = None,
) -> FrameBatch:
    """Extract frames from a video file.

    Args:
        video_path: Path to the video file.
        start_frame: First frame index to extract.
        end_frame: Last frame index (exclusive). None = end of video.
        stride: Extract every Nth frame.
        max_frames: Cap the total number of frames returned.

    Returns:
        FrameBatch with decoded BGR frames and their indices.
    """
    path = Path(video_path)
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise RuntimeError(f"Failed to open video: {path}")

    fps = cap.get(cv2.CAP_PROP_FPS)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    end = min(end_frame, total) if end_frame is not None else total

    frames: list[np.ndarray] = []
    indices: list[int] = []

    cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
    idx = start_frame

    while idx < end:
        if max_frames is not None and len(frames) >= max_frames:
            break

        ret, frame = cap.read()
        if not ret:
            break

        if (idx - start_frame) % stride == 0:
            frames.append(frame)
            indices.append(idx)

        idx += 1

    cap.release()
    logger.info("Extracted %d frames from %s (range %d-%d, stride %d)", len(frames), path, start_frame, end, stride)

    return FrameBatch(frames=frames, indices=indices, fps=fps, source=path)


class VideoWriter:
    """Context manager for writing annotated frames to a video file."""

    def __init__(self, output_path: str | Path, fps: float, width: int, height: int):
        self.path = Path(output_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        self._writer = cv2.VideoWriter(str(self.path), fourcc, fps, (width, height))
        if not self._writer.isOpened():
            raise RuntimeError(f"Failed to open video writer: {self.path}")
        self._count = 0

    def write(self, frame: np.ndarray) -> None:
        self._writer.write(frame)
        self._count += 1

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self._writer.release()
        logger.info("Wrote %d frames to %s", self._count, self.path)
