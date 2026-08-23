# Time-series fault-classification baseline

## Dataset

The baseline uses the Bently Nevada System1 recordings from the University of
Tennessee Advanced Systems Lab dataset:

- Repository: `UTK-ASL/Dataset_digital_twin_predictive_maintenance`
- Pinned revision: `6376d4acaccc95472e22e5c44ce9ee2d35b28c89`
- Related paper: Williams et al., *Cross-domain digital twin architecture for
  predictive maintenance via machine learning and Large Language Models*, 2026,
  <https://doi.org/10.1016/j.cie.2026.111914>

The upstream README calls the dataset MIT-licensed, while the repository's actual
`LICENSE` file contains Apache License 2.0. SentinelAI treats the LICENSE file as
authoritative. The source dataset remains under ignored `datasets/` storage and is
not redistributed.

Download the pinned revision:

```shell
uv run python -m scripts.download_utk_dataset
```

## Discovered structure

The seven files under `BentlyNevada_System1/CombinedFiles` contain 21,137 raw rows.
Rows sharing a minute timestamp are aggregated into measurement windows.

| Recording | Raw rows | Windows | Label |
| --- | ---: | ---: | --- |
| Baseline 1 | 2,965 | 251 | `healthy` |
| Baseline 2 | 2,973 | 241 | `healthy` |
| Bent shaft | 2,898 | 241 | `bent_shaft` |
| Eccentric rotor | 3,403 | 290 | `eccentric_rotor` |
| Faulted bearing | 2,380 | 191 | `bearing_fault` |
| Faulted coupling | 2,098 | 117 | `coupling_fault` |
| Imbalance | 4,420 | 246 | `imbalance` |

The 38 coupling rows without timestamps are discarded, leaving 1,577 windows.
The two baseline recordings are merged because the dataset documentation identifies
both as repeat measurements of healthy operation.

## Features and leakage controls

Each window contains the mean and sample standard deviation of these six channel-1
measurements:

- bias
- derived peak
- direct
- direct RMS
- velocity peak
- velocity RMS

Missing values are median-imputed inside the fitted sklearn pipeline. Logistic
regression also standardizes features inside that pipeline.

The following fields are deliberately excluded:

- `status`, because it is the target;
- timestamps and source filenames, because they identify the condition/session;
- `volts`, because all bearing rows use 45 V and every other condition uses 50 V;
- channel-2 fields, because channel 2 exactly duplicates channel 1 in every row of
  four recordings but is independent in the other three recordings.

The data is not randomly split by row. Within every recording, complete timestamp
windows are assigned to blocked chronological train, validation, and test partitions
at 60/20/20 boundaries. Five windows are purged after each boundary. This prevents
same-minute samples from crossing partitions and reduces leakage from neighboring
measurements.

There is only one recording for each fault class. A session-held-out multiclass test
would therefore remove that class from training entirely. The chronological split is
the strongest evaluation that retains every class, but it measures later-window
generalization within known recording sessions rather than generalization to new
machines or new fault sessions.

## Training and results

Train logistic-regression and random-forest baselines, select by validation macro F1,
refit a fresh selected pipeline on the combined train and validation partitions,
evaluate it once on the test partition, and save that exact tested pipeline:

```shell
uv run python -m modules.timeseries.cli train
```

Validation macro F1:

- Logistic regression: `1.0000`
- Random forest: `0.9731`

Logistic regression was selected. Held-out test metrics:

- Accuracy: `0.9404`
- Balanced accuracy: `0.9445`
- Macro precision: `0.9414`
- Macro recall: `0.9445`
- Macro F1: `0.9418`

After model-family selection, a fresh logistic-regression pipeline was fitted on the
943 training and 279 validation windows before this test evaluation.

Full parameters, per-class metrics, class counts, and the confusion matrix are stored
in `evaluation/timeseries_baseline_results.json`. The generated inference pipeline is
stored at `models/timeseries_fault_classifier.joblib`; model binaries and their local
metadata remain ignored by Git.

Reproduce evaluation of the saved artifact:

```shell
uv run python -m modules.timeseries.cli evaluate
```

Run inference on the first timestamp window in a source recording:

```shell
uv run python -m modules.timeseries.cli predict \
  --input-csv datasets/utk_digital_twin_predictive_maintenance/data/BentlyNevada_System1/CombinedFiles/Combined_FaultedBearing.csv
```

The pinned dataset produces a `bearing_fault` time-series `Prediction` with confidence
approximately `0.9951` for that sample window.

`Prediction.confidence` currently contains the classifier's raw `predict_proba` output.
Probability calibration is intentionally deferred to SentinelAI's later Decision Engine
layer.

## Limitations

- Data comes from one laboratory test bed with short, steady-state sessions.
- Five fault classes have only one recording each, so unseen-session evaluation is not
  currently possible.
- Minute timestamps contain multiple measurements without sub-minute ordering.
- Results should not be interpreted as cross-machine or production performance.
