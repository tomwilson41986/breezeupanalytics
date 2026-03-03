# Public Models for Equine Keypoint Tracking & 3D Reconstruction

> **Ultra Thoroughbreds — Equine Gait Analysis Project**
> Last updated: March 2026

This document catalogues every publicly available pretrained model that can perform keypoint detection or 3D reconstruction on horses, with download locations, code snippets, keypoint counts, and licensing.

---

## Zero-Labelling Models (Ready Out of the Box)

These models can run inference on horse video immediately with no custom training or annotation required.

| Model | Keypoints | Horse mAP | Speed | How to Use |
|---|---|---|---|---|
| **DLC SuperAnimal-Quadruped** | 39 | 84.6 (zero-shot) | ~5–15 FPS | `pip install deeplabcut` → run on video |
| **easy_ViTPose (AP-10K)** | 17 | ~71–74 | 30+ FPS | `--det-class horse --dataset ap10k` |
| **ViTPose++ (HuggingFace)** | 17 | 74.5 | ~10–30 FPS | `dataset_index=3` for animal head |
| **MMPose HRNet-w32 (AnimalPose)** | 20 | ~70+ | ~15–25 FPS | `--det-cat-id=17` for horse bbox |
| **Dessie** | 3D mesh | N/A | ~1–2 FPS | Single-image 3D shape + pose |
| **MagicPony** | 3D mesh | N/A | ~1–2 FPS | Single-image 3D reconstruction |

All of the above ship with pretrained weights that include horses in their training data. No labelling needed to get started.

---

## 1. 2D Keypoint Estimation Models

### 1.1 DeepLabCut SuperAnimal-Quadruped

The strongest zero-shot option. Trained on Quadruped-80K (Horse-30, AnimalPose, AP-10K, AcinoSet, StanfordDogs, iRodent).

- **Keypoints:** 39 (unified quadruped superset)
- **Architecture:** HRNet-w32 (top-down) + Faster R-CNN detector; also DLCRNet (bottom-up)
- **Horse Performance:** 84.6 mAP zero-shot on AnimalPose benchmark. Validated on Horse-30 — matched ground truth stride detection in 24 of 30 videos
- **Video Adaptation:** Built-in unsupervised adaptation reduces jitter with zero labels. Also supports Kalman filtering post-processing
- **Fine-tuning:** 10–100× more data efficient than training from scratch. As few as 14–73 frames significantly improve Horse-10 performance
- **License:** Modified MIT — academic/non-commercial use only

**Weights:**

| File | Description | Location |
|---|---|---|
| `pose_model.pth` | HRNet-w32 for DLC 3.0 PyTorch | HuggingFace: `mwmathis/DeepLabCutModelZoo-SuperAnimal-Quadruped` |
| `detector.pt` | Faster R-CNN horse/animal detector | Same HuggingFace repo |
| `hrnet_w32_quadruped80k.pth` | HRNet-w32 MMPose-compatible | Same HuggingFace repo |

**Quick start (zero-shot on video):**

```python
import deeplabcut

deeplabcut.video_inference_superanimal(
    ["breeze_up.mp4"],
    superanimal_name="superanimal_quadruped",
    scale_list=[200, 300, 400],
    video_adapt=True
)
```

**Download weights directly:**

```python
from pathlib import Path
from dlclibrary import download_huggingface_model

model_dir = Path("./superanimal_quadruped")
model_dir.mkdir(exist_ok=True)
download_huggingface_model(
    "mwmathis/DeepLabCutModelZoo-SuperAnimal-Quadruped",
    model_dir
)
```

| Link | URL |
|---|---|
| Repository | https://github.com/DeepLabCut/DeepLabCut |
| Model Zoo Docs | https://deeplabcut.github.io/DeepLabCut/docs/ModelZoo.html |
| HuggingFace | https://huggingface.co/mwmathis/DeepLabCutModelZoo-SuperAnimal-Quadruped |
| Horse-10 Benchmark | https://horse10.deeplabcut.org |
| Paper | Ye et al. (2024) Nature Communications |

---

### 1.2 ViTPose++ (AP-10K Animal Expert)

State-of-the-art transformer pose estimation with dedicated animal keypoint head via Mixture-of-Experts.

