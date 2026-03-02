# PROJECT SPECIFICATION: Equine Gait Analysis & Keypoint Tracking via Computer Vision

**Breeze Up & 2YO Sales — US and Europe**

Prepared for: Ultra Thoroughbreds
Date: March 2026
Version: 1.0 — Claude Code Build Spec

---

## 1. Executive Summary

This specification defines a computer vision system for equine gait analysis and keypoint tracking, targeting Breeze Up and two-year-old in-training sales in the United States and Europe. The system will process video of Thoroughbred horses galloping on a track and generate biomechanical data and performance metrics from that footage.

The primary goal is to build a stable keypoint tracking pipeline that can reliably detect anatomical landmarks on galloping Thoroughbreds, extract gait cycle data, and produce actionable analytics for bloodstock evaluation. The system should work from standard broadcast-quality or smartphone video without requiring markers on the horse.

This document covers the state of the art in equine pose estimation, recommended model architecture, the keypoint schema, the metrics we can derive, and a phased implementation plan suitable for execution with Claude Code.

---

## 2. State of the Art: Equine Pose Estimation

### 2.1 Foundation Models & Frameworks

#### 2.1.1 DeepLabCut (DLC) 3.0 + SuperAnimal-Quadruped

DeepLabCut is the most established open-source framework for markerless animal pose estimation. Version 3.0 is PyTorch-native and ships with SuperAnimal-Quadruped, a foundation model pretrained on 40,000+ images across quadruped species including horses. Key facts:

- **SuperAnimal-Quadruped** provides 39 keypoints out-of-the-box with zero-shot inference on horses. It achieves 84.6 mAP on the AnimalPose benchmark (dogs, cats, cows, horses, sheep) without any fine-tuning.
- DLC includes a dedicated **Horse-10 benchmark**: 30 diverse Thoroughbred horses with 22 body parts labeled across 8,114 frames. This was specifically designed to test generalization across individuals.
- Supports **multi-animal tracking** (maDLC) with identity tracking, critical for scenarios with multiple horses on track.
- Built-in **active learning loop**: label 50–200 frames, train, evaluate, refine. Achieves human-level accuracy with minimal data.
- Supports **stereo-camera 3D reconstruction** natively. A published equine dataset (DLC_Horse on GitHub) demonstrates 3D stride length and stance duration from stereo video.

#### 2.1.2 VAREN: Very Accurate and Realistic Equine Network (CVPR 2024)

VAREN is the state-of-the-art 3D parametric horse model, published at CVPR 2024 by the Max Planck Institute. It is built from 3D scans of real horses and provides:

- A fully articulated 3D skeleton with anatomically accurate bone structure.
- Learned pose-dependent deformations that model muscle bulging and skin sliding during motion.
- Variable body shape parameters that can represent horses of different sizes and conformations.
- Two resolution levels: a coarse mesh for fast fitting and a detailed mesh for analysis.

VAREN is ideal as a longer-term target for 3D body reconstruction from monocular video. It can be combined with 2D keypoint detections to fit a full 3D horse model to each frame.

**Code:** `github.com/silviazuffi/varen`

#### 2.1.3 PFERD Dataset (Scientific Data, 2024)

The Poses for Equine Research Dataset provides synchronized multi-view video and 3D marker data from five horses with 100+ skin-attached markers. It covers walking, trotting, cantering, and advanced motions (rearing, kicking). This is the most comprehensive public 3D equine motion dataset and establishes baselines for 3D markerless motion capture using the hSMAL/VAREN body models.

**Site:** `celiali.github.io/PFERD`

#### 2.1.4 ViTPose / ViTPose++ (SOTA Keypoint Detection)

ViTPose is the top-performing keypoint detection architecture on MS COCO and has strong animal pose estimation capabilities:

