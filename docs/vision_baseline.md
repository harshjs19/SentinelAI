# Vision Intelligence V1: VisA PCB1 baseline

Vision V1 is a normal-only industrial visual anomaly detector and offline localization
baseline. It uses only the PCB1 subset of Amazon Science's official [Visual Anomaly
(VisA)](https://github.com/amazon-science/spot-diff) release and its official
`split_csv/1cls.csv`. VisA is licensed under
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). The verified official archive
is 1,929,840,640 bytes with SHA-256
`2eb8690c803ab37de0324772964100169ec8ba1fa3f7e94291c9ca673f40f362`.

## Data and leakage audit

The extracted subset is `pcb1/Data/Images/{Normal,Anomaly}` plus
`pcb1/Data/Masks/Anomaly` and `pcb1/image_anno.csv`. It contains 1,104 JPEG images:
1,004 normal and 100 anomalous, with 100 PNG masks. Every image and mask is 1404×1070.
The annotation labels contain four atomic anomaly classes (`bent`, `melt`, `missing`,
and `scratch`), including multi-label combinations.

No byte-identical PCB1 images or exact duplicates crossing the official split were
found. A coarse 64-bit difference-hash audit found 53 train/test pairs at Hamming
distance at most one; this is reported as an inspection signal, not proof of duplicate
content, because PCB1 has a fixed, highly similar scene. Adjacent numeric normal images
were more similar than random pairs at 32×24 grayscale resolution (median mean absolute
difference 0.0330 versus 0.0473). Consequently, the internal fit/calibration partition
keeps numeric filename blocks of ten wholly on one side.

Filenames, filesystem paths, `Normal`/`Anomaly` directories, split labels, anomaly
labels, masks, and image metadata are used only for loading, partitioning, or
evaluation. None enters a feature vector.

The official one-class split has 904 training normals, 100 test normals, and 100 test
anomalies. Seed 42 and the grouped 80/20 policy yielded 726 detector-fit normals and 178
normal calibration images. Only the 726 fit normals fitted either detector. Only the
178 calibration normals established image and pixel thresholds. Test anomalies and
masks did not fit models or thresholds. Masks were evaluation-only.

## Frozen representation and preprocessing

Images are decoded from JPEG/PNG bytes, converted to RGB, resized without changing
aspect ratio, and symmetrically padded to 256×256; edges are not cropped. Padding uses
the ImageNet mean. Image resize is bilinear, mask resize is nearest-neighbor, and images
use ImageNet V1 mean `(0.485, 0.456, 0.406)` and standard deviation
`(0.229, 0.224, 0.225)`. There is no stochastic augmentation.

The encoder is frozen torchvision ResNet-18 with
`ResNet18_Weights.IMAGENET1K_V1` (`resnet18-f37072fd.pth`, 46,830,571 bytes, SHA-256
`f37072fd47e89c5e827621c5baffa7500819f7896bbacec160b1a16c560e07ec`) under
torchvision `0.28.0+cpu`. It runs in evaluation and inference modes with no trainable
parameters. `layer4` average pooling supplies a 512-dimensional global embedding.
Aligned `layer2` and `layer3` features supply a 16×16 grid of 384-dimensional patch
embeddings. ImageNet classifier logits and labels are not used as defect predictions.
Runtime loads only verified local weights and never downloads them over HTTP.

## Frozen models and thresholds

The comparison baseline standardizes global embeddings and applies Ledoit-Wolf
Mahalanobis distance. It is scientific context only. The predeclared runtime model
L2-normalizes patches, uniformly samples at most 5,000 fit-normal patches with seed 42,
and uses cosine distance to the nearest normal patch. The image score is the linear 99th
percentile of its 256 patch distances.

The image decision threshold is the linear p99 of 178 normal calibration image scores:
`0.2399601145`. The independent localization threshold is p99.9 of upsampled normal
calibration anomaly-map pixels: `0.1616612430`. Neither was optimized on test labels or
masks. Pixel ranking metrics include both normal and anomalous official test images.
AUPRO is intentionally omitted rather than approximated with an unverified metric.