- **Keypoints:** 17 (AP-10K schema: eyes, nose, neck, shoulders, elbows, wrists, hips, knees, ankles, tail root)
- **Architecture:** Vision Transformer backbone (ViT-S/B/L/H) with MoE FFN + task-specific decoder
- **Horse Performance:** ViTPose++-B achieves 74.5 mAP on AP-10K val (54 species incl. horses)
- **Expert Heads:** 6 heads — COCO (0), AIC (1), MPII (2), **AP-10K (3)**, APT-36K (4), COCO-WholeBody (5)
- **License:** Apache 2.0

**Sizes:**

| Variant | Params | AP-10K mAP |
|---|---|---|
| ViTPose++-S | ~24M | ~68 |
| ViTPose++-B | ~86M | 74.5 |
| ViTPose++-L | ~307M | ~76 |
| ViTPose++-H | ~632M | ~78 |

**HuggingFace Transformers (recommended):**

```python
from transformers import (
    VitPoseForPoseEstimation,
    VitPoseImageProcessor,
    RTDetrForObjectDetection,
    RTDetrImageProcessor,
)
from PIL import Image

image = Image.open("horse.jpg")

# Stage 1: Detect horse bounding box
det_processor = RTDetrImageProcessor.from_pretrained("PekingU/rtdetr_r50vd")
det_model = RTDetrForObjectDetection.from_pretrained("PekingU/rtdetr_r50vd")
det_inputs = det_processor(images=image, return_tensors="pt")
det_outputs = det_model(**det_inputs)
# Filter for horse class (COCO id=18)

# Stage 2: ViTPose++ with AP-10K animal head
processor = VitPoseImageProcessor.from_pretrained("usyd-community/vitpose-plus-large")
model = VitPoseForPoseEstimation.from_pretrained("usyd-community/vitpose-plus-large")
inputs = processor(image, boxes=[horse_bboxes], return_tensors="pt")
outputs = model(**inputs, dataset_index=3)  # 3 = AP-10K animal head
```

**HuggingFace checkpoints:**

| Model | HuggingFace ID |
|---|---|
| ViTPose++-S | `usyd-community/vitpose-plus-small` |
| ViTPose++-B | `usyd-community/vitpose-plus-base` |
| ViTPose++-L | `usyd-community/vitpose-plus-large` |
| ViTPose++-H | `usyd-community/vitpose-plus-huge` |

| Link | URL |
|---|---|
| Repository | https://github.com/ViTAE-Transformer/ViTPose |
| HuggingFace Docs | https://huggingface.co/docs/transformers/model_doc/vitpose |
| Paper (ViTPose) | Xu et al. (2022) NeurIPS |
| Paper (ViTPose++) | Xu et al. (2024) TPAMI |

---

### 1.3 easy_ViTPose

Production-friendly wrapper bundling YOLOv8 detection + ViTPose keypoints + SORT tracking. The simplest path to running ViTPose on horse video.

- **Keypoints:** 17 (AP-10K) or 23 (APT-36K), selectable via `--dataset`
- **Detection:** Supports `--det-class horse` for horse-specific bounding boxes
- **Speed:** 30+ FPS on modern NVIDIA GPUs and Apple Silicon (MPS)
- **Export:** Supports ONNX and TensorRT for edge deployment
- **Fine-tuning:** Includes guide for custom dataset fine-tuning with COCO-format annotations
- **License:** Apache 2.0

**Weights (all on HuggingFace `JunkyByte/easy_ViTPose`):**

| Checkpoint | Dataset | Architecture |
|---|---|---|
| `vitpose-s-ap10k.pth` | AP-10K (animals) | ViT-S |
| `vitpose-b-ap10k.pth` | AP-10K (animals) | ViT-B |
| `vitpose-l-ap10k.pth` | AP-10K (animals) | ViT-L |
| `vitpose-h-ap10k.pth` | AP-10K (animals) | ViT-H |
| `vitpose-*-apt36k.pth` | APT-36K (animals + tracking) | S/B/L/H |

**Quick start:**

```bash
git clone https://github.com/JunkyByte/easy_ViTPose.git
cd easy_ViTPose && pip install -e .
pip install -r requirements.txt

# Download models
./models/download.sh

# Run on horse video
python inference.py \
    --det-class horse \
    --input breeze_up.mp4 \
    --model ./ckpts/vitpose-l-ap10k.pth \
    --yolo ./yolov8l.pt \
    --dataset ap10k \
    --output-path results/ \
    --save-img --save-json
```