- Uses Vision Transformer (ViT) backbone with a lightweight decoder for heatmap regression.
- ViTPose++ extends this to heterogeneous keypoints across species using a knowledge factorization framework.
- Achieves state-of-the-art AP on AP-10K (animal pose benchmark with 54 species including horses) and APT-36K.
- Pretrained weights available via MMPose. Can be fine-tuned on horse-specific data with minimal effort.

#### 2.1.5 YOLO Pose (Ultralytics YOLOv8/v11/v26)

Ultralytics YOLO Pose provides single-stage detection + keypoint estimation in one forward pass:

- **Real-time inference**: 30+ FPS on consumer GPUs, suitable for processing large video volumes.
- Supports **custom keypoint schemas**. Can be fine-tuned on horse-specific keypoints via standard YOLO format.
- Multiple model sizes (nano to extra-large) for different compute budgets.
- Strong ecosystem: works with Roboflow for labeling/deployment, Supervision library for post-processing.

YOLO Pose is the recommended starting point for real-time inference and production deployment. Fine-tuning on horse data is straightforward.

---

### 2.2 Horse-Specific Datasets & Models

| Dataset / Model | Type | Details | Use Case |
|---|---|---|---|
| Horse-10 (DLC) | 2D Keypoints | 30 Thoroughbreds, 22 keypoints, 8,114 frames | Fine-tuning DLC for cross-individual generalization |
| AP-10K | 2D Keypoints | 54 species incl. horses, 17 keypoints, 10K images | Pretraining animal pose models |
| APT-36K | 2D Keypoints + Tracking | 30 species, 36K images with tracking annotations | Multi-animal pose + temporal tracking |
| AnimalPose (ICCV 2019) | 2D Keypoints | 5 species incl. horses, 20 keypoints | Cross-domain adaptation benchmark |
| PFERD | 3D Marker + Video | 5 horses, 100+ markers, 10 camera angles | 3D motion capture ground truth |
| VAREN | 3D Parametric Model | Articulated mesh from 3D scans, anatomical skeleton | 3D shape + pose reconstruction |
| DLC_Horse (Stereo) | 3D Keypoints | Stereo video, stride length + stance duration | 3D gait analysis via stereo |
| Roboflow Horse Pose | 2D Keypoints | Community datasets with YOLO-format annotations | Quick prototyping + fine-tuning YOLO |

---

### 2.3 Roboflow & Off-the-Shelf Options

Roboflow Universe hosts several horse pose estimation datasets and pretrained models that can be used for rapid prototyping:

- **Horse Pose by Nicolai Høirup Nielsen:** Keypoint detection model trained with YOLO-Pose format. Can be tested in-browser via Roboflow inference.
- **Horse Pose Estimation (multiple):** Several community datasets with varying keypoint counts. Quality varies; best used as supplementary training data.
- **Roboflow Keypoint Detection Pipeline:** Label, train, and deploy keypoint models with skeleton definition, annotation tooling, and one-click model training. Supports YOLO-Pose natively.

**Recommendation:** Use Roboflow for labeling and dataset management, but train locally or via cloud GPU for best control over model architecture and hyperparameters.

---

## 3. Recommended Architecture

### 3.1 Two-Track Strategy

We recommend a dual-track approach to balance quick results with long-term sophistication:

| Track | Approach | Timeline | Output |
|---|---|---|---|
| **Track A: Production 2D** | YOLO-Pose fine-tuned on horse keypoints + ByteTrack temporal tracking | Weeks 1–4 | Stable 2D keypoints per frame, gait cycle metrics, speed/stride data |
| **Track B: Research 3D** | DeepLabCut + VAREN 3D model fitting from monocular video | Weeks 5–12 | 3D joint angles, limb trajectories, conformation metrics |

---

### 3.2 Track A: Production 2D Pipeline (Primary)

This is the core deliverable. The pipeline processes video and outputs per-frame keypoints plus derived gait metrics.

