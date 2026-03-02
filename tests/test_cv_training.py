"""Tests for training infrastructure: dataset tools, config, active learning."""

import json
import tempfile
from pathlib import Path

import cv2
import numpy as np
import pytest
import yaml

from src.cv.schema import NUM_KEYPOINTS, KEYPOINT_NAMES, FLIP_INDICES, SKELETON_EDGES


# ---------- Dataset format tools ----------

class TestCOCOToYOLO:
    """Test COCO keypoint -> YOLO-Pose format conversion."""

    @pytest.fixture
    def coco_dataset(self, tmp_path):
        """Create a minimal COCO keypoint dataset for testing."""
        images_dir = tmp_path / "images"
        images_dir.mkdir()

        # Create dummy images
        for i in range(3):
            img = np.zeros((480, 640, 3), dtype=np.uint8)
            cv2.imwrite(str(images_dir / f"frame_{i:04d}.jpg"), img)

        # Create COCO annotation JSON
        coco = {
            "images": [
                {"id": i, "file_name": f"frame_{i:04d}.jpg", "width": 640, "height": 480}
                for i in range(3)
            ],
            "categories": [
                {
                    "id": 1,
                    "name": "horse",
                    "keypoints": KEYPOINT_NAMES,
                    "skeleton": [[a + 1, b + 1] for a, b in SKELETON_EDGES],
                }
            ],
            "annotations": [],
        }

        # Add annotations — one horse per image
        for i in range(3):
            kpts = []
            for k in range(NUM_KEYPOINTS):
                x = 200.0 + k * 10
                y = 200.0 + k * 5
                v = 2  # visible
                kpts.extend([x, y, v])

            coco["annotations"].append({
                "id": i,
                "image_id": i,
                "category_id": 1,
                "bbox": [150, 100, 300, 250],  # x, y, w, h
                "keypoints": kpts,
                "num_keypoints": NUM_KEYPOINTS,
            })

        json_path = tmp_path / "annotations.json"
        with open(json_path, "w") as f:
            json.dump(coco, f)

        return json_path, images_dir

    def test_coco_to_yolo_conversion(self, coco_dataset, tmp_path):
        from src.cv.training.dataset import coco_to_yolo_pose

        json_path, images_dir = coco_dataset
        output = tmp_path / "yolo_output"

        coco_to_yolo_pose(json_path, output, image_dir=images_dir)

        # Check output structure
        assert (output / "images").exists()
        assert (output / "labels").exists()

        # Check label files created
        labels = list((output / "labels").glob("*.txt"))
        assert len(labels) == 3

        # Check label format
        with open(labels[0]) as f:
            line = f.readline().strip()
            parts = line.split()
            # class + 4 bbox + 24*3 keypoints = 77
            assert len(parts) == 5 + NUM_KEYPOINTS * 3

            # First value is class ID (0)
            assert parts[0] == "0"

            # Bbox values should be normalized (0-1)
            for v in parts[1:5]:
                val = float(v)
                assert 0 <= val <= 1, f"Bbox value {val} not normalized"

    def test_coco_to_yolo_no_copy(self, coco_dataset, tmp_path):
        from src.cv.training.dataset import coco_to_yolo_pose

        json_path, images_dir = coco_dataset
        output = tmp_path / "yolo_nocopy"

        coco_to_yolo_pose(json_path, output, image_dir=images_dir, copy_images=False)

        # Images should not be copied
        images = list((output / "images").glob("*.jpg"))
        assert len(images) == 0

        # Labels should still be created
        labels = list((output / "labels").glob("*.txt"))
        assert len(labels) == 3