| Method | ROC AUC | AP | pAUC@0.1 | Precision | Recall | F1 | Balanced accuracy | Confusion matrix |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| Global Mahalanobis comparison | 0.9315 | 0.9286 | 0.7721 | 0.9583 | 0.4600 | 0.6216 | 0.7200 | `[[98,2],[54,46]]` |
| Patch nearest-neighbor runtime | 0.8964 | 0.8620 | 0.6805 | 0.8889 | 0.0800 | 0.1468 | 0.5350 | `[[99,1],[92,8]]` |

Patch localization achieved pixel ROC AUC `0.9834`, pixel AP `0.4297`, IoU `0.2550`,
and Dice `0.4063`. Representative locked-test examples were anomaly `003.JPG` (true
positive), normal `0730.JPG` (false positive), and anomaly `000.JPG` (false negative).
These examples were inspected only after evaluation and did not change the detector.
At the frozen pixel threshold, their anomaly-map IoUs were respectively 0.0393, 0.0000,
and 0.0441; the first map covered all 56 annotated pixels but substantially overmarked
the image. The image-level false negative still overlapped 31 of 48 mask pixels, which
illustrates that image classification and thresholded localization have distinct rules.
The strong ranking metrics but low p99-threshold recall are preserved honestly for a
future Vision V2; the global result did not replace the predeclared patch runtime model.

## Artifact, runtime, and API

The ignored version-1 artifact is `models/vision_pcb1_anomaly_detector.joblib`
(7,684,980 bytes). It contains the 5,000-patch bank, normal calibration scores,
thresholds, split identity/counts, preprocessing, encoder compatibility identity, and
evaluation metrics. It does not duplicate ResNet weights. The ignored feature cache is
436,516,656 bytes.

On the experiment host, all work ran on CPU. Frozen feature extraction for all 1,104
images took 43.18 seconds. Traced peak training allocation was about 2.30 GB. A warm
real inference on anomaly `003.JPG` took 0.0374 seconds for feature extraction and
0.1765 seconds end to end, returning
`Prediction(modality=vision, label=visual_anomaly, confidence=0.0157414)`. Confidence is
low because this sample lies only slightly above the frozen p99 threshold.

The real PostgreSQL/HTTP smoke used a persisted `pcb1` development machine. The cold
multipart prediction request (including first model load and weight verification) took
3.8254 seconds and returned the same Prediction with `PredictionProduced`. The warm
analysis request took 0.1431 seconds and returned a provisional abnormal analysis with
RAW `visual_anomaly`, `health_score=null`, and `risk_level=null`; observed event order
was `PredictionProduced` then `AnalysisProduced`.

Runtime endpoints accept multipart field `file` for a machine whose `asset_type` is
exactly `pcb1`:

- `POST /machines/{machine_id}/predictions/vision`
- `POST /machines/{machine_id}/analyses/vision`

Missing artifact or encoder assets return safe HTTP 503 responses without paths.
Unsupported assets return 422 and malformed images return 400. Successful analysis
publishes `PredictionProduced` before `AnalysisProduced` and remains provisional with
`health_score=null` and `risk_level=null`.

Vision confidence is bounded raw empirical evidence relative to normal calibration
scores. It is not defect probability, failure probability, severity, health, or risk.
`visual_anomaly` is not a precise visual or mechanical fault diagnosis. Vision, Audio,
and Time-Series raw confidences are not calibrated to a common scale and are not fused.

## Limitations and later work

The detector supports the PCB1 reference distribution, not arbitrary assets, views,
cameras, lighting, or PCB variants. Localization is coarse at the 16×16 feature grid.
The static acquisition creates visually similar samples despite the grouped internal
split. There is no supervised defect classification, backbone fine-tuning, probability
calibration, evidence package, health scoring, risk scoring, or multimodal fusion.

ResNet-18 has not been measured on Raspberry Pi 4, so V1 is not claimed to be Pi-ready.
A later deployment study may compare ONNX, quantization, TorchScript/export,
MobileNet/EfficientNet, or an edge/server split. A later Vision V2 can investigate the
low frozen-threshold recall without changing this locked V1 result.