**Step 1: Horse Detection**
- Use YOLOv8/v11 object detection (pretrained on COCO) to detect horse bounding boxes in each frame.
- Apply ByteTrack or BoT-SORT for multi-object tracking to maintain identity across frames.
- Optionally fine-tune on Thoroughbred racing footage for better detection in gallop scenarios.

**Step 2: Keypoint Estimation**
- Fine-tune YOLO-Pose on our custom equine keypoint schema (see Section 4).
- Alternative: use DeepLabCut SuperAnimal-Quadruped zero-shot, then fine-tune with 100–200 labeled frames from our target domain (Breeze Up track footage).
- Crop detected horse regions and run keypoint model on each crop for maximum accuracy.

**Step 3: Temporal Smoothing & Gait Cycle Detection**
- Apply Savitzky-Golay or Kalman filtering to keypoint trajectories to reduce jitter.
- Detect gait cycles (stride boundaries) from vertical oscillation of the withers or poll keypoint.
- Use Fourier analysis or peak detection on limb keypoint trajectories to identify stance/swing phases.

**Step 4: Metric Computation**
- Compute all metrics defined in Section 5 from smoothed keypoint trajectories.
- Calibrate pixel-to-real-world distances using known reference objects (rail height, track width) or camera calibration.

---

### 3.3 Track B: 3D Reconstruction Pipeline (Research)

Once Track A is stable, extend to 3D:

- Use 2D keypoint detections from Track A as input.
- Fit VAREN 3D model to 2D keypoints via optimization (similar to SMPLify for humans).
- Extract 3D joint angles, limb lengths, and conformation parameters.
- For multi-camera setups: use DLC triangulation for ground-truth 3D.
- For monocular: use learned depth priors from VAREN shape model.

---

## 4. Equine Keypoint Schema

We define a 24-keypoint skeleton optimized for gallop gait analysis. This schema is compatible with YOLO-Pose annotation format and covers the anatomical landmarks most relevant to Thoroughbred performance assessment.

| ID | Keypoint | Anatomical Description | Gait Relevance |
|---|---|---|---|
| 0 | Poll | Top of the head between the ears | Head carriage, balance indicator |
| 1 | Nose | Tip of the muzzle | Head position tracking |
| 2 | Throat | Throatlatch junction | Flexion angle of the poll |
| 3 | Withers | Highest point of the shoulder | Primary vertical displacement reference |
| 4 | Mid-back | Midpoint of the thoracolumbar spine | Spinal flexion during gallop |
| 5 | Croup | Highest point of the hindquarters (tuber sacrale) | Hindquarter power assessment |
| 6 | Tail base | Dock / base of the tail | Pelvic tilt tracking |
| 7 | L Shoulder | Point of the left shoulder (scapulohumeral joint) | Forelimb reach |
| 8 | L Elbow | Left elbow joint | Forelimb flexion |
| 9 | L Knee (fore) | Left carpus (knee) | Forelimb mechanics |
| 10 | L Fetlock (fore) | Left fore fetlock joint | Stride ground contact |
| 11 | L Fore Hoof | Left fore hoof (ground contact point) | Stride length, stance timing |
| 12 | R Shoulder | Point of the right shoulder | Forelimb reach |
| 13 | R Elbow | Right elbow joint | Forelimb flexion |
| 14 | R Knee (fore) | Right carpus (knee) | Forelimb mechanics |
| 15 | R Fetlock (fore) | Right fore fetlock joint | Stride ground contact |
| 16 | R Fore Hoof | Right fore hoof | Stride length, stance timing |
| 17 | L Hip (stifle) | Left stifle joint | Hindlimb drive |
| 18 | L Hock | Left hock (tarsus) joint | Hindlimb propulsion mechanics |
| 19 | L Hind Fetlock | Left hind fetlock | Hind stride ground contact |
| 20 | L Hind Hoof | Left hind hoof | Hind stride length |
| 21 | R Hip (stifle) | Right stifle joint | Hindlimb drive |
| 22 | R Hock | Right hock joint | Hindlimb propulsion mechanics |
| 23 | R Hind Hoof | Right hind hoof | Hind stride length |

