# Audio Intelligence V2: frozen AST representation experiment

## Outcome

Audio V1's global log-mel summaries were close to chance under the Section 02 domain
shift. V2 tested whether a stronger frozen representation would address that weakness
without changing SentinelAI's normal-only anomaly-detection or runtime boundaries.

It did not under this protocol. Shrinkage Mahalanobis was the stronger V2 candidate,
but its Section 01 selection score was `0.5157682925029387`, below the V1 PCA reference
of `0.5801603837048501`. The deployment decision was made from Section 01 only, so V2
was not promoted and the V1 format-1 artifact remains the default runtime audio model.

## Pinned frozen encoder

V2 uses the AudioSet-fine-tuned Audio Spectrogram Transformer
[`MIT/ast-finetuned-audioset-10-10-0.4593`](https://huggingface.co/MIT/ast-finetuned-audioset-10-10-0.4593)
under its BSD-3-Clause license. Preparation is pinned to commit:

```text
f826b80d28226b62986cc218e5cec390b1096902
```

Run the preparation command before any V2 inference:

```shell
uv run python -m scripts.download_audio_encoder
```

It downloads only `config.json`, `preprocessor_config.json`, and the safetensors
checkpoint into ignored `models/pretrained/ast-audioset/` storage. The checkpoint is
346,404,948 bytes with SHA-256
`ae0c1e2ad4e1381d851fa9bf298ba13ebc9c5a914cdee2dbe427a6583869924d`;
all prepared files total 346,432,008 bytes. A generated identity file records and
verifies file sizes/checksums, model ID, revision, representation, and preprocessing.
Runtime loading is local-only and never downloads model assets during an HTTP request.
Missing local assets continue through the existing path-free 503 boundary.

AST remains in `eval()` with every parameter frozen, and embedding calls run under
`torch.inference_mode()`. No AST fine-tuning, adapters, neural classifier, or MIMII
label adaptation is performed.

## Waveform preprocessing and representation

Waveforms continue to be validated as finite mono audio and are resampled to 16 kHz
when required. V2 delegates spectrogram creation, 128-bin mel settings, length-1024
padding/truncation, and AudioSet normalization (`mean=-4.2677393`, `std=4.5689974`) to
the pinned Transformers `ASTFeatureExtractor` configuration.

The anomaly representation is the mean of the final hidden state's classification and
distillation token vectors. This produces one finite 768-value embedding per clip.
AudioSet classification logits and label probabilities are not anomaly features or
fault predictions. A real repeated MIMII clip probe produced identical `(1, 768)`
embeddings on CPU with no gradients enabled.

## Derived embedding cache

All 3,599 bearing clips were embedded once and stored in ignored
`datasets/derived/mimii_dg_bearing_ast/embeddings.npz` storage. Extraction took
3,660.661 seconds on CPU; the compressed cache is 10,254,693 bytes.

The cache pairs every embedding with its dataset-relative WAV path. Its sidecar records
the MIMII archive checksum, encoder ID and exact revision, pooling representation,
dimension, and full preprocessing identity/config. A mismatch in any metadata or path
ordering rejects the cache as stale. Filenames, paths, section/domain/split, labels,
and operating attributes are never embedding or anomaly-detector inputs.

## Normal-only protocol

The V1 split discipline is retained:

1. Section 00 normal training audio supplies 800 detector-fit and 200 threshold-
   calibration embeddings, split deterministically within section/domain groups using
   every fifth sorted clip for calibration.
2. Section 01's 200 labeled test clips evaluate the two fixed candidates and select
   their family using the harmonic mean of source ROC AUC, target ROC AUC, and
   standardized pAUC at `max_fpr=0.1`.
3. A fresh selected detector fits 1,599 Section 00+01 normal embeddings. A separate 400
   normal embeddings freeze the threshold at their linear 99th percentile.
4. Section 02 is then evaluated once as a **locked post-baseline Section 02 benchmark**.
   It is not described as a pristine V2 holdout because V1's poor Section 02 result
   motivated this representation experiment.

No anomalous MIMII clip fits scaling, PCA, covariance, a reference bank, or threshold
calibration. Section 02 labels do not affect representation, candidate selection,
parameters, promotion, or threshold.

## Section 01 model selection

| Candidate | ROC AUC | pAUC@0.1 | AP | Source AUC | Target AUC | Selection |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Cosine kNN, k=5 | 0.4918 | 0.5095 | 0.5118 | 0.4492 | 0.5336 | 0.4948 |
| Shrinkage Mahalanobis | 0.5306 | 0.5058 | 0.5349 | 0.4696 | 0.5848 | 0.5158 |
| V1 PCA reference | 0.5823 | 0.5737 | 0.6224 | 0.5196 | 0.6652 | 0.5802 |

Cosine kNN uses mean cosine distance to five L2-normalized Section 00 normal references.
Shrinkage Mahalanobis uses a normal-only `StandardScaler`, randomized PCA with the fixed
rule `min(128, fit_count-1, embedding_dimension)`, and Ledoit-Wolf covariance. No large
hyperparameter search was performed. Shrinkage Mahalanobis was selected but not
promoted because it did not beat V1 on Section 01.

The final normal-only calibration threshold is `26.887555095994728`. It was not chosen
to optimize anomaly F1.

## Locked post-baseline Section 02 benchmark

| Metric | V1 | V2 | V2 - V1 |
| --- | ---: | ---: | ---: |
| ROC AUC | 0.5213 | 0.5139 | -0.0074 |
| pAUC@0.1 | 0.5068 | 0.5037 | -0.0032 |
| Average Precision | 0.5249 | 0.5277 | +0.0029 |
| F1 | 0.3034 | 0.1217 | -0.1817 |
| Balanced accuracy | 0.4950 | 0.4950 | 0.0000 |
| Source ROC AUC | 0.5088 | 0.5224 | +0.0136 |
| Target ROC AUC | 0.5292 | 0.5056 | -0.0236 |

V2 precision is `0.4667`, recall is `0.0700`, and confusion matrix `[[TN, FP],
[FN, TP]]` is `[[92, 8], [93, 7]]`. The learned AST representation did not resolve
the cross-section/domain generalization problem. Section 02 did not trigger reselection,
retuning, promotion, or rollback because promotion had already been decided from
Section 01.

## Runtime and evidence semantics

The experimental format-2 joblib artifact is 1,084,739 bytes and references, rather
than embeds, the 346 MB frozen encoder. One warm loaded-encoder clip took approximately
1.072 seconds on this CPU host; the extraction process was observed around 936 MB
working set. These are practical observations, not a formal benchmark.

The public `AudioPredictor.predict(AudioInput) -> Prediction` contract and existing
audio HTTP endpoints are unchanged. V2's anomaly score is not a probability. The V1
empirical transformation still maps distance from the normal-only threshold to bounded
`[0, 1]` evidence on the predicted side, and Decision Engine retains
`ConfidenceKind.RAW`.

A direct non-deployed V2 prediction on
`section_02_target_test_anomaly_0044_vel_14_f-n_C.wav` returned `healthy` with raw
confidence `0.13604481661164802`. The corresponding isolated Decision Engine result
was provisional/normal with `health_score=null`, `risk_level=null`, and event order
`PredictionProduced` then `AnalysisProduced`. This miss is consistent with the weak
benchmark and is not hidden.

Audio raw evidence remains statistically different from time-series `predict_proba`.
There is no cross-modal averaging, weighting, calibration, or fusion. `acoustic_anomaly`
remains a generic abnormal finding and is never mapped to `bearing_fault`.

## Deployment limitations

- The fitted reference distribution supports the MIMII DG bearing context only; general
  AudioSet pretraining does not make it a universal industrial anomaly detector.
- Section 02 is a post-baseline comparative benchmark, not a pristine prospective V2
  holdout.
- Confidence is bounded raw empirical evidence, not probability of anomaly, failure,
  severity, health, or risk.
- No fault taxonomy, multimodal fusion, health scoring, or risk scoring is available.
- An 86.6M-parameter PyTorch AST is treated as backend/server-side inference. Raspberry
  Pi 4 deployment would require later work such as distillation, quantization, ONNX, a
  smaller encoder, or an edge/server split; none is implemented here.

Complete machine-readable results are in `evaluation/audio_v2_results.json`. The V1
history remains in `evaluation/audio_baseline_results.json` and
`docs/audio_baseline.md` without alteration.
