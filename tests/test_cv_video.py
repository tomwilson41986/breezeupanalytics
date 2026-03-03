"""Tests for video I/O utilities."""

import tempfile
from pathlib import Path

import cv2
import numpy as np
import pytest

from src.cv.video import FrameBatch, VideoWriter, extract_frames, get_video_meta


@pytest.fixture
def sample_video(tmp_path):
    """Create a minimal test video (30 frames of colored noise)."""
    path = tmp_path / "test.mp4"
    fps = 30.0
    width, height = 320, 240
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(path), fourcc, fps, (width, height))

    for i in range(30):
        # Gradient frame so each frame is slightly different
        frame = np.zeros((height, width, 3), dtype=np.uint8)
        frame[:, :, 0] = i * 8  # blue channel varies
        frame[:, :, 1] = 128
        frame[:, :, 2] = 64
        writer.write(frame)

    writer.release()
    return path


def test_get_video_meta(sample_video):
    meta = get_video_meta(sample_video)
    assert meta.width == 320
    assert meta.height == 240
    assert meta.fps == pytest.approx(30.0, abs=1.0)
    assert meta.frame_count == 30
    assert meta.duration_s == pytest.approx(1.0, abs=0.1)


def test_get_video_meta_missing():
    with pytest.raises(FileNotFoundError):
        get_video_meta("/nonexistent/video.mp4")


def test_extract_all_frames(sample_video):
    batch = extract_frames(sample_video)
    assert len(batch.frames) == 30
    assert len(batch.indices) == 30
    assert batch.indices[0] == 0
    assert batch.indices[-1] == 29
    assert batch.frames[0].shape == (240, 320, 3)


def test_extract_with_stride(sample_video):
    batch = extract_frames(sample_video, stride=3)
    assert len(batch.frames) == 10  # 30 / 3
    assert batch.indices == list(range(0, 30, 3))


def test_extract_with_max_frames(sample_video):
    batch = extract_frames(sample_video, max_frames=5)
    assert len(batch.frames) == 5


def test_extract_with_range(sample_video):
    batch = extract_frames(sample_video, start_frame=10, end_frame=20)
    assert len(batch.frames) == 10
    assert batch.indices[0] == 10
    assert batch.indices[-1] == 19


def test_video_writer(tmp_path):
    out_path = tmp_path / "output.mp4"
    frame = np.zeros((240, 320, 3), dtype=np.uint8)

    with VideoWriter(out_path, fps=30.0, width=320, height=240) as writer:
        for _ in range(10):
            writer.write(frame)

    assert out_path.exists()
    meta = get_video_meta(out_path)
    assert meta.frame_count == 10