**Python API:**

```python
import cv2
from easy_ViTPose import VitInference

model = VitInference(
    model_path="./ckpts/vitpose-l-ap10k.pth",
    yolo_path="./yolov8l.pt",
    model_name="l",
    det_class="horse",
    dataset="ap10k",
    is_video=True
)

frame = cv2.imread("horse_frame.jpg")
keypoints = model.inference(frame)
```

| Link | URL |
|---|---|
| Repository | https://github.com/JunkyByte/easy_ViTPose |
| HuggingFace | https://huggingface.co/JunkyByte/easy_ViTPose |

---

### 1.4 MMPose Animal Pose Models

OpenMMLab's comprehensive toolbox with dedicated animal configs and pretrained weights across multiple architectures.

- **Keypoints:** 20 (AnimalPose), 17 (AP-10K), or 22 (Horse-10)
- **Architectures:** HRNet-w32, HRNet-w48, ResNet-50/101/152, ViTPose, RTMPose
- **Detection:** RTMDet or Faster R-CNN with COCO category `17` for horse
- **License:** Apache 2.0

**Key pretrained weights:**

| Config | Weights URL | Dataset |
|---|---|---|
| `td-hm_hrnet-w32_8xb64-210e_animalpose-256x256` | `download.openmmlab.com/mmpose/animal/hrnet/hrnet_w32_animalpose_256x256-1aa7f075_20210426.pth` | AnimalPose (5 species incl. horse) |
| Horse-10 configs (3 splits) | Via MMPose model zoo | Horse-10 (30 Thoroughbreds, 22 keypoints) |
| AP-10K configs | Via MMPose model zoo | AP-10K (54 species, 17 keypoints) |

**Demo:**

```bash
# Install
pip install -U openmim
mim install mmengine mmcv mmdet mmpose

# Run animal pose on horse image
python demo/topdown_demo_with_mmdet.py \
    demo/mmdetection_cfg/rtmdet_m_8xb32-300e_coco.py \
    rtmdet_m_weights.pth \
    configs/animal_2d_keypoint/topdown_heatmap/animalpose/td-hm_hrnet-w32_8xb64-210e_animalpose-256x256.py \
    hrnet_w32_animalpose_256x256-1aa7f075_20210426.pth \
    --input horse.jpg --det-cat-id=17 --show --draw-heatmap

# Or use the Inferencer (simpler):
python demo/inferencer_demo.py horse_images/ \
    --pose2d animal --vis-out-dir results/
```

| Link | URL |
|---|---|
| Repository | https://github.com/open-mmlab/mmpose |
| Animal Pose Docs | https://mmpose.readthedocs.io/en/dev-1.x/dataset_zoo/2d_animal_keypoint.html |
| Demo Docs | https://mmpose.readthedocs.io/en/latest/demos.html |

---

### 1.5 YOLO-Pose (Ultralytics)

Fastest single-stage option. Pretrained on COCO human keypoints — requires fine-tuning for horse skeleton, but training pipeline is straightforward.

- **Keypoints (pretrained):** 17 (COCO human) — **not usable zero-shot on horses**
- **Custom Keypoints:** Fully configurable skeleton via YAML dataset definition
- **Sizes:** Nano / Small / Medium / Large / Extra-Large
- **Speed:** 30–200+ FPS depending on size
- **License:** AGPL-3.0 (open source) or Ultralytics Enterprise

**Fine-tuning on custom horse keypoints:**

```yaml
# horse_keypoints.yaml
path: ./datasets/horse_pose
train: images/train
val: images/val

kpt_shape: [24, 3]  # 24 keypoints, (x, y, visibility)

flip_idx: [0,1,2,3,4,5,6,12,13,14,15,16,7,8,9,10,11,21,22,23,23,17,18,19,20]

names:
  0: horse
```

```python
from ultralytics import YOLO

model = YOLO("yolo11m-pose.pt")
results = model.train(
    data="horse_keypoints.yaml",
    epochs=100,
    imgsz=640,
    batch=16
)
```

| Link | URL |
|---|---|
| Repository | https://github.com/ultralytics/ultralytics |
| Pose Docs | https://docs.ultralytics.com/tasks/pose |
| Custom Training | https://docs.ultralytics.com/datasets/pose |