class TestDatasetValidation:
    def test_validate_valid_dataset(self, tmp_path):
        from src.cv.training.dataset import validate_yolo_dataset

        # Create valid dataset
        images = tmp_path / "images"
        labels = tmp_path / "labels"
        images.mkdir()
        labels.mkdir()

        for i in range(5):
            cv2.imwrite(str(images / f"img_{i}.jpg"), np.zeros((100, 100, 3), dtype=np.uint8))
            with open(labels / f"img_{i}.txt", "w") as f:
                # class cx cy w h + 24 keypoints * 3
                parts = ["0", "0.5", "0.5", "0.3", "0.4"]
                parts += ["0.5", "0.5", "2"] * NUM_KEYPOINTS
                f.write(" ".join(parts))

        report = validate_yolo_dataset(tmp_path)
        assert report["valid"]
        assert report["num_images"] == 5
        assert report["num_labels"] == 5
        assert report["num_annotations"] == 5

    def test_validate_missing_labels(self, tmp_path):
        from src.cv.training.dataset import validate_yolo_dataset

        images = tmp_path / "images"
        labels = tmp_path / "labels"
        images.mkdir()
        labels.mkdir()

        cv2.imwrite(str(images / "img_0.jpg"), np.zeros((100, 100, 3), dtype=np.uint8))
        # No label file

        report = validate_yolo_dataset(tmp_path)
        assert not report["valid"]
        assert len(report["missing_labels"]) == 1

    def test_validate_missing_dirs(self, tmp_path):
        from src.cv.training.dataset import validate_yolo_dataset

        report = validate_yolo_dataset(tmp_path)
        assert not report["valid"]


class TestDatasetSplit:
    def test_split_dataset(self, tmp_path):
        from src.cv.training.dataset import split_dataset

        # Create source dataset
        src = tmp_path / "source"
        images = src / "images"
        labels = src / "labels"
        images.mkdir(parents=True)
        labels.mkdir()

        for i in range(20):
            cv2.imwrite(str(images / f"img_{i}.jpg"), np.zeros((100, 100, 3), dtype=np.uint8))
            (labels / f"img_{i}.txt").write_text("0 0.5 0.5 0.3 0.4")

        output = tmp_path / "split"
        counts = split_dataset(src, output, train_ratio=0.7, val_ratio=0.2, test_ratio=0.1)

        assert counts["train"] == 14  # 70%
        assert counts["val"] == 4     # 20%
        assert counts["test"] == 2    # 10%

        # Check directories exist
        assert (output / "train" / "images").exists()
        assert (output / "train" / "labels").exists()
        assert (output / "val" / "images").exists()
        assert (output / "test" / "images").exists()


class TestFrameExtraction:
    @pytest.fixture
    def sample_video(self, tmp_path):
        path = tmp_path / "test.mp4"
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(str(path), fourcc, 30.0, (320, 240))
        for i in range(60):
            frame = np.zeros((240, 320, 3), dtype=np.uint8)
            frame[:, :, 0] = i * 4
            writer.write(frame)
        writer.release()
        return path

    def test_extract_uniform(self, sample_video, tmp_path):
        from src.cv.training.dataset import extract_frames_for_labeling

        output = tmp_path / "frames"
        paths = extract_frames_for_labeling(sample_video, output, num_frames=10, strategy="uniform")
        assert len(paths) == 10
        assert all(p.exists() for p in paths)

    def test_extract_random(self, sample_video, tmp_path):
        from src.cv.training.dataset import extract_frames_for_labeling

        output = tmp_path / "frames"
        paths = extract_frames_for_labeling(sample_video, output, num_frames=10, strategy="random")
        assert len(paths) == 10

    def test_extract_motion(self, sample_video, tmp_path):
        from src.cv.training.dataset import extract_frames_for_labeling

        output = tmp_path / "frames"
        paths = extract_frames_for_labeling(sample_video, output, num_frames=5, strategy="motion")
        assert len(paths) <= 5


# ---------- Training config ----------