**Skeleton connectivity:** Poll–Throat–Withers–Mid-back–Croup–Tail base along the topline, with each limb chain branching from the shoulder/hip joints down to the hooves.

**YOLO-Pose flip indices** (for horizontal augmentation): `[0, 1, 2, 3, 4, 5, 6, 12, 13, 14, 15, 16, 7, 8, 9, 10, 11, 21, 22, 23, 23, 17, 18, 19, 20]`

---

## 5. Metrics & Data Generation

The following metrics can be computed from tracked keypoints. All metrics should be computed per-stride and aggregated across the gallop sequence.

### 5.1 Gait Cycle Metrics

| Metric | Derivation | Significance |
|---|---|---|
| Stride Length | Distance between successive ground contacts of the same hoof | Primary speed indicator; correlates with racing ability |
| Stride Frequency | Number of complete gait cycles per second (Hz) | Cadence; elite sprinters typically 2.2–2.5 Hz at full gallop |
| Stride Duration | Time for one complete gait cycle (ms) | Inverse of frequency; consistency indicates soundness |
| Stance Duration | Time each hoof is in contact with the ground per stride | Power transmission window; shorter = faster turnover |
| Swing Duration | Time each limb is in the air per stride | Limb recovery efficiency |
| Duty Factor | Stance duration / stride duration ratio | Values <0.5 indicate aerial phase present (gallop) |
| Overreach | Distance the hind hoof lands ahead of the fore hoof print | Athleticism indicator; greater overreach = more power |
| Suspension Phase | Duration of aerial phase (all 4 hooves off ground) | Gallop quality; longer = more elastic energy storage |

### 5.2 Biomechanical Metrics

| Metric | Derivation | Significance |
|---|---|---|
| Withers Vertical Displacement | Peak-to-trough distance of withers keypoint (px or cm) | Locomotion efficiency; excessive = wasted energy |
| Head/Neck Angle | Angle at the poll-throat-withers chain | Balance and head carriage during gallop |
| Forelimb Protraction Angle | Angle of forelimb at maximum forward extension | Forelimb reach and stride coverage |
| Hindlimb Engagement Angle | Angle of hindlimb at maximum forward placement | Engine power; greater engagement = more propulsion |
| Fetlock Extension Angle | Maximum dorsiflexion angle of the fetlock during stance | Tendon loading; extreme angles may indicate risk |
| Knee Flexion (Fore) | Peak flexion of the carpus during swing phase | Limb clearance and action quality |
| Hock Flexion | Peak flexion of the hock during swing phase | Hindlimb mechanics and soundness indicator |
| Lateral Symmetry Index | L vs R limb parameter differences as percentage | Asymmetry >8–10% may indicate lameness or discomfort |

### 5.3 Performance / Speed Metrics

| Metric | Derivation | Significance |
|---|---|---|
| Estimated Speed | Stride length × stride frequency (calibrated) | Absolute speed at each point in the gallop |
| Acceleration Profile | Change in speed across successive strides | Acceleration ability and stamina indicator |
| Speed Efficiency Index | Speed / stride frequency ratio | Whether speed comes from length (efficient) or cadence |
| Ground Cover per Stride | Horizontal displacement of the centroid per gait cycle | Effective forward motion per stride |

### 5.4 Conformation & Movement Quality (3D Track)

| Metric | Derivation | Significance |
|---|---|---|
| Body Length Index | Withers-to-croup distance as ratio of height | Conformation assessment from video |
| Topline Angle | Angle of withers-midback-croup line | Spinal posture during gallop |
| Limb Length Ratios | Segment lengths (upper/lower limb) from 3D reconstruction | Conformational analysis without physical measurement |
| Joint Range of Motion | Min/max angles per joint across the gait cycle (3D) | Flexibility and mechanical soundness |
| Movement Quality Score | Composite of symmetry, regularity, and smoothness metrics | Overall movement quality index |