---

### 1.6 Roboflow Community Models

Community-contributed horse keypoint datasets and models. Variable quality — best for prototyping or supplementary training data.

| Model | Author | License | Notes |
|---|---|---|---|
| Horse Pose | Nicolai Høirup Nielsen | CC BY 4.0 | YOLO-Pose format, browser demo |
| Horse Pose Estimation | Various | CC BY 4.0 | 267+ images, multiple versions |

| Link | URL |
|---|---|
| Nielsen Horse Pose | https://universe.roboflow.com/nicolai-hoirup-nielsen/horse-pose |
| Horse Pose Estimation | https://universe.roboflow.com/horses-emeth/horse-pose-estimation-rxehu |
| Test Horse Pose (267 imgs) | https://universe.roboflow.com/test-akqok/horse-pose-estimation-8egum |

---

## 2. 3D Reconstruction & Parametric Models

### 2.1 VAREN (CVPR 2024)

State-of-the-art 3D parametric horse model from Max Planck. Learned from real 3D scans with pose-dependent muscle deformations.

- **Type:** Parametric 3D mesh model (analogous to SMPL for humans)
- **Output:** Articulated 3D mesh with anatomically accurate skeleton, variable body shape, pose-dependent muscle bulging
- **Checkpoint:** `pred_net_100.pth` — download from project website (registration required)
- **Training Data:** Real 3D horse scans (decimated meshes + registrations available)
- **Dependencies:** PyTorch3D, absl-py
- **License:** Research use (check project website)

```bash
git clone https://github.com/silviazuffi/varen.git
conda activate pytorch3d
pip install absl-py
# Register at project website → download pred_net_100.pth
# Place in varen/checkpoints/
```

| Link | URL |
|---|---|
| Repository | https://github.com/silviazuffi/varen |
| Paper | Zuffi et al., CVPR 2024 |

---

### 2.2 Dessie (ACCV 2024)

Single-image 3D horse shape and pose estimation using synthetic data and disentangled learning.

- **Type:** Monocular image → 3D horse mesh (shape + pose via hSMAL body model)
- **Backbone:** DINO-ViTs8 (last 3 layers unfrozen)
- **Pretrained:** Synthetic-only (version_9: Dessie, version_12: DinoHMR) and real-data fine-tuned variants
- **Generalisation:** Zero-shot to zebras, cows, deer
- **Dependencies:** PyTorch 1.11+, hSMAL body model (separate download)
- **License:** Research use

```bash
git clone https://github.com/Celiali/DESSIE.git
pip install torch==1.11.0+cu113 torchvision==0.12.0+cu113
pip install -r requirements.txt
# Download hSMAL model → ./code/src/SMAL/smpl_models/
# Download pretrained → ./results/
```

| Link | URL |
|---|---|
| Repository | https://github.com/Celiali/Dessie |
| Project Page | https://celiali.github.io/Dessie |
| Paper | Li et al., ACCV 2024 |

---

### 2.3 3D-Fauna / MagicPony / Ponymation

Family of models for single-image and video 3D quadruped reconstruction. Horse is the primary training category.

| Model | Venue | What It Does |
|---|---|---|
| **MagicPony** | CVPR 2023 | Single-image → articulated 3D horse. Pretrained model via `download_pretrained_horse.sh` |
| **3D-Fauna** | CVPR 2024 | Pan-category (100+ species) single-image 3D reconstruction. No 3D supervision |
| **Ponymation** | ECCV 2024 | Generative model of articulated 3D motions from unlabeled video. Horse/cow/giraffe/zebra |

- **Representation:** Hybrid SDF-mesh via DMTet
- **Input:** Single RGB image (test). DINO features + masks (train)
- **Output:** Textured 3D mesh, novel views, animations
- **License:** Research use

```bash
git clone https://github.com/3DAnimals/3DAnimals.git
cd results/magicpony && sh download_pretrained_horse.sh
python run.py --config-name test_magicpony_horse
```

| Link | URL |
|---|---|
| Repository | https://github.com/3DAnimals/3DAnimals |
| 3D-Fauna Project | https://kyleleey.github.io/3DFauna |

---

## 3. Datasets (For Fine-Tuning)

