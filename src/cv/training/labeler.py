"""Web-based GUI for equine keypoint annotation.

Full workflow:
1. Upload a video (or point to existing frames)
2. Extract frames automatically
3. Optionally auto-label with ViTPose for a head start
4. Manually correct/place keypoints in the browser
5. Labels saved in YOLO-Pose format to data/training/<project>/labels/

Usage:
    python -m src.cv.training.labeler              # launches on port 5000
    python -m src.cv.training.labeler --port 8080   # custom port

All projects live under data/training/. After labelling:
    equine-train split data/training/<project> -o data/training/<project>_split
    equine-train train data/training/<project>_split
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import threading
from pathlib import Path

import cv2
import numpy as np
from flask import Flask, Response, jsonify, request, send_from_directory

from src.cv.schema import (
    EQUINE_KEYPOINTS,
    KEYPOINT_COLORS,
    KEYPOINT_NAMES,
    LIMB_GROUPS,
    NUM_KEYPOINTS,
    SKELETON_EDGES,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Flask app
# ---------------------------------------------------------------------------

app = Flask(__name__)

# Base directory for all training data
_DATA_ROOT = Path("data/training")

# Global state
_STATE: dict = {
    "images_dir": "",
    "labels_dir": "",
    "image_files": [],
    "project": "",
    "data_root": str(_DATA_ROOT),
}


def _list_images(directory: Path) -> list[Path]:
    """List image files sorted by name."""
    paths = []
    for ext in ("*.jpg", "*.jpeg", "*.png", "*.bmp"):
        paths.extend(directory.glob(ext))
    return sorted(paths)


def _load_yolo_label(label_path: Path, img_w: int, img_h: int) -> list[dict]:
    """Load a YOLO-Pose label file and denormalize coordinates."""
    if not label_path.exists():
        return []

    text = label_path.read_text().strip()
    if not text:
        return []

    annotations = []
    for line in text.split("\n"):
        parts = line.strip().split()
        if len(parts) < 5:
            continue

        cx, cy, bw, bh = float(parts[1]), float(parts[2]), float(parts[3]), float(parts[4])
        x1 = (cx - bw / 2) * img_w
        y1 = (cy - bh / 2) * img_h
        x2 = (cx + bw / 2) * img_w
        y2 = (cy + bh / 2) * img_h

        keypoints = []
        kpt_values = parts[5:]
        for k in range(NUM_KEYPOINTS):
            idx = k * 3
            if idx + 2 < len(kpt_values):
                kx = float(kpt_values[idx]) * img_w
                ky = float(kpt_values[idx + 1]) * img_h
                vis = int(kpt_values[idx + 2])
            else:
                kx, ky, vis = 0.0, 0.0, 0
            keypoints.append({"x": kx, "y": ky, "visibility": vis})

        annotations.append({
            "bbox": [x1, y1, x2, y2],
            "keypoints": keypoints,
        })

    return annotations


def _save_yolo_label(label_path: Path, annotations: list[dict], img_w: int, img_h: int) -> None:
    """Save annotations in YOLO-Pose format."""
    label_path.parent.mkdir(parents=True, exist_ok=True)

    lines = []
    for ann in annotations:
        bbox = ann["bbox"]
        x1, y1, x2, y2 = bbox[0], bbox[1], bbox[2], bbox[3]
        cx = ((x1 + x2) / 2) / img_w
        cy = ((y1 + y2) / 2) / img_h
        bw = (x2 - x1) / img_w
        bh = (y2 - y1) / img_h

        parts = [f"0 {cx:.6f} {cy:.6f} {bw:.6f} {bh:.6f}"]

        for kp in ann["keypoints"]:
            kx = kp["x"] / img_w
            ky = kp["y"] / img_h
            vis = kp["visibility"]
            parts.append(f"{kx:.6f} {ky:.6f} {vis}")

        lines.append(" ".join(parts))

    label_path.write_text("\n".join(lines))


def _set_project(project_name: str) -> None:
    """Switch active project."""
    project_dir = Path(_STATE["data_root"]) / project_name
    images_dir = project_dir / "images"
    labels_dir = project_dir / "labels"

    images_dir.mkdir(parents=True, exist_ok=True)
    labels_dir.mkdir(parents=True, exist_ok=True)

    _STATE["project"] = project_name
    _STATE["images_dir"] = str(images_dir)
    _STATE["labels_dir"] = str(labels_dir)
    _STATE["image_files"] = _list_images(images_dir)


def _get_project_stats(project_dir: Path) -> dict:
    """Get stats for a project directory."""
    images_dir = project_dir / "images"
    labels_dir = project_dir / "labels"

    image_files = _list_images(images_dir) if images_dir.exists() else []
    label_files = list(labels_dir.glob("*.txt")) if labels_dir.exists() else []

    # Count non-empty labels (frames with actual annotations)
    labeled = 0
    for lf in label_files:
        text = lf.read_text().strip()
        if text:
            labeled += 1

    return {
        "name": project_dir.name,
        "total_frames": len(image_files),
        "labeled_frames": labeled,
        "path": str(project_dir),
    }


# ---------------------------------------------------------------------------
# API routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    """Serve the main UI."""
    return _LABELER_HTML


@app.route("/api/projects")
def api_projects():
    """List all projects in data/training/."""
    data_root = Path(_STATE["data_root"])
    data_root.mkdir(parents=True, exist_ok=True)

    projects = []
    for d in sorted(data_root.iterdir()):
        if d.is_dir() and (d / "images").exists():
            projects.append(_get_project_stats(d))

    return jsonify({
        "projects": projects,
        "data_root": str(data_root.resolve()),
        "active": _STATE["project"],
    })


@app.route("/api/open_project/<name>")
def api_open_project(name: str):
    """Open an existing project."""
    project_dir = Path(_STATE["data_root"]) / name
    if not project_dir.exists():
        return jsonify({"error": "Project not found"}), 404

    _set_project(name)
    return jsonify({
        "status": "opened",
        "project": name,
        "total_frames": len(_STATE["image_files"]),
    })


@app.route("/api/upload_video", methods=["POST"])
def api_upload_video():
    """Upload a video and extract frames into a new project."""
    if "video" not in request.files:
        return jsonify({"error": "No video file provided"}), 400

    video_file = request.files["video"]
    project_name = request.form.get("project_name", "").strip()
    num_frames = int(request.form.get("num_frames", 50))
    strategy = request.form.get("strategy", "uniform")

    if not project_name:
        project_name = Path(video_file.filename or "video").stem

    # Sanitize project name
    project_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in project_name)

    data_root = Path(_STATE["data_root"])
    project_dir = data_root / project_name
    videos_dir = project_dir / "videos"
    images_dir = project_dir / "images"
    labels_dir = project_dir / "labels"

    for d in [videos_dir, images_dir, labels_dir]:
        d.mkdir(parents=True, exist_ok=True)

    # Save uploaded video
    video_path = videos_dir / (video_file.filename or "upload.mp4")
    video_file.save(str(video_path))

    # Extract frames
    from src.cv.training.dataset import extract_frames_for_labeling
    frames = extract_frames_for_labeling(
        video_path, output_dir=images_dir,
        num_frames=num_frames, strategy=strategy,
    )

    _set_project(project_name)

    return jsonify({
        "status": "created",
        "project": project_name,
        "video": str(video_path),
        "frames_extracted": len(frames),
        "images_dir": str(images_dir.resolve()),
        "labels_dir": str(labels_dir.resolve()),
    })


@app.route("/api/import_video", methods=["POST"])
def api_import_video():
    """Import a video from a local path (no upload needed)."""
    data = request.get_json()
    video_path = data.get("video_path", "")
    project_name = data.get("project_name", "")
    num_frames = int(data.get("num_frames", 50))
    strategy = data.get("strategy", "uniform")

    if not video_path or not Path(video_path).exists():
        return jsonify({"error": f"Video not found: {video_path}"}), 400

    if not project_name:
        project_name = Path(video_path).stem

    project_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in project_name)

    data_root = Path(_STATE["data_root"])
    project_dir = data_root / project_name
    images_dir = project_dir / "images"
    labels_dir = project_dir / "labels"

    for d in [images_dir, labels_dir]:
        d.mkdir(parents=True, exist_ok=True)

    from src.cv.training.dataset import extract_frames_for_labeling
    frames = extract_frames_for_labeling(
        video_path, output_dir=images_dir,
        num_frames=num_frames, strategy=strategy,
    )

    _set_project(project_name)

    return jsonify({
        "status": "created",
        "project": project_name,
        "frames_extracted": len(frames),
        "images_dir": str(images_dir.resolve()),
        "labels_dir": str(labels_dir.resolve()),
    })


@app.route("/api/images")
def api_images():
    """List all available images in the active project."""
    files = _STATE["image_files"]
    return jsonify({
        "images": [f.name for f in files],
        "total": len(files),
        "project": _STATE["project"],
    })


@app.route("/api/image/<filename>")
def api_image(filename: str):
    """Serve an image file."""
    return send_from_directory(_STATE["images_dir"], filename)


@app.route("/api/annotation/<filename>")
def api_annotation(filename: str):
    """Load existing annotation for an image."""
    stem = Path(filename).stem
    label_path = Path(_STATE["labels_dir"]) / f"{stem}.txt"

    img_path = Path(_STATE["images_dir"]) / filename
    img = cv2.imread(str(img_path))
    if img is None:
        return jsonify({"annotations": [], "img_w": 0, "img_h": 0})

    h, w = img.shape[:2]
    annotations = _load_yolo_label(label_path, w, h)

    return jsonify({
        "annotations": annotations,
        "img_w": w,
        "img_h": h,
    })


@app.route("/api/save", methods=["POST"])
def api_save():
    """Save annotation for an image."""
    data = request.get_json()
    filename = data["filename"]
    annotations = data["annotations"]
    img_w = data["img_w"]
    img_h = data["img_h"]

    stem = Path(filename).stem
    label_path = Path(_STATE["labels_dir"]) / f"{stem}.txt"

    _save_yolo_label(label_path, annotations, img_w, img_h)

    return jsonify({"status": "saved", "path": str(label_path)})


@app.route("/api/schema")
def api_schema():
    """Return the equine keypoint schema for the frontend."""
    group_colors = {}
    for group, bgr in KEYPOINT_COLORS.items():
        r, g, b = bgr[2], bgr[1], bgr[0]
        group_colors[group] = f"#{r:02x}{g:02x}{b:02x}"

    kp_colors = []
    for kp_id in range(NUM_KEYPOINTS):
        for group, ids in LIMB_GROUPS.items():
            if kp_id in ids:
                kp_colors.append(group_colors.get(group, "#c8c8c8"))
                break
        else:
            kp_colors.append("#c8c8c8")

    return jsonify({
        "num_keypoints": NUM_KEYPOINTS,
        "names": KEYPOINT_NAMES,
        "descriptions": [kp.description for kp in EQUINE_KEYPOINTS],
        "skeleton": [[a, b] for a, b in SKELETON_EDGES],
        "colors": kp_colors,
        "groups": {name: ids for name, ids in LIMB_GROUPS.items()},
        "group_colors": group_colors,
    })


# ---------------------------------------------------------------------------
# HTML/CSS/JS frontend
# ---------------------------------------------------------------------------

_LABELER_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Equine Keypoint Labeler</title>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
       background: #1a1a2e; color: #eee; height: 100vh; overflow: hidden; }

/* ---- PROJECT VIEW ---- */
#project-view { display: flex; align-items: center; justify-content: center;
                height: 100vh; flex-direction: column; gap: 24px; padding: 20px; }
#project-view h1 { color: #e94560; font-size: 28px; }
#project-view .subtitle { color: #888; font-size: 14px; margin-top: -16px; }

.project-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
                gap: 16px; max-width: 900px; width: 100%; }
.project-card { background: #16213e; border-radius: 8px; padding: 16px; cursor: pointer;
                border: 2px solid transparent; transition: all 0.2s; }
.project-card:hover { border-color: #e94560; transform: translateY(-2px); }
.project-card h3 { color: #e94560; margin-bottom: 8px; }
.project-card .stats { font-size: 13px; color: #888; }
.project-card .stats span { color: #2ecc71; }
.project-card .path { font-size: 11px; color: #555; margin-top: 8px; word-break: break-all; }

.upload-card { background: #16213e; border-radius: 8px; padding: 20px;
               border: 2px dashed #0f3460; text-align: center; }
.upload-card h3 { color: #e94560; margin-bottom: 12px; }
.upload-card input[type=file] { display: none; }
.upload-card label { display: inline-block; padding: 10px 24px; background: #e94560;
                     color: #fff; border-radius: 4px; cursor: pointer; font-weight: 600;
                     margin-bottom: 8px; }
.upload-card label:hover { opacity: 0.85; }

.form-row { display: flex; gap: 8px; align-items: center; margin-top: 8px; justify-content: center; }
.form-row input, .form-row select { padding: 6px 10px; border-radius: 4px; border: 1px solid #333;
                                     background: #0f3460; color: #eee; font-size: 13px; }
.form-row input { width: 140px; }

.import-section { max-width: 900px; width: 100%; background: #16213e; border-radius: 8px;
                  padding: 16px; }
.import-section h3 { color: #e94560; margin-bottom: 8px; font-size: 14px; }
.import-row { display: flex; gap: 8px; }
.import-row input { flex: 1; padding: 8px 12px; border-radius: 4px; border: 1px solid #333;
                    background: #0f3460; color: #eee; font-size: 13px; }

.btn { padding: 8px 16px; border: none; border-radius: 4px; cursor: pointer;
       font-size: 13px; font-weight: 600; color: #fff; }
.btn:hover { opacity: 0.85; }
.btn:disabled { opacity: 0.4; cursor: not-allowed; }
.btn-primary { background: #e94560; }
.btn-secondary { background: #0f3460; }
.btn-success { background: #2ecc71; }

#upload-status { font-size: 13px; color: #888; margin-top: 8px; }

/* ---- ANNOTATOR VIEW ---- */
#annotator-view { display: none; height: 100vh; }
.annotator-layout { display: flex; height: 100vh; }

#sidebar { width: 280px; background: #16213e; padding: 12px; display: flex;
           flex-direction: column; gap: 8px; overflow-y: auto; flex-shrink: 0; }
#sidebar h2 { font-size: 16px; color: #e94560; margin-bottom: 4px; }
#sidebar h3 { font-size: 13px; color: #888; margin: 8px 0 4px; text-transform: uppercase; }

.nav-btn { padding: 8px 16px; border: none; border-radius: 4px; cursor: pointer;
           font-size: 13px; font-weight: 600; }
.nav-btn:hover { opacity: 0.85; }
.btn-small { padding: 4px 10px; font-size: 12px; }

#nav-row { display: flex; gap: 6px; align-items: center; }
#nav-row .nav-btn { flex: 1; }
#frame-counter { font-size: 12px; color: #888; text-align: center; min-width: 60px; }

#kp-list { flex: 1; overflow-y: auto; }
.kp-item { padding: 5px 8px; border-radius: 4px; cursor: pointer; display: flex;
           align-items: center; gap: 6px; font-size: 12px; margin-bottom: 2px;
           border: 2px solid transparent; }
.kp-item:hover { background: rgba(255,255,255,0.05); }
.kp-item.active { border-color: #e94560; background: rgba(233,69,96,0.1); }
.kp-item.placed { opacity: 1; }
.kp-item.unplaced { opacity: 0.4; }
.kp-dot { width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0; }
.kp-name { flex: 1; }
.kp-vis { font-size: 10px; color: #888; }

#canvas-wrap { flex: 1; display: flex; align-items: center; justify-content: center;
               position: relative; overflow: hidden; background: #111; }
#canvas { cursor: crosshair; }

#status { position: fixed; bottom: 0; left: 0; right: 0; height: 28px;
          background: #0f3460; display: flex; align-items: center; padding: 0 12px;
          font-size: 12px; color: #aaa; gap: 16px; z-index: 10; }
#status .saved { color: #2ecc71; }

#help-overlay { display: none; position: fixed; inset: 0; background: rgba(0,0,0,0.8);
                z-index: 100; align-items: center; justify-content: center; }
#help-overlay.show { display: flex; }
#help-box { background: #16213e; padding: 24px; border-radius: 8px; max-width: 500px; }
#help-box h3 { margin-bottom: 12px; color: #e94560; }
#help-box table { width: 100%; }
#help-box td { padding: 4px 8px; font-size: 13px; }
#help-box td:first-child { color: #e94560; font-family: monospace; white-space: nowrap; }

#save-path-info { font-size: 11px; color: #888; background: #0a0f1e; padding: 6px 8px;
                  border-radius: 4px; word-break: break-all; }
</style>
</head>
<body>

<!-- ========== PROJECT SELECTION VIEW ========== -->
<div id="project-view">
  <h1>Equine Keypoint Labeler</h1>
  <p class="subtitle">Upload a video or open an existing project to start annotating</p>

  <div class="project-grid" id="project-list"></div>

  <div class="upload-card">
    <h3>New Project from Video</h3>
    <label for="video-input">Choose Video File (.mp4)</label>
    <input type="file" id="video-input" accept="video/*">
    <div id="video-filename" style="font-size:12px;color:#888;margin:4px 0"></div>
    <div class="form-row">
      <input id="project-name-input" placeholder="Project name" />
      <select id="num-frames-select">
        <option value="30">30 frames</option>
        <option value="50" selected>50 frames</option>
        <option value="100">100 frames</option>
        <option value="200">200 frames</option>
      </select>
      <select id="strategy-select">
        <option value="uniform" selected>Uniform</option>
        <option value="motion">High motion</option>
        <option value="random">Random</option>
      </select>
      <button class="btn btn-primary" id="upload-btn" onclick="uploadVideo()" disabled>
        Upload &amp; Extract
      </button>
    </div>
    <div id="upload-status"></div>
  </div>

  <div class="import-section">
    <h3>Import from local video path</h3>
    <div class="import-row">
      <input id="import-path" placeholder="e.g. output/hip654/hip654_raw.mp4" />
      <input id="import-name" placeholder="Project name (optional)" style="width:160px" />
      <button class="btn btn-secondary" onclick="importVideo()">Import &amp; Extract</button>
    </div>
    <div id="import-status" style="font-size:12px;color:#888;margin-top:6px"></div>
  </div>
</div>

<!-- ========== ANNOTATOR VIEW ========== -->
<div id="annotator-view">
  <div class="annotator-layout">
    <div id="sidebar">
      <div style="display:flex;align-items:center;gap:8px">
        <button class="btn btn-secondary btn-small" onclick="backToProjects()">&larr; Projects</button>
        <h2 id="project-title" style="flex:1;font-size:14px"></h2>
      </div>

      <div id="save-path-info"></div>

      <div id="nav-row">
        <button class="nav-btn btn-secondary" onclick="prevImage()">&larr; Prev</button>
        <span id="frame-counter">0 / 0</span>
        <button class="nav-btn btn-secondary" onclick="nextImage()">Next &rarr;</button>
      </div>

      <div style="display:flex;gap:6px">
        <button class="nav-btn btn-success" onclick="saveAnnotation()" style="flex:1">Save (S)</button>
        <button class="nav-btn btn-primary btn-small" onclick="toggleHelp()">? Help</button>
      </div>

      <div style="display:flex;gap:6px">
        <button class="nav-btn btn-secondary btn-small" onclick="addAnnotation()" style="flex:1">+ Add Horse</button>
        <button class="nav-btn btn-secondary btn-small" onclick="deleteAnnotation()" style="flex:1">- Remove</button>
      </div>

      <h3 id="ann-label">Annotation 1/1</h3>
      <div style="display:flex;gap:6px">
        <button class="nav-btn btn-secondary btn-small" onclick="prevAnnotation()" style="flex:1">&larr; Prev</button>
        <button class="nav-btn btn-secondary btn-small" onclick="nextAnnotation()" style="flex:1">Next &rarr;</button>
      </div>

      <h3>Keypoints <span style="font-size:10px;color:#666">(click to select, then click image)</span></h3>
      <div id="kp-list"></div>
    </div>

    <div id="canvas-wrap">
      <canvas id="canvas"></canvas>
    </div>
  </div>
</div>

<div id="status">
  <span id="status-file">No image loaded</span>
  <span id="status-dims"></span>
  <span id="status-save"></span>
  <span style="flex:1"></span>
  <span>? for shortcuts</span>
</div>

<div id="help-overlay" onclick="toggleHelp()">
  <div id="help-box" onclick="event.stopPropagation()">
    <h3>Keyboard Shortcuts</h3>
    <table>
      <tr><td>A / D</td><td>Previous / Next image</td></tr>
      <tr><td>&larr; / &rarr;</td><td>Previous / Next image</td></tr>
      <tr><td>W / E</td><td>Previous / Next keypoint</td></tr>
      <tr><td>S</td><td>Save current annotation</td></tr>
      <tr><td>X</td><td>Delete selected keypoint</td></tr>
      <tr><td>Q / R</td><td>Previous / Next annotation (horse)</td></tr>
      <tr><td>N</td><td>Add new annotation (horse)</td></tr>
      <tr><td>1-9, 0</td><td>Select keypoint 1-10</td></tr>
      <tr><td>Z</td><td>Toggle auto-advance mode</td></tr>
      <tr><td>Esc</td><td>Back to projects</td></tr>
      <tr><td>?</td><td>Toggle this help</td></tr>
    </table>
    <p style="margin-top:12px;font-size:12px;color:#888">
      Click on the image to place the selected keypoint.<br>
      Drag an existing keypoint to reposition it.<br>
      Right-click a keypoint to toggle visibility (occluded/visible).
    </p>
  </div>
</div>

<script>
// ============================================================
// State
// ============================================================
let schema = null;
let imageList = [];
let currentIdx = 0;
let annotations = [];
let currentAnn = 0;
let selectedKp = 0;
let imgW = 0, imgH = 0;
let imgObj = null;
let autoAdvance = true;
let isDirty = false;
let dragging = null;
let currentView = 'projects';

const canvas = document.getElementById('canvas');
const ctx = canvas.getContext('2d');

// ============================================================
// Project view
// ============================================================
async function loadProjects() {
  const resp = await fetch('/api/projects');
  const data = await resp.json();

  const list = document.getElementById('project-list');
  list.innerHTML = '';

  if (data.projects.length === 0) {
    list.innerHTML = '<p style="color:#666;grid-column:1/-1;text-align:center">No projects yet. Upload a video to get started.</p>';
  }

  for (const p of data.projects) {
    const card = document.createElement('div');
    card.className = 'project-card';
    card.onclick = () => openProject(p.name);
    const pct = p.total_frames > 0 ? Math.round((p.labeled_frames / p.total_frames) * 100) : 0;
    card.innerHTML = `
      <h3>${p.name}</h3>
      <div class="stats">
        ${p.total_frames} frames &middot; <span>${p.labeled_frames} labeled (${pct}%)</span>
      </div>
      <div class="path">${p.path}</div>`;
    list.appendChild(card);
  }
}

async function openProject(name) {
  const resp = await fetch('/api/open_project/' + encodeURIComponent(name));
  const data = await resp.json();
  if (data.error) { alert(data.error); return; }
  await enterAnnotator(name);
}

async function enterAnnotator(projectName) {
  if (!schema) {
    const resp = await fetch('/api/schema');
    schema = await resp.json();
  }

  const resp = await fetch('/api/images');
  const data = await resp.json();
  imageList = data.images;

  document.getElementById('project-view').style.display = 'none';
  document.getElementById('annotator-view').style.display = 'block';
  document.getElementById('project-title').textContent = projectName;
  document.getElementById('save-path-info').textContent =
    'Labels saved to: data/training/' + projectName + '/labels/';
  currentView = 'annotator';

  buildKpList();
  if (imageList.length > 0) loadImage(0);
}

function backToProjects() {
  if (isDirty && !confirm('Unsaved changes. Leave without saving?')) return;
  document.getElementById('project-view').style.display = '';
  document.getElementById('annotator-view').style.display = 'none';
  currentView = 'projects';
  isDirty = false;
  loadProjects();
}

// Video file input
document.getElementById('video-input').addEventListener('change', (e) => {
  const file = e.target.files[0];
  if (file) {
    document.getElementById('video-filename').textContent = file.name;
    document.getElementById('upload-btn').disabled = false;
    if (!document.getElementById('project-name-input').value) {
      document.getElementById('project-name-input').value = file.name.replace(/\.[^.]+$/, '');
    }
  }
});

async function uploadVideo() {
  const fileInput = document.getElementById('video-input');
  const file = fileInput.files[0];
  if (!file) return;

  const projectName = document.getElementById('project-name-input').value || file.name.replace(/\.[^.]+$/, '');
  const numFrames = document.getElementById('num-frames-select').value;
  const strategy = document.getElementById('strategy-select').value;

  const statusEl = document.getElementById('upload-status');
  statusEl.textContent = 'Uploading and extracting frames... this may take a moment.';
  document.getElementById('upload-btn').disabled = true;

  const formData = new FormData();
  formData.append('video', file);
  formData.append('project_name', projectName);
  formData.append('num_frames', numFrames);
  formData.append('strategy', strategy);

  try {
    const resp = await fetch('/api/upload_video', { method: 'POST', body: formData });
    const data = await resp.json();

    if (data.error) {
      statusEl.textContent = 'Error: ' + data.error;
      document.getElementById('upload-btn').disabled = false;
      return;
    }

    statusEl.textContent = `Done! ${data.frames_extracted} frames extracted. Opening...`;
    await openProject(data.project);
  } catch (err) {
    statusEl.textContent = 'Upload failed: ' + err.message;
    document.getElementById('upload-btn').disabled = false;
  }
}

async function importVideo() {
  const videoPath = document.getElementById('import-path').value.trim();
  const projectName = document.getElementById('import-name').value.trim();
  const statusEl = document.getElementById('import-status');

  if (!videoPath) { statusEl.textContent = 'Please enter a video path.'; return; }
  statusEl.textContent = 'Extracting frames...';

  try {
    const resp = await fetch('/api/import_video', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ video_path: videoPath, project_name: projectName }),
    });
    const data = await resp.json();
    if (data.error) { statusEl.textContent = 'Error: ' + data.error; return; }
    statusEl.textContent = `Done! ${data.frames_extracted} frames. Opening...`;
    await openProject(data.project);
  } catch (err) {
    statusEl.textContent = 'Failed: ' + err.message;
  }
}

// ============================================================
// Annotator
// ============================================================
function buildKpList() {
  const list = document.getElementById('kp-list');
  list.innerHTML = '';
  for (let i = 0; i < schema.num_keypoints; i++) {
    const div = document.createElement('div');
    div.className = 'kp-item unplaced';
    div.id = 'kp-' + i;
    div.onclick = () => selectKp(i);
    div.innerHTML = `
      <div class="kp-dot" style="background:${schema.colors[i]}"></div>
      <span class="kp-name">${i}. ${schema.names[i]}</span>
      <span class="kp-vis" id="kp-vis-${i}"></span>`;
    list.appendChild(div);
  }
  selectKp(0);
}

function selectKp(i) {
  selectedKp = i;
  document.querySelectorAll('.kp-item').forEach((el, idx) => {
    el.classList.toggle('active', idx === i);
  });
}

async function loadImage(idx) {
  if (idx < 0 || idx >= imageList.length) return;
  if (isDirty && !confirm('Unsaved changes. Continue?')) return;

  currentIdx = idx;
  const filename = imageList[idx];

  imgObj = new Image();
  imgObj.onload = async () => {
    const resp = await fetch('/api/annotation/' + encodeURIComponent(filename));
    const data = await resp.json();
    imgW = data.img_w;
    imgH = data.img_h;

    annotations = data.annotations.length > 0 ? data.annotations : [makeEmptyAnnotation()];
    currentAnn = 0;
    isDirty = false;

    resizeCanvas();
    render();
    updateUI();
  };
  imgObj.src = '/api/image/' + encodeURIComponent(filename);
}

function makeEmptyAnnotation() {
  const kps = [];
  for (let i = 0; i < schema.num_keypoints; i++) kps.push({x:0, y:0, visibility:0});
  return {bbox: [0,0,0,0], keypoints: kps};
}

function resizeCanvas() {
  const wrap = document.getElementById('canvas-wrap');
  const maxW = wrap.clientWidth - 20;
  const maxH = wrap.clientHeight - 20;
  const scale = Math.min(maxW / imgW, maxH / imgH, 1);
  canvas.width = Math.round(imgW * scale);
  canvas.height = Math.round(imgH * scale);
  canvas._scale = scale;
}

function render() {
  if (!imgObj) return;
  const s = canvas._scale;
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.drawImage(imgObj, 0, 0, canvas.width, canvas.height);

  for (let ai = 0; ai < annotations.length; ai++) {
    const ann = annotations[ai];
    const cur = ai === currentAnn;
    const alpha = cur ? 1.0 : 0.35;

    const [x1,y1,x2,y2] = ann.bbox;
    if (x2 > x1 && y2 > y1) {
      ctx.strokeStyle = cur ? '#e94560' : '#555';
      ctx.lineWidth = cur ? 2 : 1;
      ctx.setLineDash([6,3]);
      ctx.strokeRect(x1*s, y1*s, (x2-x1)*s, (y2-y1)*s);
      ctx.setLineDash([]);
    }

    for (const [a,b] of schema.skeleton) {
      const ka = ann.keypoints[a], kb = ann.keypoints[b];
      if (ka.visibility > 0 && kb.visibility > 0) {
        ctx.beginPath(); ctx.moveTo(ka.x*s, ka.y*s); ctx.lineTo(kb.x*s, kb.y*s);
        ctx.strokeStyle = cur ? 'rgba(255,255,255,0.5)' : 'rgba(255,255,255,0.15)';
        ctx.lineWidth = cur ? 2 : 1; ctx.stroke();
      }
    }

    for (let ki = 0; ki < schema.num_keypoints; ki++) {
      const kp = ann.keypoints[ki];
      if (kp.visibility === 0) continue;
      const cx = kp.x*s, cy = kp.y*s;
      const r = cur ? (ki === selectedKp ? 8 : 5) : 3;

      ctx.beginPath(); ctx.arc(cx, cy, r, 0, Math.PI*2);
      ctx.fillStyle = schema.colors[ki]; ctx.globalAlpha = alpha; ctx.fill();

      if (cur && ki === selectedKp) { ctx.strokeStyle='#fff'; ctx.lineWidth=2; ctx.stroke(); }
      if (kp.visibility === 1) {
        ctx.beginPath(); ctx.arc(cx,cy,r+3,0,Math.PI*2);
        ctx.strokeStyle='rgba(255,255,0,0.6)'; ctx.lineWidth=1;
        ctx.setLineDash([3,3]); ctx.stroke(); ctx.setLineDash([]);
      }
      if (cur) { ctx.font='10px sans-serif'; ctx.fillStyle='#fff';
                  ctx.fillText(schema.names[ki], cx+r+3, cy+3); }
      ctx.globalAlpha = 1.0;
    }
  }

  if (annotations.length > 0) {
    const ann = annotations[currentAnn];
    for (let i = 0; i < schema.num_keypoints; i++) {
      const el = document.getElementById('kp-'+i);
      const vis = document.getElementById('kp-vis-'+i);
      if (!el) continue;
      if (ann.keypoints[i].visibility === 2) {
        el.classList.add('placed'); el.classList.remove('unplaced'); vis.textContent='visible';
      } else if (ann.keypoints[i].visibility === 1) {
        el.classList.add('placed'); el.classList.remove('unplaced'); vis.textContent='occluded';
      } else {
        el.classList.remove('placed'); el.classList.add('unplaced'); vis.textContent='';
      }
    }
  }
}

function updateUI() {
  document.getElementById('frame-counter').textContent = `${currentIdx+1} / ${imageList.length}`;
  document.getElementById('status-file').textContent = imageList[currentIdx] || '';
  document.getElementById('status-dims').textContent = imgW ? `${imgW}x${imgH}` : '';
  document.getElementById('ann-label').textContent = `Annotation ${currentAnn+1}/${annotations.length}`;
  document.getElementById('status-save').textContent = '';
}

// ---- Mouse ----
canvas.addEventListener('mousedown', (e) => {
  if (currentView !== 'annotator') return;
  const s = canvas._scale;
  const rect = canvas.getBoundingClientRect();
  const mx = (e.clientX - rect.left) / s, my = (e.clientY - rect.top) / s;

  if (e.button === 2) {
    e.preventDefault();
    const hit = findKpNear(mx, my, 15/s);
    if (hit) { const kp = annotations[hit.annIdx].keypoints[hit.kpIdx];
               kp.visibility = kp.visibility === 2 ? 1 : 2; isDirty = true; render(); }
    return;
  }
  const hit = findKpNear(mx, my, 10/s);
  if (hit && hit.annIdx === currentAnn) { dragging = hit; return; }

  if (annotations.length > 0) {
    annotations[currentAnn].keypoints[selectedKp] = {x: mx, y: my, visibility: 2};
    updateBbox(annotations[currentAnn]); isDirty = true;
    if (autoAdvance && selectedKp < schema.num_keypoints - 1) selectKp(selectedKp + 1);
    render();
  }
});
canvas.addEventListener('mousemove', (e) => {
  if (!dragging) return;
  const s = canvas._scale; const rect = canvas.getBoundingClientRect();
  const mx = (e.clientX-rect.left)/s, my = (e.clientY-rect.top)/s;
  annotations[dragging.annIdx].keypoints[dragging.kpIdx].x = mx;
  annotations[dragging.annIdx].keypoints[dragging.kpIdx].y = my;
  isDirty = true; render();
});
canvas.addEventListener('mouseup', () => {
  if (dragging) { updateBbox(annotations[dragging.annIdx]); dragging = null; render(); }
});
canvas.addEventListener('contextmenu', (e) => e.preventDefault());
window.addEventListener('resize', () => { if (imgObj && currentView==='annotator') { resizeCanvas(); render(); } });

function findKpNear(mx, my, radius) {
  for (let ai = 0; ai < annotations.length; ai++)
    for (let ki = 0; ki < schema.num_keypoints; ki++) {
      const kp = annotations[ai].keypoints[ki];
      if (kp.visibility === 0) continue;
      if (Math.hypot(kp.x-mx, kp.y-my) < radius) return {annIdx:ai, kpIdx:ki};
    }
  return null;
}

function updateBbox(ann) {
  let minX=Infinity, minY=Infinity, maxX=-Infinity, maxY=-Infinity, any=false;
  for (const kp of ann.keypoints) {
    if (kp.visibility > 0) { minX=Math.min(minX,kp.x); minY=Math.min(minY,kp.y);
                              maxX=Math.max(maxX,kp.x); maxY=Math.max(maxY,kp.y); any=true; }
  }
  if (any) {
    const pad = Math.max(maxX-minX, maxY-minY) * 0.1;
    ann.bbox = [Math.max(0,minX-pad), Math.max(0,minY-pad),
                Math.min(imgW,maxX+pad), Math.min(imgH,maxY+pad)];
  }
}

// ---- Actions ----
function prevImage() { loadImage(currentIdx - 1); }
function nextImage() { loadImage(currentIdx + 1); }
function prevAnnotation() { if (currentAnn>0) { currentAnn--; updateUI(); render(); } }
function nextAnnotation() { if (currentAnn<annotations.length-1) { currentAnn++; updateUI(); render(); } }
function addAnnotation() { annotations.push(makeEmptyAnnotation()); currentAnn=annotations.length-1; isDirty=true; updateUI(); render(); }
function deleteAnnotation() {
  if (annotations.length<=1) { annotations=[makeEmptyAnnotation()]; currentAnn=0; }
  else { annotations.splice(currentAnn,1); if(currentAnn>=annotations.length) currentAnn=annotations.length-1; }
  isDirty=true; updateUI(); render();
}

async function saveAnnotation() {
  const toSave = annotations.filter(ann => ann.keypoints.some(kp => kp.visibility > 0));
  await fetch('/api/save', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({ filename: imageList[currentIdx], annotations: toSave, img_w: imgW, img_h: imgH }),
  });
  isDirty = false;
  const el = document.getElementById('status-save');
  el.textContent = 'Saved!'; el.className = 'saved';
  setTimeout(() => { el.textContent = ''; }, 2000);
}

function deleteSelectedKp() {
  if (annotations.length > 0) { annotations[currentAnn].keypoints[selectedKp] = {x:0,y:0,visibility:0}; isDirty=true; render(); }
}
function toggleHelp() { document.getElementById('help-overlay').classList.toggle('show'); }

// ---- Keyboard ----
document.addEventListener('keydown', (e) => {
  if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' || e.target.tagName === 'SELECT') return;
  if (currentView !== 'annotator') return;

  switch (e.key) {
    case 'a': case 'ArrowLeft':  prevImage(); break;
    case 'd': case 'ArrowRight': nextImage(); break;
    case 'w': selectKp(Math.max(0, selectedKp-1)); break;
    case 'e': selectKp(Math.min(schema.num_keypoints-1, selectedKp+1)); break;
    case 's': e.preventDefault(); saveAnnotation(); break;
    case 'x': deleteSelectedKp(); break;
    case 'q': prevAnnotation(); break;
    case 'r': nextAnnotation(); break;
    case 'n': addAnnotation(); break;
    case 'z': autoAdvance = !autoAdvance; break;
    case '?': toggleHelp(); break;
    case 'Escape': backToProjects(); break;
    case '1':case '2':case '3':case '4':case '5':
    case '6':case '7':case '8':case '9': selectKp(parseInt(e.key)-1); break;
    case '0': selectKp(9); break;
  }
});

// ---- Start ----
loadProjects();
</script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def run_labeler(
    images_dir: str | Path | None = None,
    labels_dir: str | Path | None = None,
    host: str = "0.0.0.0",
    port: int = 5000,
    debug: bool = False,
    data_root: str | Path | None = None,
) -> None:
    """Start the labeling GUI server.

    Args:
        images_dir: Optional directory containing images to open directly.
        labels_dir: Optional directory for YOLO-Pose labels.
        host: Server host.
        port: Server port.
        debug: Enable Flask debug mode.
        data_root: Base directory for training data projects.
    """
    if data_root:
        _STATE["data_root"] = str(Path(data_root))

    data_root_path = Path(_STATE["data_root"])
    data_root_path.mkdir(parents=True, exist_ok=True)

    # If specific dirs provided, set them as active project
    if images_dir and labels_dir:
        images_dir = Path(images_dir)
        labels_dir = Path(labels_dir)
        labels_dir.mkdir(parents=True, exist_ok=True)

        if not images_dir.exists():
            raise FileNotFoundError(f"Images directory not found: {images_dir}")

        image_files = _list_images(images_dir)
        if not image_files:
            raise FileNotFoundError(f"No images found in {images_dir}")

        _STATE["images_dir"] = str(images_dir)
        _STATE["labels_dir"] = str(labels_dir)
        _STATE["image_files"] = image_files
        _STATE["project"] = images_dir.parent.name

    print(f"\n{'='*55}")
    print(f"  Equine Keypoint Labeler")
    print(f"{'='*55}")
    print(f"  Training data: {data_root_path.resolve()}")
    print(f"  Server:        http://{host}:{port}")
    print(f"{'='*55}")
    print(f"  Open the URL above in your browser.")
    print(f"  Upload a video or open a project to start labelling.")
    print(f"  Labels are saved in YOLO-Pose format for training.")
    print(f"  Press Ctrl+C to stop.\n")

    app.run(host=host, port=port, debug=debug)


def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Web-based equine keypoint labeling GUI",
    )
    parser.add_argument("--images", help="Directory containing images (opens directly)")
    parser.add_argument("--labels", help="Directory for label output (YOLO-Pose format)")
    parser.add_argument("--data-root", default="data/training",
                        help="Base directory for training projects (default: data/training)")
    parser.add_argument("--host", default="0.0.0.0", help="Server host (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=5000, help="Server port (default: 5000)")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode")

    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    run_labeler(
        images_dir=args.images,
        labels_dir=args.labels,
        host=args.host,
        port=args.port,
        debug=args.debug,
        data_root=args.data_root,
    )


if __name__ == "__main__":
    main()
