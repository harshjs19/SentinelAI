# Thermal Intelligence V1 baseline

Thermal V1 classifies thermographic appearance from the **Rotating electromechanical
system dataset for condition monitoring**. The official source is the [CORA Dataverse
record](https://doi.org/10.34810/DATA2500), version 2.1 (released 2026-07-20), under CC BY
4.0. The related 2026 Scientific Data article is available at
[doi:10.1038/s41597-026-07224-0](https://doi.org/10.1038/s41597-026-07224-0). The camera
was a FLIR GF320.

## Reproducible subset and representation

Run:

```shell
uv run python scripts/download_thermal_dataset.py
```

The downloader queries the pinned Dataverse version and selects only the 36 stationary
thermography MAT files (nine conditions by four speeds) plus four interpretation TXT
files. It verifies the Dataverse size and MD5 for every file and writes an ignored
manifest containing file IDs, names, sizes, and checksums. The selected official files
total 842,355,594 bytes; the 38+ GB synchronized CSV corpus is not downloaded.

All 36 real MAT files are MATLAB 5 files with one `imagenes_celda` variable, a 1×450
cell array. Every cell is a 240×320×3 `uint8` array. All 16,200 frames are present and
valid, and all three channels are identical grayscale values stored in RGB form. The
files contain no per-frame timestamps or calibrated temperature matrix. Thermal V1
therefore treats them as non-radiometric thermographic image appearance. Pixel values
are not described as Celsius temperatures.

The official acquisition rate is 1/6 Hz, approximately one frame every six seconds for
45 minutes. Adjacent frames are consequently highly dependent and frame count must not
be interpreted as independent experimental sample count.

## Conditions and operating domains

| Dataset code | Public model label |
| --- | --- |
| H | `healthy` |
| BD | `bearing_fault` |
| HB | `half_broken_rotor_bar` |
| OB | `broken_rotor_bar` |
| U | `imbalance` |
| M | `misalignment` |
| W25 | `gear_wear_25` |
| W50 | `gear_wear_50` |
| W75 | `gear_wear_75` |

The stationary operating points are F5 = 5 Hz / 300 rpm, F15 = 15 Hz / 900 rpm, F50 =
50 Hz / 3000 rpm, and F60 = 60 Hz / 3600 rpm. Speed is experimental grouping metadata
only and never enters the predictive feature vector. Filenames and dataset fault codes
also never enter the feature vector.

## Frozen protocol and model

The split was declared before final evaluation:

- candidate fit: every F5 and F15 frame (8,100 frames; 18 acquisitions);
- validation and family selection: every F50 frame (4,050 frames; 9 acquisitions);
- fresh final fit: F5 + F15 + F50 (12,150 frames; 27 acquisitions);
- locked final test: F60 (4,050 frames; 9 acquisitions).

No individual-frame random split is used. An acquisition never crosses a partition. F60
does not influence candidate selection, hyperparameters, preprocessing, or feature
design, and the selected pipeline is freshly instantiated before the final fit.

Input is deterministically converted to RGB, resized without cropping while preserving
aspect ratio, symmetrically padded with the ImageNet mean to 256×256, and ImageNet
normalized. There is no random augmentation. The existing verified
`ResNet18_Weights.IMAGENET1K_V1` file is loaded locally, frozen, put in evaluation mode,
and run under inference mode. Only its 512-dimensional layer-4 adaptive-average-pooled
embedding is used. ImageNet logits are never interpreted as machine conditions.

Two fixed candidates use the identical embeddings:

1. `StandardScaler` + multinomial-capable `LogisticRegression` (`max_iter=2000`, seed
   42).
2. `RandomForestClassifier` (300 trees, seed 42, `n_jobs=-1`).

F50 frame-level macro F1 is the sole selection metric, with balanced accuracy as the
predeclared tie-breaker.

## Real results

| F50 candidate | Accuracy | Balanced accuracy | Macro F1 |
| --- | ---: | ---: | ---: |
| Logistic regression | 0.0938 | 0.0938 | 0.0449 |
| Random forest | 0.1753 | 0.1753 | 0.0730 |

The random forest was selected. The fresh forest fit on F5+F15+F50 achieved the
following locked F60 frame metrics: accuracy 0.1195, balanced accuracy 0.1195, macro
precision 0.3410, macro recall 0.1195, macro F1 0.1291, and weighted F1 0.1291.

| F60 class | Precision | Recall | F1 | Support |
| --- | ---: | ---: | ---: | ---: |
| `healthy` | 0.0000 | 0.0000 | 0.0000 | 450 |
| `bearing_fault` | 0.0000 | 0.0000 | 0.0000 | 450 |
| `half_broken_rotor_bar` | 0.0000 | 0.0000 | 0.0000 | 450 |
| `broken_rotor_bar` | 0.0000 | 0.0000 | 0.0000 | 450 |
| `imbalance` | 0.0000 | 0.0000 | 0.0000 | 450 |
| `misalignment` | 0.1841 | 0.1756 | 0.1797 | 450 |
| `gear_wear_25` | 1.0000 | 0.0089 | 0.0176 | 450 |
| `gear_wear_50` | 1.0000 | 0.0556 | 0.1053 | 450 |
| `gear_wear_75` | 0.8847 | 0.8356 | 0.8594 | 450 |

The confusion-matrix label order is `healthy`, `bearing_fault`,
`half_broken_rotor_bar`, `broken_rotor_bar`, `imbalance`, `misalignment`,
`gear_wear_25`, `gear_wear_50`, `gear_wear_75`:

```text
[[  0,   0,   0, 450,   0,   0,   0,  0,   0],
 [  0,   0, 450,   0,   0,   0,   0,  0,   0],
 [  0,   0,   0, 446,   4,   0,   0,  0,   0],
 [  0,   0, 100,   0,   0, 350,   0,  0,   0],
 [  7, 443,   0,   0,   0,   0,   0,  0,   0],
 [  0,   0, 356,   0,  14,  79,   0,  0,   1],
 [  0,   0, 217,   2, 201,   0,   4,  0,  26],
 [  0,   1,   0, 402,   0,   0,   0, 25,  22],
 [  0,   0,   0,  74,   0,   0,   0,  0, 376]]
```

Experiment probabilities are the arithmetic mean of all 450 frame probability vectors.
F60 experiment accuracy and macro F1 are both 0.1111 (one correct acquisition of nine):

| F60 experiment | True | Predicted | Mean probability of prediction |
| --- | --- | --- | ---: |
| BD | `bearing_fault` | `half_broken_rotor_bar` | 0.4834 |
| H | `healthy` | `broken_rotor_bar` | 0.3795 |
| HB | `half_broken_rotor_bar` | `broken_rotor_bar` | 0.5312 |
| M | `misalignment` | `half_broken_rotor_bar` | 0.3365 |
| OB | `broken_rotor_bar` | `misalignment` | 0.3477 |
| U | `imbalance` | `bearing_fault` | 0.4816 |
| W25 | `gear_wear_25` | `half_broken_rotor_bar` | 0.2171 |
| W50 | `gear_wear_50` | `broken_rotor_bar` | 0.3065 |
| W75 | `gear_wear_75` | `gear_wear_75` | 0.2830 |

These results expose severe operating-speed domain shift rather than hiding it. Important
confusions include healthy and half-broken rotor-bar acquisitions being classified as
broken rotor bar, imbalance as bearing fault, and W25/W50 as rotor-bar classes.

## Leakage and duplicate audit

Every one of the 16,200 matrices has a distinct SHA-256; there are no exact duplicates
within an experiment or across speed/condition experiments. Under the declared
near-duplicate rule (mean absolute `uint8` difference no greater than 1.0), 13,107 of
16,164 adjacent pairs are near-identical. This confirms why frames cannot be randomly
split. A visual review of mid-acquisition frames from all 36 files found no filename,
condition, speed, timestamp, temperature scale, or class-label overlay. No crop was
introduced.

Per-experiment expected, actual, missing, corrupt, and duplicate counts are recorded in
`evaluation/thermal_baseline_results.json`; each experiment has 450 actual frames and
zero missing, corrupt, exact-duplicate, or cross-experiment-duplicate frames.

## Artifact, runtime, and APIs

Training writes an ignored 21,055,540-byte (20.08 MiB) artifact to
`models/thermal_condition_classifier.joblib` and a deterministic ignored embedding cache
of 36,694,246 bytes (34.99 MiB) under `datasets/derived/thermal_resnet18/`. The trackable
evaluation JSON contains the
complete dataset manifest, split, preprocessing and encoder identities, candidate
metrics, final metrics, experiment probabilities, audit, and artifact metadata. The
ignored companion `models/thermal_condition_classifier.metadata.json` exposes the same
embedded artifact metadata for local inspection. The artifact stores the exact tested
classifier pipeline but not ResNet weights; loading
checks its format, labels, dataset/split identity, preprocessing, encoder identity,
embedding dimension, and probability support.

Runtime accepts PNG and JPEG/JPG thermograms at:

- `POST /machines/{machine_id}/predictions/thermal`
- `POST /machines/{machine_id}/analyses/thermal`

The supported asset type is `rotating_electromechanical_system`. Missing model artifacts
produce a path-free `503` response. A real W75/F60 frame-225 inference returned
`Prediction(modality=thermal, label=gear_wear_75, confidence=0.3266666667)`; after warmup,
five CPU predictions averaged 0.0714 seconds on the development machine. The real local
PostgreSQL/HTTP smoke took 3.8996 seconds for the first prediction (including lazy model
initialization), 0.0974 seconds for a warm prediction, and 0.0906 seconds for a warm
analysis request.

`Prediction.confidence` is the selected class's raw `predict_proba` output. It is not
calibrated fault severity, probability of failure, machine-health percentage, or
operational risk. In particular, the W25/W50/W75 label suffix is the controlled gearbox
condition, not a SentinelAI health score. Thermal findings remain `RAW`; analysis remains
`provisional`, with `health_score = null` and `risk_level = null`. Thermal and Time-Series
probabilities are not automatically calibrated to one another, Audio/Vision confidence
has different semantics again, and no cross-modal fusion is implemented.

## Limitations and future work

Each condition-speed pair is one stationary acquisition on the same test bench. The
holdout measures a new operating-speed domain for the same machine configuration; it
does not establish unseen-machine, unseen-camera, unseen fault-installation, or
production-plant generalization. The paper notes that component disassembly and
reassembly can introduce condition-specific physical differences, which is an explicit
confounder. Only nine independent condition acquisitions exist in F60 despite 4,050
frames.

The full CORA dataset also contains timestamp-alignable vibration, stator current, RTD
temperature, rotational speed, and thermography. It is a promising future empirical
fusion benchmark, but Thermal V1 does not download those signals or implement fusion.
Raspberry Pi 4 performance has not been measured. ONNX, quantization, MobileNet, or an
edge/server split remain future deployment options.
