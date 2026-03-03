"""Web-based GUI for manual equine keypoint annotation.

Serves a browser-based labelling tool that lets you:
- Load images from a directory (or frames extracted from video)
- Click to place / drag to adjust the 24 equine keypoints
- View skeleton connections in real time
- Load existing pseudo-labels (from auto-labeller) for correction
- Save labels in YOLO-Pose format for training

Usage:
    python -m src.cv.training.labeler --images data/images --labels data/labels
    # Then open http://localhost:5000 in your browser

The saved labels are directly compatible with:
    equine-train split <dir> -o <split_dir>
    equine-train train <split_dir>
"""

from __future__ import annotations

import base64
import json
import logging
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

# Global state set by run_labeler()
_STATE: dict = {
    "images_dir": "",
    "labels_dir": "",
    "image_files": [],
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

        # Parse bbox
        cx, cy, bw, bh = float(parts[1]), float(parts[2]), float(parts[3]), float(parts[4])
        x1 = (cx - bw / 2) * img_w
        y1 = (cy - bh / 2) * img_h
        x2 = (cx + bw / 2) * img_w
        y2 = (cy + bh / 2) * img_h

        # Parse keypoints
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


# ---------------------------------------------------------------------------
# API routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    """Serve the labeling UI."""
    return _LABELER_HTML


@app.route("/api/images")
def api_images():
    """List all available images."""
    files = _STATE["image_files"]
    return jsonify({
        "images": [f.name for f in files],
        "total": len(files),
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

    # Read image dimensions
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
    # Convert BGR colors to RGB hex for the browser
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
# HTML/CSS/JS frontend (single-page app, embedded)
# ---------------------------------------------------------------------------

_LABELER_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Equine Keypoint Labeler</title>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
       background: #1a1a2e; color: #eee; display: flex; height: 100vh; overflow: hidden; }

/* Sidebar */
#sidebar { width: 280px; background: #16213e; padding: 12px; display: flex;
           flex-direction: column; gap: 8px; overflow-y: auto; flex-shrink: 0; }
#sidebar h2 { font-size: 16px; color: #e94560; margin-bottom: 4px; }
#sidebar h3 { font-size: 13px; color: #888; margin: 8px 0 4px; text-transform: uppercase; }

.nav-btn { padding: 8px 16px; border: none; border-radius: 4px; cursor: pointer;
           font-size: 13px; font-weight: 600; }
.nav-btn:hover { opacity: 0.85; }
.btn-primary { background: #e94560; color: #fff; }
.btn-secondary { background: #0f3460; color: #fff; }
.btn-success { background: #2ecc71; color: #fff; }
.btn-small { padding: 4px 10px; font-size: 12px; }

#nav-row { display: flex; gap: 6px; align-items: center; }
#nav-row .nav-btn { flex: 1; }
#frame-counter { font-size: 12px; color: #888; text-align: center; min-width: 60px; }

/* Keypoint list */
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

/* Main canvas area */
#canvas-wrap { flex: 1; display: flex; align-items: center; justify-content: center;
               position: relative; overflow: hidden; background: #111; }
#canvas { cursor: crosshair; }

/* Status bar */
#status { position: fixed; bottom: 0; left: 0; right: 0; height: 28px;
          background: #0f3460; display: flex; align-items: center; padding: 0 12px;
          font-size: 12px; color: #aaa; gap: 16px; z-index: 10; }
#status .saved { color: #2ecc71; }

/* Keyboard shortcuts overlay */
#help-overlay { display: none; position: fixed; inset: 0; background: rgba(0,0,0,0.8);
                z-index: 100; align-items: center; justify-content: center; }
#help-overlay.show { display: flex; }
#help-box { background: #16213e; padding: 24px; border-radius: 8px; max-width: 500px; }
#help-box h3 { margin-bottom: 12px; color: #e94560; }
#help-box table { width: 100%; }
#help-box td { padding: 4px 8px; font-size: 13px; }
#help-box td:first-child { color: #e94560; font-family: monospace; white-space: nowrap; }
</style>
</head>
<body>

<div id="sidebar">
  <h2>Equine Keypoint Labeler</h2>

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
    <button class="nav-btn btn-secondary btn-small" onclick="prevAnnotation()" style="flex:1">&larr; Prev Ann</button>
    <button class="nav-btn btn-secondary btn-small" onclick="nextAnnotation()" style="flex:1">Next Ann &rarr;</button>
  </div>

  <h3>Keypoints <span style="font-size:10px;color:#666">(click to select, then click on image)</span></h3>
  <div id="kp-list"></div>
</div>

<div id="canvas-wrap">
  <canvas id="canvas"></canvas>
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
      <tr><td>Q / R</td><td>Previous / Next annotation</td></tr>
      <tr><td>N</td><td>Add new annotation (horse)</td></tr>
      <tr><td>1-9, 0</td><td>Select keypoint 1-10</td></tr>
      <tr><td>Z</td><td>Auto-advance: place keypoint &amp; select next</td></tr>
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
let annotations = [];  // array of {bbox, keypoints}
let currentAnn = 0;    // which annotation (horse) we're editing
let selectedKp = 0;    // which keypoint is selected for placement
let imgW = 0, imgH = 0;
let imgObj = null;
let autoAdvance = true;
let isDirty = false;
let dragging = null;   // {annIdx, kpIdx}

const canvas = document.getElementById('canvas');
const ctx = canvas.getContext('2d');

// ============================================================
// Init
// ============================================================
async function init() {
  const [schemaResp, imagesResp] = await Promise.all([
    fetch('/api/schema').then(r => r.json()),
    fetch('/api/images').then(r => r.json()),
  ]);
  schema = schemaResp;
  imageList = imagesResp.images;

  buildKpList();
  if (imageList.length > 0) loadImage(0);
}

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

// ============================================================
// Image loading
// ============================================================
async function loadImage(idx) {
  if (idx < 0 || idx >= imageList.length) return;
  if (isDirty && !confirm('Unsaved changes. Continue without saving?')) return;

  currentIdx = idx;
  const filename = imageList[idx];

  // Load image
  imgObj = new Image();
  imgObj.onload = async () => {
    // Load annotation
    const resp = await fetch('/api/annotation/' + encodeURIComponent(filename));
    const data = await resp.json();
    imgW = data.img_w;
    imgH = data.img_h;

    if (data.annotations.length > 0) {
      annotations = data.annotations;
    } else {
      // Start with one empty annotation
      annotations = [makeEmptyAnnotation()];
    }
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
  for (let i = 0; i < schema.num_keypoints; i++) {
    kps.push({x: 0, y: 0, visibility: 0});
  }
  return {bbox: [0, 0, 0, 0], keypoints: kps};
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

// ============================================================
// Rendering
// ============================================================
function render() {
  if (!imgObj) return;
  const s = canvas._scale;

  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.drawImage(imgObj, 0, 0, canvas.width, canvas.height);

  // Draw all annotations
  for (let ai = 0; ai < annotations.length; ai++) {
    const ann = annotations[ai];
    const isCurrent = ai === currentAnn;
    const alpha = isCurrent ? 1.0 : 0.35;

    // Draw bbox if set
    const [x1, y1, x2, y2] = ann.bbox;
    if (x2 > x1 && y2 > y1) {
      ctx.strokeStyle = isCurrent ? '#e94560' : '#555';
      ctx.lineWidth = isCurrent ? 2 : 1;
      ctx.setLineDash([6, 3]);
      ctx.strokeRect(x1 * s, y1 * s, (x2 - x1) * s, (y2 - y1) * s);
      ctx.setLineDash([]);
    }

    // Draw skeleton
    for (const [a, b] of schema.skeleton) {
      const ka = ann.keypoints[a], kb = ann.keypoints[b];
      if (ka.visibility > 0 && kb.visibility > 0) {
        ctx.beginPath();
        ctx.moveTo(ka.x * s, ka.y * s);
        ctx.lineTo(kb.x * s, kb.y * s);
        ctx.strokeStyle = isCurrent ? 'rgba(255,255,255,0.5)' : 'rgba(255,255,255,0.15)';
        ctx.lineWidth = isCurrent ? 2 : 1;
        ctx.stroke();
      }
    }

    // Draw keypoints
    for (let ki = 0; ki < schema.num_keypoints; ki++) {
      const kp = ann.keypoints[ki];
      if (kp.visibility === 0) continue;

      const cx = kp.x * s, cy = kp.y * s;
      const radius = isCurrent ? (ki === selectedKp ? 8 : 5) : 3;
      const color = schema.colors[ki];

      ctx.beginPath();
      ctx.arc(cx, cy, radius, 0, Math.PI * 2);
      ctx.fillStyle = color;
      ctx.globalAlpha = alpha;
      ctx.fill();

      // Outline for selected
      if (isCurrent && ki === selectedKp) {
        ctx.strokeStyle = '#fff';
        ctx.lineWidth = 2;
        ctx.stroke();
      }

      // Occluded indicator
      if (kp.visibility === 1) {
        ctx.beginPath();
        ctx.arc(cx, cy, radius + 3, 0, Math.PI * 2);
        ctx.strokeStyle = 'rgba(255,255,0,0.6)';
        ctx.lineWidth = 1;
        ctx.setLineDash([3, 3]);
        ctx.stroke();
        ctx.setLineDash([]);
      }

      // Label
      if (isCurrent) {
        ctx.font = '10px sans-serif';
        ctx.fillStyle = '#fff';
        ctx.fillText(schema.names[ki], cx + radius + 3, cy + 3);
      }

      ctx.globalAlpha = 1.0;
    }
  }

  // Update keypoint list styling
  if (annotations.length > 0) {
    const ann = annotations[currentAnn];
    for (let i = 0; i < schema.num_keypoints; i++) {
      const el = document.getElementById('kp-' + i);
      const visEl = document.getElementById('kp-vis-' + i);
      if (ann.keypoints[i].visibility === 2) {
        el.classList.add('placed');
        el.classList.remove('unplaced');
        visEl.textContent = 'visible';
      } else if (ann.keypoints[i].visibility === 1) {
        el.classList.add('placed');
        el.classList.remove('unplaced');
        visEl.textContent = 'occluded';
      } else {
        el.classList.remove('placed');
        el.classList.add('unplaced');
        visEl.textContent = '';
      }
    }
  }
}

function updateUI() {
  document.getElementById('frame-counter').textContent =
    `${currentIdx + 1} / ${imageList.length}`;
  document.getElementById('status-file').textContent = imageList[currentIdx] || '';
  document.getElementById('status-dims').textContent = imgW ? `${imgW}x${imgH}` : '';
  document.getElementById('ann-label').textContent =
    `Annotation ${currentAnn + 1}/${annotations.length}`;
  document.getElementById('status-save').textContent = '';
  document.getElementById('status-save').className = '';
}

// ============================================================
// Mouse interaction
// ============================================================
canvas.addEventListener('mousedown', (e) => {
  const s = canvas._scale;
  const rect = canvas.getBoundingClientRect();
  const mx = (e.clientX - rect.left) / s;
  const my = (e.clientY - rect.top) / s;

  // Right click: toggle visibility
  if (e.button === 2) {
    e.preventDefault();
    const hit = findKpNear(mx, my, 15 / s);
    if (hit) {
      const kp = annotations[hit.annIdx].keypoints[hit.kpIdx];
      kp.visibility = kp.visibility === 2 ? 1 : 2;
      isDirty = true;
      render();
    }
    return;
  }

  // Check for drag on existing keypoint
  const hit = findKpNear(mx, my, 10 / s);
  if (hit && hit.annIdx === currentAnn) {
    dragging = hit;
    return;
  }

  // Place keypoint
  if (annotations.length > 0) {
    const ann = annotations[currentAnn];
    ann.keypoints[selectedKp] = {x: mx, y: my, visibility: 2};
    updateBbox(ann);
    isDirty = true;

    if (autoAdvance && selectedKp < schema.num_keypoints - 1) {
      selectKp(selectedKp + 1);
    }
    render();
  }
});

canvas.addEventListener('mousemove', (e) => {
  if (!dragging) return;
  const s = canvas._scale;
  const rect = canvas.getBoundingClientRect();
  const mx = (e.clientX - rect.left) / s;
  const my = (e.clientY - rect.top) / s;

  annotations[dragging.annIdx].keypoints[dragging.kpIdx].x = mx;
  annotations[dragging.annIdx].keypoints[dragging.kpIdx].y = my;
  isDirty = true;
  render();
});

canvas.addEventListener('mouseup', () => {
  if (dragging) {
    updateBbox(annotations[dragging.annIdx]);
    dragging = null;
    render();
  }
});

canvas.addEventListener('contextmenu', (e) => e.preventDefault());

window.addEventListener('resize', () => {
  if (imgObj) { resizeCanvas(); render(); }
});

function findKpNear(mx, my, radius) {
  for (let ai = 0; ai < annotations.length; ai++) {
    for (let ki = 0; ki < schema.num_keypoints; ki++) {
      const kp = annotations[ai].keypoints[ki];
      if (kp.visibility === 0) continue;
      const dx = kp.x - mx, dy = kp.y - my;
      if (Math.sqrt(dx * dx + dy * dy) < radius) {
        return {annIdx: ai, kpIdx: ki};
      }
    }
  }
  return null;
}

function updateBbox(ann) {
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
  let hasAny = false;
  for (const kp of ann.keypoints) {
    if (kp.visibility > 0) {
      minX = Math.min(minX, kp.x);
      minY = Math.min(minY, kp.y);
      maxX = Math.max(maxX, kp.x);
      maxY = Math.max(maxY, kp.y);
      hasAny = true;
    }
  }
  if (hasAny) {
    const pad = Math.max((maxX - minX), (maxY - minY)) * 0.1;
    ann.bbox = [
      Math.max(0, minX - pad), Math.max(0, minY - pad),
      Math.min(imgW, maxX + pad), Math.min(imgH, maxY + pad)
    ];
  }
}

// ============================================================
// Actions
// ============================================================
function prevImage() { loadImage(currentIdx - 1); }
function nextImage() { loadImage(currentIdx + 1); }

function prevAnnotation() {
  if (currentAnn > 0) { currentAnn--; updateUI(); render(); }
}
function nextAnnotation() {
  if (currentAnn < annotations.length - 1) { currentAnn++; updateUI(); render(); }
}
function addAnnotation() {
  annotations.push(makeEmptyAnnotation());
  currentAnn = annotations.length - 1;
  isDirty = true;
  updateUI();
  render();
}
function deleteAnnotation() {
  if (annotations.length <= 1) {
    annotations = [makeEmptyAnnotation()];
    currentAnn = 0;
  } else {
    annotations.splice(currentAnn, 1);
    if (currentAnn >= annotations.length) currentAnn = annotations.length - 1;
  }
  isDirty = true;
  updateUI();
  render();
}

async function saveAnnotation() {
  // Filter out empty annotations (no keypoints placed)
  const toSave = annotations.filter(ann =>
    ann.keypoints.some(kp => kp.visibility > 0)
  );

  const resp = await fetch('/api/save', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({
      filename: imageList[currentIdx],
      annotations: toSave,
      img_w: imgW,
      img_h: imgH,
    }),
  });
  const data = await resp.json();
  isDirty = false;

  const statusEl = document.getElementById('status-save');
  statusEl.textContent = 'Saved!';
  statusEl.className = 'saved';
  setTimeout(() => { statusEl.textContent = ''; }, 2000);
}

function deleteSelectedKp() {
  if (annotations.length > 0) {
    annotations[currentAnn].keypoints[selectedKp] = {x: 0, y: 0, visibility: 0};
    isDirty = true;
    render();
  }
}

function toggleHelp() {
  document.getElementById('help-overlay').classList.toggle('show');
}

// ============================================================
// Keyboard shortcuts
// ============================================================
document.addEventListener('keydown', (e) => {
  // Don't capture if typing in an input
  if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;

  switch (e.key) {
    case 'a': case 'ArrowLeft':  prevImage(); break;
    case 'd': case 'ArrowRight': nextImage(); break;
    case 'w': selectKp(Math.max(0, selectedKp - 1)); break;
    case 'e': selectKp(Math.min(schema.num_keypoints - 1, selectedKp + 1)); break;
    case 's': e.preventDefault(); saveAnnotation(); break;
    case 'x': deleteSelectedKp(); break;
    case 'q': prevAnnotation(); break;
    case 'r': nextAnnotation(); break;
    case 'n': addAnnotation(); break;
    case 'z': autoAdvance = !autoAdvance; break;
    case '?': toggleHelp(); break;
    case '1': case '2': case '3': case '4': case '5':
    case '6': case '7': case '8': case '9':
      selectKp(parseInt(e.key) - 1); break;
    case '0': selectKp(9); break;
  }
});

// Start
init();
</script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def run_labeler(
    images_dir: str | Path,
    labels_dir: str | Path,
    host: str = "0.0.0.0",
    port: int = 5000,
    debug: bool = False,
) -> None:
    """Start the labeling GUI server.

    Args:
        images_dir: Directory containing images to label.
        labels_dir: Directory for YOLO-Pose label output.
        host: Server host.
        port: Server port.
        debug: Enable Flask debug mode.
    """
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

    logger.info("Labeler: %d images from %s", len(image_files), images_dir)
    logger.info("Labels will be saved to %s", labels_dir)

    print(f"\n{'='*55}")
    print(f"  Equine Keypoint Labeler")
    print(f"{'='*55}")
    print(f"  Images:  {images_dir} ({len(image_files)} files)")
    print(f"  Labels:  {labels_dir}")
    print(f"  Server:  http://{host}:{port}")
    print(f"{'='*55}")
    print(f"  Open the URL above in your browser to start labeling.")
    print(f"  Press Ctrl+C to stop.\n")

    app.run(host=host, port=port, debug=debug)


def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Web-based equine keypoint labeling GUI",
    )
    parser.add_argument("--images", required=True, help="Directory containing images")
    parser.add_argument("--labels", required=True, help="Directory for label output (YOLO-Pose format)")
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
    )


if __name__ == "__main__":
    main()
