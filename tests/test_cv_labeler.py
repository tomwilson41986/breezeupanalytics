"""Tests for the web-based keypoint labeler."""

from pathlib import Path

import cv2
import numpy as np
import pytest

from src.cv.schema import NUM_KEYPOINTS
from src.cv.training.labeler import (
    _list_images,
    _load_yolo_label,
    _save_yolo_label,
    _get_project_stats,
    _set_project,
    app,
)


# ---------- Helpers ----------

def _make_test_images(directory: Path, count: int = 3) -> list[Path]:
    directory.mkdir(parents=True, exist_ok=True)
    paths = []
    for i in range(count):
        img = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
        p = directory / f"frame_{i:04d}.jpg"
        cv2.imwrite(str(p), img)
        paths.append(p)
    return paths


def _make_full_annotation(img_w=640, img_h=480):
    """Create a test annotation with all keypoints placed."""
    kps = []
    for i in range(NUM_KEYPOINTS):
        kps.append({
            "x": 100 + i * 20,
            "y": 200 + i * 10,
            "visibility": 2,
        })
    return {
        "bbox": [50, 100, 550, 420],
        "keypoints": kps,
    }


# ---------- File listing ----------

class TestListImages:
    def test_lists_jpg_files(self, tmp_path):
        _make_test_images(tmp_path, 5)
        files = _list_images(tmp_path)
        assert len(files) == 5
        assert all(f.suffix == ".jpg" for f in files)

    def test_sorted_order(self, tmp_path):
        _make_test_images(tmp_path, 3)
        files = _list_images(tmp_path)
        names = [f.name for f in files]
        assert names == sorted(names)

    def test_empty_directory(self, tmp_path):
        files = _list_images(tmp_path)
        assert files == []

    def test_ignores_non_image_files(self, tmp_path):
        _make_test_images(tmp_path, 2)
        (tmp_path / "readme.txt").write_text("not an image")
        (tmp_path / "data.json").write_text("{}")
        files = _list_images(tmp_path)
        assert len(files) == 2


# ---------- YOLO label I/O ----------

class TestYOLOLabelIO:
    def test_save_and_load_roundtrip(self, tmp_path):
        label_path = tmp_path / "test.txt"
        ann = _make_full_annotation()

        _save_yolo_label(label_path, [ann], 640, 480)
        loaded = _load_yolo_label(label_path, 640, 480)

        assert len(loaded) == 1
        for i in range(NUM_KEYPOINTS):
            assert abs(loaded[0]["keypoints"][i]["x"] - ann["keypoints"][i]["x"]) < 1
            assert abs(loaded[0]["keypoints"][i]["y"] - ann["keypoints"][i]["y"]) < 1
            assert loaded[0]["keypoints"][i]["visibility"] == 2

    def test_save_creates_parent_dirs(self, tmp_path):
        label_path = tmp_path / "sub" / "dir" / "test.txt"
        ann = _make_full_annotation()
        _save_yolo_label(label_path, [ann], 640, 480)
        assert label_path.exists()

    def test_load_nonexistent_returns_empty(self, tmp_path):
        result = _load_yolo_label(tmp_path / "nonexistent.txt", 640, 480)
        assert result == []

    def test_load_empty_file_returns_empty(self, tmp_path):
        label_path = tmp_path / "empty.txt"
        label_path.write_text("")
        result = _load_yolo_label(label_path, 640, 480)
        assert result == []

    def test_multiple_annotations(self, tmp_path):
        label_path = tmp_path / "multi.txt"
        anns = [_make_full_annotation(), _make_full_annotation()]
        # Shift second annotation
        for kp in anns[1]["keypoints"]:
            kp["x"] += 100
        anns[1]["bbox"] = [150, 100, 600, 420]

        _save_yolo_label(label_path, anns, 640, 480)
        loaded = _load_yolo_label(label_path, 640, 480)

        assert len(loaded) == 2

    def test_visibility_preserved(self, tmp_path):
        label_path = tmp_path / "vis.txt"
        ann = _make_full_annotation()
        ann["keypoints"][0]["visibility"] = 2  # visible
        ann["keypoints"][1]["visibility"] = 1  # occluded
        ann["keypoints"][2]["visibility"] = 0  # not labeled

        _save_yolo_label(label_path, [ann], 640, 480)
        loaded = _load_yolo_label(label_path, 640, 480)

        assert loaded[0]["keypoints"][0]["visibility"] == 2
        assert loaded[0]["keypoints"][1]["visibility"] == 1
        assert loaded[0]["keypoints"][2]["visibility"] == 0

    def test_bbox_roundtrip(self, tmp_path):
        label_path = tmp_path / "bbox.txt"
        ann = _make_full_annotation()
        ann["bbox"] = [100, 80, 500, 400]

        _save_yolo_label(label_path, [ann], 640, 480)
        loaded = _load_yolo_label(label_path, 640, 480)

        for i in range(4):
            assert abs(loaded[0]["bbox"][i] - ann["bbox"][i]) < 2


