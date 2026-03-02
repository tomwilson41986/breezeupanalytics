"""Horse detection using YOLO object detection.

Detects horse bounding boxes in video frames using a pretrained YOLO model.
Supports both single-frame and batch inference.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import torch
from ultralytics import YOLO

logger = logging.getLogger(__name__)

# COCO class ID for 'horse' = 17
COCO_HORSE_CLASS_ID = 17


@dataclass
class Detection:
    """A single horse bounding box detection."""
    bbox: np.ndarray       # [x1, y1, x2, y2] in pixels
    confidence: float
    track_id: int | None = None

    @property
    def width(self) -> float:
        return float(self.bbox[2] - self.bbox[0])

    @property
    def height(self) -> float:
        return float(self.bbox[3] - self.bbox[1])

    @property
    def area(self) -> float:
        return self.width * self.height

    @property
    def center(self) -> tuple[float, float]:
        return (
            float((self.bbox[0] + self.bbox[2]) / 2),
            float((self.bbox[1] + self.bbox[3]) / 2),
        )


class HorseDetector:
    """YOLO-based horse detector.

    Uses a pretrained YOLO model to detect horses in video frames.
    Filters detections to the 'horse' class only.
    """

    def __init__(
        self,
        model_path: str = "yolo11n.pt",
        confidence_threshold: float = 0.5,
        device: str | None = None,
    ):
        self.confidence_threshold = confidence_threshold
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")

        logger.info("Loading YOLO model: %s on %s", model_path, self.device)
        self.model = YOLO(model_path)

    def detect(self, frame: np.ndarray) -> list[Detection]:
        """Detect horses in a single frame.

        Args:
            frame: BGR image as numpy array (H, W, 3).

        Returns:
            List of Detection objects for horses found in the frame.
        """
        results = self.model(
            frame,
            conf=self.confidence_threshold,
            classes=[COCO_HORSE_CLASS_ID],
            verbose=False,
            device=self.device,
        )

        detections = []
        for result in results:
            if result.boxes is None:
                continue
            for box in result.boxes:
                bbox = box.xyxy[0].cpu().numpy()
                conf = float(box.conf[0])
                detections.append(Detection(bbox=bbox, confidence=conf))

        return detections

    def detect_batch(self, frames: list[np.ndarray]) -> list[list[Detection]]:
        """Detect horses in a batch of frames.

        Args:
            frames: List of BGR images.

        Returns:
            List of detection lists, one per frame.
        """
        results = self.model(
            frames,
            conf=self.confidence_threshold,
            classes=[COCO_HORSE_CLASS_ID],
            verbose=False,
            device=self.device,
        )

        all_detections = []
        for result in results:
            frame_dets = []
            if result.boxes is not None:
                for box in result.boxes:
                    bbox = box.xyxy[0].cpu().numpy()
                    conf = float(box.conf[0])
                    frame_dets.append(Detection(bbox=bbox, confidence=conf))
            all_detections.append(frame_dets)

        return all_detections

    def detect_and_track(
        self,
        frames: list[np.ndarray],
        tracker: str = "bytetrack.yaml",
    ) -> list[list[Detection]]:
        """Detect and track horses across a sequence of frames.

        Uses ByteTrack via YOLO's built-in tracking to maintain consistent
        identity across frames.

        Args:
            frames: Ordered list of BGR frames.
            tracker: Tracker config (bytetrack.yaml or botsort.yaml).

        Returns:
            List of detection lists with track_id assigned.
        """
        all_detections = []

        for frame in frames:
            results = self.model.track(
                frame,
                conf=self.confidence_threshold,
                classes=[COCO_HORSE_CLASS_ID],
                tracker=tracker,
                persist=True,
                verbose=False,
                device=self.device,
            )

            frame_dets = []
            for result in results:
                if result.boxes is None:
                    continue
                for box in result.boxes:
                    bbox = box.xyxy[0].cpu().numpy()
                    conf = float(box.conf[0])
                    track_id = int(box.id[0]) if box.id is not None else None
                    frame_dets.append(Detection(bbox=bbox, confidence=conf, track_id=track_id))
            all_detections.append(frame_dets)

        return all_detections


def crop_detection(frame: np.ndarray, det: Detection, padding: float = 0.1) -> np.ndarray:
    """Crop a detected horse region from a frame with optional padding.

    Args:
        frame: Full BGR image.
        det: Detection with bounding box.
        padding: Fractional padding to add around the bbox (0.1 = 10%).

    Returns:
        Cropped BGR image.
    """
    h, w = frame.shape[:2]
    x1, y1, x2, y2 = det.bbox

    pad_w = (x2 - x1) * padding
    pad_h = (y2 - y1) * padding

    x1 = max(0, int(x1 - pad_w))
    y1 = max(0, int(y1 - pad_h))
    x2 = min(w, int(x2 + pad_w))
    y2 = min(h, int(y2 + pad_h))

    return frame[y1:y2, x1:x2].copy()