---

## 6. Labeling Strategy: Do We Need to Label?

### 6.1 What We Can Use Out of the Box

Several options exist for zero-shot or minimal-labeling inference:

- **DeepLabCut SuperAnimal-Quadruped:** 39 keypoints, zero-shot on horses. Published results show 84.6 mAP on AnimalPose benchmark. Best zero-shot option.
- **ViTPose with AP-10K weights:** 17 keypoints for quadrupeds. Strong out-of-distribution performance on horses. Available via MMPose.
- **DLC horse_sideview pretrained model:** Pretrained specifically on horses walking left to right. Works on diverse horse sizes and coat colors.

### 6.2 Why We Still Need Some Labeling

Despite strong zero-shot performance, fine-tuning is essential for our use case because:

- **Domain gap:** Breeze Up footage has specific camera angles, lighting, track surfaces, and horse silks/tack that differ from training data.
- **Gallop-specific challenges:** Most training data features walking/trotting horses. Gallop introduces motion blur, self-occlusion from limb overlap, and extreme limb positions.
- **Our keypoint schema:** We want 24 specific anatomical landmarks tuned for gait analysis. Off-the-shelf models use different keypoint definitions.
- **Multi-horse scenarios:** Breeze Ups often feature pairs of horses; we need robust tracking through occlusion.

### 6.3 Recommended Labeling Plan

Use a progressive labeling strategy to minimize effort while maximizing model accuracy:

| Phase | Frames | Source | Purpose |
|---|---|---|---|
| Phase 1: Bootstrap | 100–200 frames | 2–3 Breeze Up videos (US + European venues) | Initial fine-tuning on domain-specific data |
| Phase 2: Active Learning | 50–100 frames | Model selects uncertain frames | Target edge cases (occlusion, blur, near-side vs far-side) |
| Phase 3: Scale | 200–500 frames | Diverse conditions (rain, different tracks, coat colors) | Robustness across venues and conditions |
| **Total** | **350–800 frames** | **Across 10–20 videos** | **Production-ready model** |

**Labeling tooling:** Use Roboflow for annotation (supports keypoint skeleton definition), or DeepLabCut's built-in labeling GUI. Export in COCO keypoint format for maximum compatibility.

---

## 7. Best Practices for Computer Vision Tracking

### 7.1 Video Capture

- Minimum 60 FPS, ideally 120+ FPS for gallop analysis (limb motion is extremely fast).
- Side-on (perpendicular to track) camera angle is optimal for 2D gait analysis.
- Fixed camera position with known focal length enables calibration.
- Consistent lighting; avoid backlighting. Overcast conditions are ideal.
- Resolution: 1080p minimum. 4K preferred for distant horses or wide shots.
- Include a reference object of known size in frame for pixel-to-metric calibration.

### 7.2 Keypoint Detection Best Practices

- Use **top-down approach**: detect horse bounding box first, then run keypoint model on cropped region.
- Apply **test-time augmentation** (horizontal flip + multi-scale) for maximum accuracy at inference time.
- Use **heatmap-based** keypoint detection (not direct regression) for better accuracy on occluded joints.
- Set a **confidence threshold** (0.3–0.5) and interpolate low-confidence keypoints from temporal neighbors.
- Train with augmentation: random rotation (±15°), scale (0.75–1.25×), horizontal flip (with keypoint flip indices), color jitter, and motion blur.

### 7.3 Tracking Best Practices

- Use a modern tracker: **ByteTrack** or **BoT-SORT** (both available via Ultralytics/Supervision).
- Apply **Kalman filtering** on keypoint trajectories to smooth jitter and predict through brief occlusions.
- For consistent identity across a gallop run, use **appearance features** (Re-ID embedding) alongside motion prediction.
- Handle entry/exit of frame gracefully: initialize new tracks, terminate lost tracks after N frames.
- Post-process with **temporal median filtering** (window 3–5 frames) for final keypoint cleanup.

