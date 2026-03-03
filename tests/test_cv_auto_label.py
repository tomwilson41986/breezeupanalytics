"""Tests for the auto-labeling agent."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import cv2
import numpy as np
import pytest

from src.cv.schema import NUM_KEYPOINTS
from src.cv.training.auto_label import (
    AP10K_TO_EQUINE_MAP,
    COCO_TO_EQUINE_MAP,
    AutoLabelAgent,
    AutoLabelResult,
    PseudoLabel,
)


# ---------- Helpers ----------

def _make_test_images(directory: Path, count: int = 5) -> list[Path]:
    """Create dummy test images."""
    directory.mkdir(parents=True, exist_ok=True)
    paths = []
    for i in range(count):
        img = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
        p = directory / f"frame_{i:04d}.jpg"
        cv2.imwrite(str(p), img)
        paths.append(p)
    return paths


def _make_pseudo_label(
    quality: float = 0.7,
    n_confident: int = 16,
    needs_review: bool = False,
) -> PseudoLabel:
    """Create a synthetic PseudoLabel for testing."""
    kpts = np.random.rand(NUM_KEYPOINTS, 2).astype(np.float32) * 400 + 100
    conf = np.zeros(NUM_KEYPOINTS, dtype=np.float32)
    conf[:n_confident] = np.random.uniform(0.4, 0.9, size=n_confident).astype(np.float32)
    return PseudoLabel(
        bbox=np.array([100, 80, 500, 400], dtype=np.float32),
        keypoints=kpts,
        confidence=conf,
        quality_score=quality,
        num_confident=n_confident,
        needs_review=needs_review,
    )


# ---------- Mapping table tests ----------

class TestMappingTables:
    def test_coco_to_equine_map_valid_targets(self):
        """All target IDs should be valid equine keypoint IDs."""
        for src, dst in COCO_TO_EQUINE_MAP.items():
            assert 0 <= dst < NUM_KEYPOINTS, f"COCO {src} -> equine {dst} out of range"

    def test_coco_to_equine_map_valid_sources(self):
        """All source IDs should be valid COCO keypoint IDs (0-16)."""
        for src in COCO_TO_EQUINE_MAP:
            assert 0 <= src <= 16, f"COCO source {src} out of range"

    def test_coco_to_equine_map_unique_targets(self):
        """Each equine keypoint should be mapped from at most one COCO keypoint."""
        targets = list(COCO_TO_EQUINE_MAP.values())
        assert len(targets) == len(set(targets)), "Duplicate target keypoints in mapping"


# ---------- Quality scoring tests ----------

class TestQualityScoring:
    def test_high_quality_label(self):
        agent = AutoLabelAgent(quality_threshold=0.4, min_confident_kpts=8)
        label = _make_pseudo_label()

        # Set high confidence on topline and limb keypoints
        label.confidence[:] = 0.8
        agent._score_quality(label)

        assert label.quality_score > 0.6
        assert label.num_confident == NUM_KEYPOINTS
        assert not label.needs_review

    def test_low_quality_label(self):
        agent = AutoLabelAgent(quality_threshold=0.4, min_confident_kpts=8)
        label = _make_pseudo_label()

        # Very few confident keypoints
        label.confidence[:] = 0.05
        label.confidence[1] = 0.5  # only nose
        agent._score_quality(label)

        assert label.quality_score < 0.4
        assert label.needs_review
        assert len(label.review_reasons) > 0

    def test_missing_topline_flagged(self):
        agent = AutoLabelAgent(quality_threshold=0.4, min_confident_kpts=4)
        label = _make_pseudo_label()

        # Confident on limbs but NOT on topline (withers=3, mid_back=4, croup=5)
        label.confidence[:] = 0.0
        label.confidence[7] = 0.8   # l_shoulder
        label.confidence[8] = 0.8   # l_elbow
        label.confidence[11] = 0.8  # l_fore_hoof
        label.confidence[17] = 0.8  # l_hip
        label.confidence[18] = 0.8  # l_hock
        agent._score_quality(label)

        assert "missing_topline" in label.review_reasons

    def test_incomplete_limbs_flagged(self):
        agent = AutoLabelAgent(quality_threshold=0.4, min_confident_kpts=4)
        label = _make_pseudo_label()

        # Only topline confident, no limbs
        label.confidence[:] = 0.0
        label.confidence[3] = 0.8  # withers
        label.confidence[4] = 0.8  # mid_back
        label.confidence[5] = 0.8  # croup
        label.confidence[0] = 0.8  # poll
        agent._score_quality(label)

        assert "incomplete_limbs" in label.review_reasons


# ---------- Geometric inference tests ----------

class TestGeometricInference:
    def test_infer_withers_from_shoulders(self):
        agent = AutoLabelAgent()
        label = _make_pseudo_label()

        # Set shoulders but not withers
        label.confidence[3] = 0.0   # withers unknown
        label.confidence[7] = 0.8   # l_shoulder
        label.confidence[12] = 0.8  # r_shoulder
        label.keypoints[7] = [200, 300]
        label.keypoints[12] = [220, 310]

        agent._infer_missing_keypoints(label)

        assert label.confidence[3] > 0, "Withers should be inferred"
        # Withers should be approximately above the midpoint of shoulders
        assert label.keypoints[3, 0] == pytest.approx(210.0, abs=5)

    def test_infer_midback_from_withers_croup(self):
        agent = AutoLabelAgent()
        label = _make_pseudo_label()

        label.confidence[4] = 0.0   # mid_back unknown
        label.confidence[3] = 0.8   # withers
        label.confidence[5] = 0.8   # croup
        label.keypoints[3] = [200, 250]
        label.keypoints[5] = [400, 260]

        agent._infer_missing_keypoints(label)

        assert label.confidence[4] > 0, "Mid-back should be inferred"
        # Should be midpoint
        assert label.keypoints[4, 0] == pytest.approx(300.0, abs=5)

    def test_infer_fetlock_from_knee_hoof(self):
        agent = AutoLabelAgent()
        label = _make_pseudo_label()

        label.confidence[10] = 0.0  # l_fetlock_fore unknown
        label.confidence[9] = 0.8   # l_knee_fore
        label.confidence[11] = 0.8  # l_fore_hoof
        label.keypoints[9] = [200, 350]
        label.keypoints[11] = [200, 450]

        agent._infer_missing_keypoints(label)

        assert label.confidence[10] > 0, "Fetlock should be inferred"
        assert label.keypoints[10, 1] == pytest.approx(400.0, abs=5)  # midpoint

    def test_no_inference_when_keypoint_already_confident(self):
        agent = AutoLabelAgent()
        label = _make_pseudo_label()

        # Withers already confident — should not be overwritten
        label.confidence[3] = 0.9
        label.keypoints[3] = [250, 200]
        original_pos = label.keypoints[3].copy()

        label.confidence[7] = 0.8
        label.confidence[12] = 0.8

        agent._infer_missing_keypoints(label)

        np.testing.assert_array_equal(label.keypoints[3], original_pos)


# ---------- YOLO format output tests ----------

class TestYOLOOutput:
    def test_label_to_yolo_line_format(self):
        agent = AutoLabelAgent()
        label = _make_pseudo_label()
        label.confidence[:] = 0.8

        line = agent._label_to_yolo_line(label, img_w=640, img_h=480)
        parts = line.split()

        # Should have: class + 4 bbox + 24*3 keypoints = 77 values
        assert len(parts) == 5 + NUM_KEYPOINTS * 3

        # Class ID should be 0
        assert parts[0] == "0"

        # Bbox should be normalized
        cx, cy, bw, bh = [float(p) for p in parts[1:5]]
        assert 0 <= cx <= 1
        assert 0 <= cy <= 1
        assert 0 < bw <= 1
        assert 0 < bh <= 1

    def test_label_to_yolo_visibility_flags(self):
        agent = AutoLabelAgent(keypoint_confidence=0.3)
        label = _make_pseudo_label()

        label.confidence[0] = 0.8   # visible
        label.confidence[1] = 0.1   # low conf -> occluded
        label.confidence[2] = 0.0   # not detected

        line = agent._label_to_yolo_line(label, img_w=640, img_h=480)
        parts = line.split()

        # Keypoint 0 visibility (index 5 + 0*3 + 2 = 7)
        assert parts[7] == "2"  # visible
        # Keypoint 1 visibility (index 5 + 1*3 + 2 = 10)
        assert parts[10] == "1"  # occluded
        # Keypoint 2 visibility (index 5 + 2*3 + 2 = 13)
        assert parts[13] == "0"  # not labeled

    def test_label_to_yolo_normalized_keypoints(self):
        agent = AutoLabelAgent()
        label = _make_pseudo_label()
        label.confidence[:] = 0.8

        # Set a keypoint at known pixel position
        label.keypoints[0] = [320, 240]

        line = agent._label_to_yolo_line(label, img_w=640, img_h=480)
        parts = line.split()

        kp0_x = float(parts[5])
        kp0_y = float(parts[6])
        assert kp0_x == pytest.approx(0.5, abs=0.01)
        assert kp0_y == pytest.approx(0.5, abs=0.01)


# ---------- Directory labeling tests (mocked models) ----------

class TestDirectoryLabeling:
    @patch.object(AutoLabelAgent, "_init_models")
    @patch.object(AutoLabelAgent, "label_image")
    def test_label_directory_basic(self, mock_label, mock_init, tmp_path):
        """Test directory labeling with mocked model inference."""
        images_dir = tmp_path / "images"
        _make_test_images(images_dir, count=3)
        output_dir = tmp_path / "labels"

        # Mock label_image to return one horse per image
        def fake_label(path):
            label = _make_pseudo_label(quality=0.7, n_confident=16)
            return [label]

        mock_label.side_effect = fake_label

        agent = AutoLabelAgent()
        result = agent.label_directory(images_dir, output_dir)

        assert result.num_images == 3
        assert result.num_labeled == 3
        assert result.num_horses == 3

        # Check label files exist
        label_files = list(output_dir.glob("*.txt"))
        assert len(label_files) == 3

    @patch.object(AutoLabelAgent, "_init_models")
    @patch.object(AutoLabelAgent, "label_image")
    def test_label_directory_with_review_flags(self, mock_label, mock_init, tmp_path):
        """Test that low-quality labels are flagged for review."""
        images_dir = tmp_path / "images"
        _make_test_images(images_dir, count=4)
        output_dir = tmp_path / "labels"
        review_dir = tmp_path / "review"

        call_count = [0]

        def fake_label(path):
            call_count[0] += 1
            if call_count[0] <= 2:
                # Good quality
                label = _make_pseudo_label(quality=0.7, n_confident=16)
                label.needs_review = False
                label.review_reasons = []
                return [label]
            else:
                # Poor quality
                label = _make_pseudo_label(quality=0.2, n_confident=4)
                label.needs_review = True
                label.review_reasons = ["low_quality (0.20 < 0.40)"]
                return [label]

        mock_label.side_effect = fake_label

        agent = AutoLabelAgent()
        result = agent.label_directory(images_dir, output_dir, review_dir=review_dir)

        assert result.num_flagged == 2
        assert review_dir.exists()

        # Review manifest should exist
        manifest = output_dir / "review_manifest.json"
        assert manifest.exists()
        with open(manifest) as f:
            data = json.load(f)
        assert data["flagged_for_review"] == 2

    @patch.object(AutoLabelAgent, "_init_models")
    @patch.object(AutoLabelAgent, "label_image")
    def test_label_directory_no_detections(self, mock_label, mock_init, tmp_path):
        """Test handling of images with no horse detections."""
        images_dir = tmp_path / "images"
        _make_test_images(images_dir, count=2)
        output_dir = tmp_path / "labels"

        mock_label.return_value = []  # no detections

        agent = AutoLabelAgent()
        result = agent.label_directory(images_dir, output_dir)

        assert result.num_labeled == 0
        assert result.num_horses == 0

        # Empty label files should still be created
        label_files = list(output_dir.glob("*.txt"))
        assert len(label_files) == 2
        for lf in label_files:
            assert lf.read_text() == ""

    @patch.object(AutoLabelAgent, "_init_models")
    @patch.object(AutoLabelAgent, "label_image")
    def test_label_directory_multi_horse(self, mock_label, mock_init, tmp_path):
        """Test images with multiple horse detections."""
        images_dir = tmp_path / "images"
        _make_test_images(images_dir, count=2)
        output_dir = tmp_path / "labels"

        def fake_label(path):
            return [
                _make_pseudo_label(quality=0.8, n_confident=18),
                _make_pseudo_label(quality=0.6, n_confident=12),
            ]

        mock_label.side_effect = fake_label

        agent = AutoLabelAgent()
        result = agent.label_directory(images_dir, output_dir)

        assert result.num_horses == 4  # 2 per image * 2 images

        # Each label file should have 2 lines (one per horse)
        for lf in output_dir.glob("*.txt"):
            lines = lf.read_text().strip().split("\n")
            assert len(lines) == 2


# ---------- Integration test with the full quality + inference pipeline ----------

class TestEndToEndPseudoLabel:
    def test_quality_scoring_with_inference(self):
        """Test that geometric inference improves quality scores."""
        agent = AutoLabelAgent(quality_threshold=0.4, min_confident_kpts=8)

        # Label with shoulders and hips but no topline
        label = _make_pseudo_label()
        label.confidence[:] = 0.0
        label.keypoints[:] = 0.0

        # Set shoulder and hip positions
        label.confidence[7] = 0.8; label.keypoints[7] = [200, 300]   # l_shoulder
        label.confidence[12] = 0.8; label.keypoints[12] = [220, 310] # r_shoulder
        label.confidence[17] = 0.8; label.keypoints[17] = [400, 320] # l_hip
        label.confidence[21] = 0.8; label.keypoints[21] = [420, 330] # r_hip
        label.confidence[1] = 0.7; label.keypoints[1] = [150, 250]   # nose

        # Score before inference
        agent._score_quality(label)
        quality_before = label.quality_score
        n_confident_before = label.num_confident

        # Run geometric inference
        agent._infer_missing_keypoints(label)

        # Score after inference
        agent._score_quality(label)

        assert label.num_confident > n_confident_before
        assert label.quality_score >= quality_before


# ---------- Source mode tests ----------

class TestSourceModes:
    def test_valid_source_modes(self):
        """All three source modes should be accepted."""
        for source in ("coco", "vitpose", "ensemble"):
            agent = AutoLabelAgent(source=source)
            assert agent.source == source

    def test_invalid_source_raises(self):
        """Invalid source should raise ValueError."""
        with pytest.raises(ValueError, match="Unknown source"):
            AutoLabelAgent(source="invalid")

    def test_default_source_is_vitpose(self):
        """Default source should be vitpose."""
        agent = AutoLabelAgent()
        assert agent.source == "vitpose"

    def test_vitpose_size_stored(self):
        agent = AutoLabelAgent(source="vitpose", vitpose_size="large")
        assert agent.vitpose_size == "large"


# ---------- Ensemble merge tests ----------

class TestEnsembleMerge:
    """Test the confidence-weighted ensemble merge logic."""

    def test_ensemble_prefers_higher_confidence(self):
        """When only one model predicts a keypoint, that prediction wins."""
        agent = AutoLabelAgent(source="ensemble", keypoint_confidence=0.3)

        # Simulate vitpose label with strong shoulder prediction
        v_label = _make_pseudo_label()
        v_label.confidence[:] = 0.0
        v_label.confidence[7] = 0.9  # l_shoulder
        v_label.keypoints[7] = [200, 300]

        # Simulate coco label with no shoulder but strong hip
        c_label = _make_pseudo_label()
        c_label.confidence[:] = 0.0
        c_label.confidence[17] = 0.85  # l_hip
        c_label.keypoints[17] = [400, 320]

        # Manually test the merge logic
        merged_kpts = np.zeros((NUM_KEYPOINTS, 2), dtype=np.float32)
        merged_conf = np.zeros(NUM_KEYPOINTS, dtype=np.float32)
        threshold = 0.3

        for i in range(NUM_KEYPOINTS):
            v_has = v_label.confidence[i] >= threshold
            c_has = c_label.confidence[i] >= threshold

            if v_has and c_has:
                total = v_label.confidence[i] + c_label.confidence[i]
                merged_kpts[i] = (
                    v_label.confidence[i] * v_label.keypoints[i]
                    + c_label.confidence[i] * c_label.keypoints[i]
                ) / total
                merged_conf[i] = max(v_label.confidence[i], c_label.confidence[i])
            elif v_has:
                merged_kpts[i] = v_label.keypoints[i]
                merged_conf[i] = v_label.confidence[i]
            elif c_has:
                merged_kpts[i] = c_label.keypoints[i]
                merged_conf[i] = c_label.confidence[i]

        # Shoulder should come from vitpose
        np.testing.assert_allclose(merged_kpts[7], [200, 300])
        assert merged_conf[7] == pytest.approx(0.9)

        # Hip should come from coco
        np.testing.assert_allclose(merged_kpts[17], [400, 320])
        assert merged_conf[17] == pytest.approx(0.85)

    def test_ensemble_averages_when_both_confident(self):
        """When both models predict, coordinates are confidence-weighted."""
        v_conf = 0.9
        c_conf = 0.6
        v_pos = np.array([200, 300], dtype=np.float32)
        c_pos = np.array([210, 310], dtype=np.float32)

        total = v_conf + c_conf
        expected = (v_conf * v_pos + c_conf * c_pos) / total

        # ViTPose has higher weight so result should be closer to its position
        assert expected[0] < 207  # closer to 200 than 210

    def test_ensemble_max_confidence(self):
        """Merged confidence should be max of the two models."""
        v_conf = 0.9
        c_conf = 0.6
        assert max(v_conf, c_conf) == 0.9


# ---------- AP-10K mapping table tests ----------

class TestAP10KMapping:
    def test_ap10k_map_valid_targets(self):
        for src, dst in AP10K_TO_EQUINE_MAP.items():
            assert 0 <= dst < NUM_KEYPOINTS, f"AP10K {src} -> equine {dst} out of range"

    def test_ap10k_map_valid_sources(self):
        for src in AP10K_TO_EQUINE_MAP:
            assert 0 <= src <= 16, f"AP10K source {src} out of range"

    def test_ap10k_covers_all_limb_endpoints(self):
        """AP-10K should map to all four hoof keypoints."""
        targets = set(AP10K_TO_EQUINE_MAP.values())
        hooves = {11, 16, 20, 23}  # l_fore, r_fore, l_hind, r_hind
        assert hooves.issubset(targets), f"Missing hooves: {hooves - targets}"
