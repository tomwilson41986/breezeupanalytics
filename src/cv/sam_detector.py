"""SAM 2 + Grounding DINO horse/jockey detection and segmentation.

Uses Grounding DINO for text-prompted detection ("horse", "jockey") and
SAM 2 for pixel-precise segmentation masks.  For video, SAM 2 tracks
objects across frames after initial detection, providing robust tracking
even through challenging viewpoints (front, rear, oblique).

Pipeline:
    1. Grounding DINO: text prompt → bounding boxes for "horse" and "jockey"
    2. SAM 2: bounding boxes → segmentation masks
    3. Extract horse bounding boxes from masks for keypoint estimation

Usage:
    detector = SAMHorseDetector()
    detections = detector.detect(frame)  # list[Detection]
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import cv2
import numpy as np
import torch
from PIL import Image

from src.cv.detection import Detection

logger = logging.getLogger(__name__)


@dataclass
class SegmentationResult:
    """Detection + segmentation mask for a single object."""
    bbox: np.ndarray          # [x1, y1, x2, y2]
    confidence: float
    label: str                # "horse" or "jockey"
    mask: np.ndarray | None   # (H, W) boolean mask, None if no mask
    track_id: int | None = None


class SAMHorseDetector:
    """Grounding DINO + SAM 2 detector for horses and jockeys.

    Replaces YOLO detection with text-prompted zero-shot detection
    using Grounding DINO, refined with SAM 2 segmentation masks.

    The horse bounding boxes are returned as Detection objects
    compatible with the existing pipeline.
    """

    def __init__(
        self,
        sam_model_size: str = "tiny",
        box_threshold: float = 0.25,
        text_threshold: float = 0.20,
        device: str | None = None,
    ):
        from transformers import (
            AutoModelForZeroShotObjectDetection,
            AutoProcessor,
            Sam2Model,
            Sam2Processor,
        )

        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.box_threshold = box_threshold
        self.text_threshold = text_threshold

        # --- Grounding DINO for text-based detection ---
        logger.info("Loading Grounding DINO (tiny)...")
        self.dino_processor = AutoProcessor.from_pretrained(
            "IDEA-Research/grounding-dino-tiny"
        )
        self.dino_model = AutoModelForZeroShotObjectDetection.from_pretrained(
            "IDEA-Research/grounding-dino-tiny"
        ).to(self.device)
        self.dino_model.eval()

        # --- SAM 2 for segmentation ---
        sam_models = {
            "tiny": "facebook/sam2.1-hiera-tiny",
            "small": "facebook/sam2.1-hiera-small",
            "base": "facebook/sam2.1-hiera-base-plus",
            "large": "facebook/sam2.1-hiera-large",
        }
        sam_id = sam_models.get(sam_model_size, sam_models["tiny"])
        logger.info("Loading SAM 2.1 (%s) from %s...", sam_model_size, sam_id)
        self.sam_processor = Sam2Processor.from_pretrained(sam_id)
        self.sam_model = Sam2Model.from_pretrained(sam_id).to(self.device)
        self.sam_model.eval()

        logger.info("SAM Horse Detector ready (device=%s)", self.device)

    def detect(
        self,
        frame: np.ndarray,
        text_prompt: str = "a horse . a jockey",
    ) -> list[Detection]:
        """Detect horses in a frame using Grounding DINO + SAM 2.

        Args:
            frame: BGR image (H, W, 3).
            text_prompt: Grounding DINO text prompt.

        Returns:
            List of Detection objects for horses (not jockeys).
        """
        results = self.detect_and_segment(frame, text_prompt)

        # Filter to horse detections only and convert to Detection objects
        detections = []
        for seg in results:
            if "horse" in seg.label.lower():
                det = Detection(
                    bbox=seg.bbox,
                    confidence=seg.confidence,
                    track_id=seg.track_id,
                )
                detections.append(det)

        return detections

    def detect_fast(
        self,
        frame: np.ndarray,
        text_prompt: str = "a horse . a jockey",
    ) -> list[Detection]:
        """Fast detection using Grounding DINO only (no SAM segmentation).

        Significantly faster than detect() since it skips SAM.
        """
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        pil_image = Image.fromarray(rgb)
        h, w = frame.shape[:2]

        dino_inputs = self.dino_processor(
            images=pil_image, text=text_prompt, return_tensors="pt"
        ).to(self.device)

        with torch.no_grad():
            dino_outputs = self.dino_model(**dino_inputs)

        dino_results = self.dino_processor.post_process_grounded_object_detection(
            dino_outputs,
            dino_inputs.input_ids,
            threshold=self.box_threshold,
            text_threshold=self.text_threshold,
            target_sizes=[(h, w)],
        )[0]

        boxes = dino_results["boxes"]
        scores = dino_results["scores"]
        labels = dino_results["labels"]

        detections = []
        for i in range(len(boxes)):
            if "horse" in labels[i].lower():
                detections.append(Detection(
                    bbox=boxes[i].cpu().numpy(),
                    confidence=float(scores[i]),
                ))
        return detections

    def detect_and_segment(
        self,
        frame: np.ndarray,
        text_prompt: str = "a horse . a jockey",
    ) -> list[SegmentationResult]:
        """Detect and segment horses and jockeys in a frame.

        Args:
            frame: BGR image (H, W, 3).
            text_prompt: Grounding DINO text prompt.

        Returns:
            List of SegmentationResult with masks.
        """
        # Convert BGR to RGB PIL image
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        pil_image = Image.fromarray(rgb)
        h, w = frame.shape[:2]

        # --- Step 1: Grounding DINO detection ---
        dino_inputs = self.dino_processor(
            images=pil_image, text=text_prompt, return_tensors="pt"
        ).to(self.device)

        with torch.no_grad():
            dino_outputs = self.dino_model(**dino_inputs)

        dino_results = self.dino_processor.post_process_grounded_object_detection(
            dino_outputs,
            dino_inputs.input_ids,
            threshold=self.box_threshold,
            text_threshold=self.text_threshold,
            target_sizes=[(h, w)],
        )[0]

        boxes = dino_results["boxes"]      # (N, 4) xyxy
        scores = dino_results["scores"]    # (N,)
        labels = dino_results["labels"]    # list[str]

        if len(boxes) == 0:
            return []

        # --- Step 2: SAM 2 segmentation ---
        input_boxes = [[box.tolist() for box in boxes]]
        sam_inputs = self.sam_processor(
            images=pil_image,
            input_boxes=input_boxes,
            return_tensors="pt",
        ).to(self.device)

        with torch.no_grad():
            sam_outputs = self.sam_model(**sam_inputs, multimask_output=False)

        masks = self.sam_processor.post_process_masks(
            sam_outputs.pred_masks.cpu(),
            sam_inputs["original_sizes"],
        )[0]  # (N, 1, H, W)

        # --- Build results ---
        results = []
        for i in range(len(boxes)):
            bbox = boxes[i].cpu().numpy()
            mask = masks[i, 0].numpy() if masks is not None else None

            # Refine bounding box from mask if available
            if mask is not None and mask.any():
                bbox = self._mask_to_bbox(mask)

            results.append(SegmentationResult(
                bbox=bbox,
                confidence=float(scores[i]),
                label=labels[i],
                mask=mask,
            ))

        return results

    def detect_batch(
        self,
        frames: list[np.ndarray],
        fast: bool = True,
    ) -> list[list[Detection]]:
        """Detect horses in a batch of frames.

        Uses Grounding DINO only (fast=True) or Grounding DINO + SAM (fast=False).
        """
        detect_fn = self.detect_fast if fast else self.detect
        all_detections = []
        for i, frame in enumerate(frames):
            dets = detect_fn(frame)
            all_detections.append(dets)

            if i % 100 == 0 and i > 0:
                logger.info("SAM detection: %d/%d frames", i, len(frames))

        return all_detections

    def detect_and_track(
        self,
        frames: list[np.ndarray],
        seed_frame_idx: int | None = None,
    ) -> list[list[Detection]]:
        """Detect horses across video frames using Grounding DINO.

        Uses fast per-frame detection with Grounding DINO for robust
        horse detection from all viewpoints. Assigns consistent track
        IDs based on IoU overlap between consecutive frames.

        Args:
            frames: List of BGR images.
            seed_frame_idx: Unused (kept for API compatibility).

        Returns:
            List of Detection lists, one per frame.
        """
        if not frames:
            return []

        logger.info("SAM detect_and_track: %d frames (per-frame Grounding DINO)", len(frames))

        all_detections = self.detect_batch(frames, fast=True)

        # Assign consistent track IDs using IoU between consecutive frames
        self._assign_track_ids(all_detections)

        detected_count = sum(1 for dets in all_detections if len(dets) > 0)
        logger.info(
            "Grounding DINO detection: %d/%d frames with horses (%.0f%%)",
            detected_count, len(frames), 100 * detected_count / len(frames),
        )

        return all_detections

    def _assign_track_ids(self, all_detections: list[list[Detection]]) -> None:
        """Assign consistent track IDs based on IoU between frames."""
        next_id = 1
        prev_dets: list[Detection] = []

        for dets in all_detections:
            if not dets:
                prev_dets = []
                continue

            if not prev_dets:
                for d in dets:
                    d.track_id = next_id
                    next_id += 1
            else:
                # Match by best IoU
                used = set()
                for d in dets:
                    best_iou = 0.0
                    best_match = None
                    for pd in prev_dets:
                        if pd.track_id in used:
                            continue
                        iou = self._compute_iou(d.bbox, pd.bbox)
                        if iou > best_iou:
                            best_iou = iou
                            best_match = pd

                    if best_match and best_iou > 0.1:
                        d.track_id = best_match.track_id
                        used.add(best_match.track_id)
                    else:
                        d.track_id = next_id
                        next_id += 1

            prev_dets = dets

    @staticmethod
    def _compute_iou(box1: np.ndarray, box2: np.ndarray) -> float:
        """Compute IoU between two xyxy boxes."""
        x1 = max(box1[0], box2[0])
        y1 = max(box1[1], box2[1])
        x2 = min(box1[2], box2[2])
        y2 = min(box1[3], box2[3])
        inter = max(0, x2 - x1) * max(0, y2 - y1)
        area1 = (box1[2] - box1[0]) * (box1[3] - box1[1])
        area2 = (box2[2] - box2[0]) * (box2[3] - box2[1])
        union = area1 + area2 - inter
        return inter / union if union > 0 else 0.0

    def _track_with_sam2_video(
        self,
        frames: list[np.ndarray],
        seed_idx: int,
        seed_detections: list[SegmentationResult],
    ) -> list[list[Detection]]:
        """Track horses using SAM 2 video propagation."""
        from transformers import Sam2VideoModel, Sam2VideoProcessor

        # Convert frames to RGB PIL images
        pil_frames = [
            Image.fromarray(cv2.cvtColor(f, cv2.COLOR_BGR2RGB))
            for f in frames
        ]

        logger.info("Initializing SAM 2 video session with %d frames...", len(pil_frames))
        video_processor = Sam2VideoProcessor.from_pretrained("facebook/sam2.1-hiera-tiny")
        video_model = Sam2VideoModel.from_pretrained("facebook/sam2.1-hiera-tiny").to(self.device)
        video_model.eval()

        # Initialize video session
        inference_session = video_processor.init_video_session(
            video=pil_frames,
            inference_device=self.device,
        )

        # Add box prompts from seed frame
        horse_boxes = [det.bbox.tolist() for det in seed_detections]
        obj_ids = list(range(1, len(horse_boxes) + 1))

        video_processor.add_inputs_to_inference_session(
            inference_session=inference_session,
            frame_idx=seed_idx,
            obj_ids=obj_ids,
            input_boxes=[horse_boxes],
        )

        # Run on seed frame
        with torch.no_grad():
            video_model(inference_session=inference_session, frame_idx=seed_idx)

        # Propagate through video
        logger.info("Propagating SAM 2 tracking...")
        video_segments: dict[int, dict[int, np.ndarray]] = {}
        h, w = frames[0].shape[:2]

        for sam2_output in video_model.propagate_in_video_iterator(inference_session):
            masks = video_processor.post_process_masks(
                [sam2_output.pred_masks],
                original_sizes=[[h, w]],
                binarize=True,
            )[0]

            frame_masks = {}
            for i, obj_id in enumerate(obj_ids):
                if i < len(masks):
                    frame_masks[obj_id] = masks[i, 0].numpy()
            video_segments[sam2_output.frame_idx] = frame_masks

        logger.info("SAM 2 tracking complete: %d/%d frames have masks", len(video_segments), len(frames))

        # Convert masks to Detection objects
        all_detections: list[list[Detection]] = []
        for fidx in range(len(frames)):
            frame_dets = []
            if fidx in video_segments:
                for obj_id, mask in video_segments[fidx].items():
                    if mask.any():
                        bbox = self._mask_to_bbox(mask)
                        frame_dets.append(Detection(
                            bbox=bbox,
                            confidence=0.9,
                            track_id=obj_id,
                        ))
            all_detections.append(frame_dets)

        tracked_count = sum(1 for dets in all_detections if len(dets) > 0)
        logger.info("SAM 2 tracking: %d/%d frames with detections (%.0f%%)",
                     tracked_count, len(frames), 100 * tracked_count / len(frames))

        return all_detections

    @staticmethod
    def _mask_to_bbox(mask: np.ndarray) -> np.ndarray:
        """Extract bounding box from a binary mask."""
        ys, xs = np.where(mask > 0)
        if len(xs) == 0:
            return np.array([0, 0, 0, 0], dtype=np.float32)
        return np.array([xs.min(), ys.min(), xs.max(), ys.max()], dtype=np.float32)