### 7.4 Calibration & Measurement

- Use **homography** (4+ corresponding points between image and ground plane) for perspective correction.
- Rail height or track markers as calibration reference for pixel-to-meter conversion.
- For speed estimation, track the centroid of the bounding box (or the withers keypoint) across calibrated frames.
- Account for **lens distortion**, especially with wide-angle cameras. Calibrate using a checkerboard pattern.

---

## 8. Technology Stack

| Component | Technology | Notes |
|---|---|---|
| Language | Python 3.10+ | Primary development language |
| Deep Learning | PyTorch 2.x | Backend for all models |
| Object Detection | Ultralytics YOLOv8/v11 | Horse detection + keypoint estimation |
| Pose Estimation (Research) | DeepLabCut 3.0 | SuperAnimal pretrained models, active learning |
| 3D Model (Research) | VAREN + PyTorch3D | 3D parametric horse model fitting |
| Tracking | ByteTrack via Supervision | Multi-object tracking with identity |
| Labeling | Roboflow + DLC GUI | Keypoint annotation with skeleton support |
| Video Processing | OpenCV + FFmpeg | Frame extraction, preprocessing |
| Data Analysis | NumPy, SciPy, Pandas | Signal processing, metric computation |
| Visualization | Matplotlib, Plotly | Gait analysis charts and overlays |
| Deployment | FastAPI + ONNX Runtime | API for video processing at scale |
| Frontend | React / Next.js | Analytics dashboard (integrates with Ultra Analytics) |
| Storage | S3 / GCS | Video storage, model artifacts |
| GPU Compute | NVIDIA A100/A10 (Cloud) | Training and batch inference |

---

## 9. Implementation Plan (Claude Code Build)

The following phases are designed for execution with Claude Code. Each phase produces a working deliverable.

### Phase 1: Foundation (Weeks 1–2)

**Goal:** Working horse detection + zero-shot keypoint estimation pipeline.

- Set up project structure: Python package with CLI for video processing.
- Implement horse detection using pretrained YOLO model.
- Integrate DeepLabCut SuperAnimal-Quadruped for zero-shot keypoint inference.
- Build video processing pipeline: frame extraction, detection, keypoint estimation, visualization.
- Output: annotated video with keypoints overlaid, CSV of per-frame keypoint coordinates.
- **Deliverable:** Process a Breeze Up video end-to-end with zero-shot keypoints.

### Phase 2: Custom Model Training (Weeks 3–4)

**Goal:** Fine-tuned YOLO-Pose model on our 24-keypoint equine schema.

- Define keypoint skeleton and create Roboflow project.
- Label 100–200 frames from diverse Breeze Up footage.
- Fine-tune YOLO-Pose (start with YOLOv8m-pose pretrained weights).
- Evaluate: compute mAP, OKS, and per-keypoint accuracy. Target: 70+ mAP.
- Active learning: identify failure cases, label additional frames, retrain.
- **Deliverable:** Custom horse keypoint model with >70 mAP on held-out test set.

### Phase 3: Gait Analysis Engine (Weeks 5–6)

**Goal:** Compute all gait metrics from keypoint trajectories.

- Implement temporal smoothing (Kalman filter or Savitzky-Golay) on keypoint tracks.
- Build gait cycle detector: identify stride boundaries from withers vertical displacement.
- Implement metric computation for all Section 5 metrics.
- Build calibration module: homography-based pixel-to-metric conversion.
- Output structured data: per-stride metrics, per-horse summary, comparative tables.
- **Deliverable:** JSON/CSV output of all gait metrics for each horse in a Breeze Up video.

### Phase 4: Multi-Horse Tracking (Weeks 7–8)

**Goal:** Handle pairs/groups of horses with consistent identity.

