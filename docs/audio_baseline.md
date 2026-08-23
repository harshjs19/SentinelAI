# Audio anomalous-sound baseline

## Dataset and attribution

Audio V1 uses only the bearing subset of **MIMII DG: Sound Dataset for
Malfunctioning Industrial Machine Investigation and Inspection for Domain
Generalization Task**:

- Official record: <https://zenodo.org/records/6529888>
- DOI: `10.5281/zenodo.6529888`
- License: Creative Commons Attribution 4.0 International (CC BY 4.0)
- Archive: `bearing.zip`, 772,253,369 bytes
- Official MD5: `6381a00f9efc0ced779c8ad847e4ff59`

Download and verify only the official bearing archive:

```shell
uv run python -m scripts.download_mimii_dg_bearing
```

The archive and extracted audio remain under ignored `datasets/` storage and are not
redistributed by SentinelAI.

## Observed data structure

The verified archive contains `bearing/train`, `bearing/test`, and one attribute CSV
for each of Sections 00, 01, and 02. All 3,599 WAV files are mono, 16-bit PCM, 16 kHz,
and exactly 10 seconds long. No byte-identical clips were found.

| Section | Normal train: source | Normal train: target | Labeled test clips |
| --- | ---: | ---: | ---: |
| 00 | 990 | 10 | 200 |
| 01 | 990 | 9 | 200 |
| 02 | 990 | 10 | 200 |

Every test section contains 50 clips for each source/target and normal/anomaly
combination. Filenames explicitly contain the section, source/target domain, train/test
split, normal/anomaly label, index, and operating attributes such as velocity,
location, or fault-noise condition. These fields and filesystem paths are used only to
locate and partition clips. They are never model features.

## Held-out-section protocol

This is a SentinelAI domain-shift experiment, not an official DCASE challenge score:

1. PCA reconstruction error and IsolationForest candidates fit Section 00 normal
   training audio only.
2. Within each section/domain normal-training group, every fifth sorted clip is held
   out for threshold calibration. This gives 800 detector-fit and 200 calibration
   clips for candidate training.
3. Section 01 labeled test clips select the detector family. They never fit either
   detector and do not choose the threshold.
4. A fresh selected detector fits the remaining Section 00+01 normal training clips:
   1,599 detector-fit clips with 400 normal calibration clips.
5. The threshold is frozen at the linear 99th percentile of those 400 normal scores.
6. Section 02 labeled test audio is evaluated only after detector selection, final fit,
   and threshold selection are complete.

Anomalous clips are never used to fit an anomaly detector. Section 02 labels do not
influence feature design, detector selection, hyperparameters, or the threshold.

## Features and detectors

WAV audio is downmixed to mono and resampled to 16 kHz when necessary. The feature
pipeline calculates a 64-band power mel spectrogram with a 1,024-sample Hann FFT and
512-sample hop, converts it to decibels, and records the mean and standard deviation of
each mel band across time. The result is a deterministic 128-value audio-content
vector.

The candidates are:

- PCA reconstruction error after `StandardScaler`, retaining 95% variance;
- IsolationForest after `StandardScaler`, with 300 estimators and seed 42.

Higher scores mean more anomalous audio for both candidates. Selection uses the
harmonic mean of Section 01 source ROC AUC, target ROC AUC, and standardized partial
ROC AUC at `max_fpr=0.1`:

```text
selection = 3 / (1/source_auc + 1/target_auc + 1/pauc)
```

## Real results

Section 01 validation:

| Detector | ROC AUC | pAUC@0.1 | AP | Source AUC | Target AUC | Selection |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| PCA reconstruction | 0.5823 | 0.5737 | 0.6224 | 0.5196 | 0.6652 | 0.5802 |
| IsolationForest | 0.4853 | 0.5337 | 0.5406 | 0.4540 | 0.5184 | 0.4995 |

PCA reconstruction was selected. Its final normal-calibration threshold is
`0.4605192170917355`.

Held-out Section 02:

- ROC AUC: `0.5213`
- pAUC@0.1: `0.5068`
- Average Precision: `0.5249`
- Source ROC AUC: `0.5088`
- Target ROC AUC: `0.5292`
- Precision: `0.4889`
- Recall: `0.2200`
- F1: `0.3034`
- Balanced accuracy: `0.4950`
- Confusion matrix `[[TN, FP], [FN, TP]]`: `[[77, 23], [78, 22]]`

This lightweight baseline is close to chance under the held-out Section 02 shift. The
weak result is retained rather than tuning against the test section or replacing the
experiment with a deep model.

Full metrics, counts, parameters, threshold distribution, and feature metadata are in
`evaluation/audio_baseline_results.json`. The ignored model and sidecar metadata are
written under `models/`.

## Runtime confidence semantics

The detector first compares an anomaly score `s` with the saved threshold `t`. The
normal calibration scores define an empirical percentile function `F`. Audio
`Prediction.confidence` measures normalized percentile distance from the threshold on
the selected side:

```text
anomalous: (F(s) - F(t)) / (1 - F(t))
healthy:   (F(t) - F(s)) / F(t)
```

The result is clipped to `[0, 1]`; evidence is zero at the decision boundary and grows
toward the extreme of the predicted side. It is `ConfidenceKind.RAW`, not a calibrated
class probability, probability of failure, fault severity, health score, or risk.

Time-series raw confidence is selected-class `predict_proba`; audio raw confidence is
empirical normal-score evidence. The two are not directly comparable and must not be
averaged, multiplied, or used as multimodal fusion weights.

## Commands and HTTP API

Train, reproduce saved-artifact evaluation, or run one WAV prediction:

```shell
uv run python -m modules.audio.cli train
uv run python -m modules.audio.cli evaluate
uv run python -m modules.audio.cli predict --input-wav path/to/clip.wav
```

For a machine whose `asset_type` is exactly `bearing`, upload WAV audio as multipart
field `file`:

```text
POST /machines/{machine_id}/predictions/audio
POST /machines/{machine_id}/analyses/audio
```

The prediction label is only `healthy` or `acoustic_anomaly`. An acoustic anomaly is
not a bearing-fault diagnosis or an identified physical failure mechanism. Audio-only
analysis remains provisional, with unavailable health score and risk level represented
as `null`.

## Limitations

- The artifact supports the MIMII DG bearing context only.
- The baseline uses compact global summaries and may miss time-local sound structure.
- Section 02 performance demonstrates weak domain-shift robustness.
- Confidence is raw empirical evidence and is not calibrated across machines or
  modalities.
- No fault-type taxonomy, multimodal fusion, health scoring, or risk scoring is
  implemented.