class TestTrainingConfig:
    def test_generate_dataset_yaml(self, tmp_path):
        from src.cv.training.config import generate_dataset_yaml

        dataset_dir = tmp_path / "dataset"
        dataset_dir.mkdir()
        (dataset_dir / "train" / "images").mkdir(parents=True)
        (dataset_dir / "val" / "images").mkdir(parents=True)

        yaml_path = generate_dataset_yaml(dataset_dir)
        assert yaml_path.exists()

        with open(yaml_path) as f:
            config = yaml.safe_load(f)

        assert config["names"] == {0: "horse"}
        assert config["kpt_shape"] == [NUM_KEYPOINTS, 3]
        assert len(config["flip_idx"]) == NUM_KEYPOINTS
        assert "train" in config
        assert "val" in config

    def test_hyperparams_finetune(self):
        from src.cv.training.config import get_training_hyperparams

        params = get_training_hyperparams("finetune")
        assert params["epochs"] == 100
        assert params["lr0"] < 0.01  # lower LR for fine-tuning
        assert params["freeze"] == 10  # freeze backbone
        assert params["pose"] == 12.0  # high keypoint loss weight
        assert params["flipud"] == 0.0  # no vertical flip

    def test_hyperparams_scratch(self):
        from src.cv.training.config import get_training_hyperparams

        params = get_training_hyperparams("scratch")
        assert params["epochs"] == 300  # more epochs
        assert params["lr0"] > 0.005   # higher LR

    def test_hyperparams_active_learning(self):
        from src.cv.training.config import get_training_hyperparams

        params = get_training_hyperparams("active_learning")
        assert params["epochs"] == 30   # fewer epochs
        assert params["freeze"] == 15   # freeze more

    def test_hyperparams_invalid_preset(self):
        from src.cv.training.config import get_training_hyperparams

        with pytest.raises(ValueError):
            get_training_hyperparams("nonexistent")

    def test_generate_model_yaml(self, tmp_path):
        from src.cv.training.config import generate_model_yaml

        path = generate_model_yaml(tmp_path / "model.yaml")
        assert path.exists()

        with open(path) as f:
            config = yaml.safe_load(f)

        assert config["nc"] == 1
        assert config["kpt_shape"] == [NUM_KEYPOINTS, 3]


# ---------- Active learning ----------

class TestActiveLearning:
    def test_select_uncertain_low_confidence(self):
        from src.cv.training.active_learning import select_uncertain_frames

        # Create synthetic confidence data: some frames certain, some uncertain
        rng = np.random.default_rng(42)
        conf = rng.uniform(0.7, 0.95, size=(100, NUM_KEYPOINTS)).astype(np.float32)
        # Make a few frames very uncertain
        conf[10] = 0.1
        conf[30] = 0.15
        conf[50] = 0.2
        conf[70] = 0.05

        selected = select_uncertain_frames(conf, n_select=4, strategy="low_confidence")
        assert len(selected) == 4

        # Most uncertain frames should be selected
        selected_indices = {uf.frame_idx for uf in selected}
        assert 70 in selected_indices  # lowest confidence
        assert 10 in selected_indices

    def test_select_uncertain_combined(self):
        from src.cv.training.active_learning import select_uncertain_frames

        rng = np.random.default_rng(42)
        conf = rng.uniform(0.5, 0.9, size=(50, NUM_KEYPOINTS)).astype(np.float32)

        selected = select_uncertain_frames(conf, n_select=10, strategy="combined")
        assert len(selected) <= 10
        assert all(uf.uncertainty_score > 0 for uf in selected)

    def test_select_uncertain_min_spacing(self):
        from src.cv.training.active_learning import select_uncertain_frames

        # All frames equally uncertain — spacing should apply
        conf = np.full((20, NUM_KEYPOINTS), 0.5, dtype=np.float32)
        selected = select_uncertain_frames(conf, n_select=5, strategy="low_confidence")

        # Check minimum spacing between selected frames
        indices = sorted(uf.frame_idx for uf in selected)
        for i in range(1, len(indices)):
            assert indices[i] - indices[i - 1] >= 5

    def test_per_keypoint_accuracy(self):
        from src.cv.training.active_learning import compute_per_keypoint_accuracy

        N, K = 10, NUM_KEYPOINTS
        gt = np.random.rand(N, K, 2) * 100
        preds = gt + np.random.randn(N, K, 2) * 2  # small noise
        vis = np.ones((N, K))

        results = compute_per_keypoint_accuracy(preds, gt, vis, threshold_px=5.0)
        assert len(results) == K
        # With small noise and 5px threshold, most should be >50% correct
        avg_acc = np.mean(list(results.values()))
        assert avg_acc > 50

    def test_oks_computation(self):
        from src.cv.training.active_learning import compute_oks

        N = 5
        K = NUM_KEYPOINTS
        gt = np.random.rand(N, K, 2) * 100
        vis = np.ones((N, K))
        areas = np.full(N, 10000.0)

        # Perfect predictions
        oks_perfect = compute_oks(gt, gt, vis, areas)
        np.testing.assert_allclose(oks_perfect, 1.0, atol=1e-5)

        # Very wrong predictions
        preds_bad = gt + 500
        oks_bad = compute_oks(preds_bad, gt, vis, areas)
        assert np.all(oks_bad < 0.1)