- Integrate ByteTrack for multi-object tracking with identity.
- Handle occlusion: interpolate keypoints when horses overlap.
- Assign horse IDs: match detected horses to lot numbers / hip numbers.
- Batch processing: process entire sale catalog of videos.
- **Deliverable:** Process a full Breeze Up sale session with per-horse metric reports.

### Phase 5: Dashboard Integration (Weeks 9–10)

**Goal:** Integrate CV metrics into Ultra Analytics frontend.

- Design API endpoints for submitting video and retrieving results.
- Build React components for gait analysis visualization.
- Comparative views: overlay two horses' gait parameters side by side.
- Historical tracking: store metrics per horse across multiple videos/dates.
- **Deliverable:** Gait analysis section live in Ultra Analytics with interactive charts.

### Phase 6: 3D Reconstruction (Weeks 11–12, Research)

**Goal:** Fit VAREN 3D model to monocular video.

- Install VAREN and PyTorch3D.
- Implement 2D-to-3D lifting: optimize VAREN parameters to match 2D keypoint detections.
- Extract 3D joint angles, limb lengths, conformation parameters.
- Validate against known horse measurements where available.
- **Deliverable:** 3D horse model overlay on video + 3D metric extraction for selected horses.

---

## 10. Key Risks & Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Motion blur at gallop | Keypoint accuracy degrades | High FPS capture (120+); train with motion blur augmentation; temporal interpolation |
| Self-occlusion of limbs | Near-side limbs occlude far-side | Train on diverse angles; use temporal context to infer occluded keypoints; 3D model as prior |
| Variable tack/clothing | Silks, shadow rolls, etc. alter appearance | Augment training data with diverse tack; include tacked-up horses in training set |
| Camera variation across venues | Different angles, distances, lighting | Label data from multiple venues; apply domain adaptation techniques |
| Speed calibration accuracy | Pixel-to-metric errors | Use multiple reference objects; validate against GPS/timing beam data where available |
| Multiple similar horses | Identity switches in tracking | Use Re-ID features; leverage saddle cloth numbers for identity verification |

---

## 11. Key References & Resources

### Models & Code

- **DeepLabCut 3.0:** `github.com/DeepLabCut/DeepLabCut`
- **SuperAnimal-Quadruped:** via DLC Model Zoo (39 keypoints, zero-shot)
- **VAREN 3D Horse Model:** `github.com/silviazuffi/varen` (CVPR 2024)
- **PFERD Dataset:** `celiali.github.io/PFERD` (Scientific Data, 2024)
- **ViTPose/ViTPose++:** `github.com/ViTAE-Transformer/ViTPose`
- **Ultralytics YOLO-Pose:** `docs.ultralytics.com/tasks/pose`
- **Roboflow Keypoint Detection:** `universe.roboflow.com` (search: horse pose)
- **AP-10K Benchmark:** `github.com/AlexTheBad/AP-10K`
- **Horse-10 Benchmark:** `horse10.deeplabcut.org`
- **DLC Equine Stereo Dataset:** `github.com/NarimanNiknejad/DLC_Horse`

### Papers

- Zuffi et al. (2024) — VAREN: Very Accurate and Realistic Equine Network. CVPR 2024.
- Li et al. (2024) — The Poses for Equine Research Dataset (PFERD). Scientific Data.
- Ye et al. (2024) — SuperAnimal pretrained pose estimation models. Nature Communications.
- Mathis et al. (2018, 2019) — DeepLabCut: Markerless pose estimation. Nature Neuroscience / Nature Protocols.
- Xu et al. (2024) — ViTPose++: Vision Transformer for Generic Body Pose Estimation.
- Yu et al. (2021) — AP-10K: A Benchmark for Animal Pose Estimation. NeurIPS 2021.
- Hinrichs et al. (2025) — AI-assisted digital video analysis of equine gait. JEVS.
- Key et al. (2025) — Reliability of markerless CV algorithm for equine gait analysis. EVJ.

---

*End of Specification*