| Dataset | Images / Frames | Keypoints | Species | Format | License |
|---|---|---|---|---|---|
| **Horse-10 / Horse-30** | 8,114 frames, 30 horses | 22 | Thoroughbreds only | DLC / COCO | CC BY-NC 4.0 |
| **AP-10K** | 10,015 images | 17 | 54 species incl. horse | COCO | CC BY-NC 4.0 |
| **APT-36K** | 36,000 images | 17 | 30 species + tracking | COCO | Academic |
| **AnimalPose** | ~4,000 images | 20 | 5 species (dog, cat, sheep, cow, horse) | COCO / VOC XML | Academic |
| **PFERD** | Multi-view video, 5 horses | 100+ markers (3D) | Horses | Custom / 3D | Academic |
| **Roboflow Horse Pose** | 267+ images | Varies | Horses | YOLO / COCO | CC BY 4.0 |

| Link | URL |
|---|---|
| Horse-10 | https://horse10.deeplabcut.org |
| AP-10K | https://github.com/AlexTheBad/AP-10K |
| PFERD | https://celiali.github.io/PFERD |
| AnimalPose | Via MMPose dataset zoo |

---

## 4. Comparison Matrix

| Model | Zero-Shot Horses? | Keypoints | Speed | Fine-Tune Effort | Best For |
|---|---|---|---|---|---|
| **DLC SuperAnimal-Q** | ✅ 84.6 mAP | 39 | ~5–15 FPS | Minimal (14+ frames) | Best zero-shot baseline |
| **ViTPose++ (AP-10K)** | ✅ 74.5 mAP | 17 | ~10–30 FPS | Moderate | Highest ceiling after fine-tune |
| **easy_ViTPose** | ✅ | 17/23 | 30+ FPS | Moderate | Fastest deployment path |
| **MMPose HRNet** | ✅ | 17–22 | ~15–25 FPS | Moderate | Most flexible configs |
| **YOLO-Pose** | ❌ needs fine-tune | Custom 24 | 30–200+ FPS | Requires 100–200 frames | Production real-time |
| **VAREN** | N/A (3D fitting) | Full skeleton | Offline | N/A | 3D joint angles, conformation |
| **Dessie** | ✅ | 3D mesh | ~1–2 FPS | None | Quick 3D shape from photo |
| **MagicPony / 3D-Fauna** | ✅ | 3D mesh | ~1–2 FPS | None | Textured 3D reconstruction |

---

## 5. Recommended Integration Order

### Step 1 — Zero-Shot Baseline (No Labelling)

Run both DLC SuperAnimal-Quadruped and easy_ViTPose on the same Breeze Up clips. Compare keypoint stability, jitter, and anatomical accuracy. This validates the pipeline before any custom training.

### Step 2 — Production 2D Model (100–200 Labelled Frames)

Fine-tune YOLO-Pose on our custom 24-keypoint equine schema. Use Step 1 predictions as pseudo-labels to accelerate annotation (predict-then-correct workflow).

### Step 3 — 3D Research Track (No Additional Labelling)

Fit VAREN to 2D keypoints from Step 2 via optimisation. Use Dessie for rapid single-image experiments. Explore Ponymation for motion synthesis.

---

## References

| Paper | Venue | Year |
|---|---|---|
| Ye et al. — SuperAnimal pretrained pose estimation models | Nature Communications | 2024 |
| Xu et al. — ViTPose++: Vision Transformer for Generic Body Pose Estimation | TPAMI | 2024 |
| Xu et al. — ViTPose: Simple Vision Transformer Baselines | NeurIPS | 2022 |
| Zuffi et al. — VAREN: Very Accurate and Realistic Equine Network | CVPR | 2024 |
| Li et al. — Dessie: Disentanglement for 3D Horse Shape and Pose | ACCV | 2024 |
| Li et al. — Learning the 3D Fauna of the Web | CVPR | 2024 |
| Wu et al. — Ponymation: Learning Articulated 3D Animal Motions | ECCV | 2024 |
| Yu et al. — AP-10K: A Benchmark for Animal Pose Estimation | NeurIPS | 2021 |
| Li et al. — PFERD: Poses for Equine Research Dataset | Scientific Data | 2024 |
| Mathis et al. — DeepLabCut: Markerless pose estimation | Nature Neuroscience | 2018 |
| Rogers, Mathis et al. — Horse-10: Out-of-domain robustness for pose estimation | WACV | 2021 |