# ---------- Project helpers ----------

class TestProjectHelpers:
    def test_get_project_stats(self, tmp_path):
        project_dir = tmp_path / "my_project"
        images_dir = project_dir / "images"
        labels_dir = project_dir / "labels"
        _make_test_images(images_dir, 5)
        labels_dir.mkdir(parents=True)

        # Create 2 non-empty label files
        ann = _make_full_annotation()
        _save_yolo_label(labels_dir / "frame_0000.txt", [ann], 640, 480)
        _save_yolo_label(labels_dir / "frame_0001.txt", [ann], 640, 480)
        # One empty label
        (labels_dir / "frame_0002.txt").write_text("")

        stats = _get_project_stats(project_dir)
        assert stats["name"] == "my_project"
        assert stats["total_frames"] == 5
        assert stats["labeled_frames"] == 2

    def test_get_project_stats_no_images(self, tmp_path):
        project_dir = tmp_path / "empty_project"
        (project_dir / "images").mkdir(parents=True)
        (project_dir / "labels").mkdir(parents=True)

        stats = _get_project_stats(project_dir)
        assert stats["total_frames"] == 0
        assert stats["labeled_frames"] == 0

    def test_set_project(self, tmp_path):
        from src.cv.training.labeler import _STATE
        _STATE["data_root"] = str(tmp_path)

        # Create project with images
        images_dir = tmp_path / "test_proj" / "images"
        _make_test_images(images_dir, 4)

        _set_project("test_proj")

        assert _STATE["project"] == "test_proj"
        assert _STATE["images_dir"] == str(images_dir)
        assert len(_STATE["image_files"]) == 4


# ---------- Flask API tests ----------

class TestFlaskAPI:
    @pytest.fixture
    def client(self, tmp_path):
        from src.cv.training.labeler import _STATE
        images_dir = tmp_path / "images"
        labels_dir = tmp_path / "labels"
        _make_test_images(images_dir, 3)
        labels_dir.mkdir()

        _STATE["images_dir"] = str(images_dir)
        _STATE["labels_dir"] = str(labels_dir)
        _STATE["image_files"] = _list_images(images_dir)
        _STATE["project"] = "test"
        _STATE["data_root"] = str(tmp_path)

        app.config["TESTING"] = True
        with app.test_client() as c:
            yield c

    def test_index_returns_html(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert b"Equine Keypoint Labeler" in resp.data

    def test_api_images(self, client):
        resp = client.get("/api/images")
        data = resp.get_json()
        assert data["total"] == 3
        assert len(data["images"]) == 3
        assert data["project"] == "test"

    def test_api_schema(self, client):
        resp = client.get("/api/schema")
        data = resp.get_json()
        assert data["num_keypoints"] == NUM_KEYPOINTS
        assert len(data["names"]) == NUM_KEYPOINTS
        assert len(data["skeleton"]) > 0
        assert len(data["colors"]) == NUM_KEYPOINTS

    def test_api_annotation_empty(self, client):
        resp = client.get("/api/annotation/frame_0000.jpg")
        data = resp.get_json()
        assert data["annotations"] == []
        assert data["img_w"] > 0
        assert data["img_h"] > 0

    def test_api_save_and_load(self, client):
        ann = _make_full_annotation()
        save_resp = client.post("/api/save", json={
            "filename": "frame_0000.jpg",
            "annotations": [ann],
            "img_w": 640,
            "img_h": 480,
        })
        assert save_resp.get_json()["status"] == "saved"

        load_resp = client.get("/api/annotation/frame_0000.jpg")
        data = load_resp.get_json()
        assert len(data["annotations"]) == 1
        assert data["annotations"][0]["keypoints"][0]["visibility"] == 2

    def test_api_projects(self, client, tmp_path):
        from src.cv.training.labeler import _STATE
        # Create a project structure in data_root
        project_dir = tmp_path / "my_project" / "images"
        _make_test_images(project_dir, 2)

        resp = client.get("/api/projects")
        data = resp.get_json()
        assert "projects" in data
        assert "data_root" in data
        # Should find our created project
        names = [p["name"] for p in data["projects"]]
        assert "my_project" in names

    def test_api_open_project(self, client, tmp_path):
        # Create a project
        project_dir = tmp_path / "open_test" / "images"
        _make_test_images(project_dir, 4)

        resp = client.get("/api/open_project/open_test")
        data = resp.get_json()
        assert data["status"] == "opened"
        assert data["project"] == "open_test"
        assert data["total_frames"] == 4

    def test_api_open_nonexistent_project(self, client):
        resp = client.get("/api/open_project/nonexistent_xyz")
        assert resp.status_code == 404
        data = resp.get_json()
        assert "error" in data
