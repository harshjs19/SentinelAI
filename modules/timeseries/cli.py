import argparse
import json
from pathlib import Path

import pandas as pd

from modules.timeseries.config import TimeseriesTrainingConfig
from modules.timeseries.data import extract_window_features
from modules.timeseries.predictor import TimeseriesPredictor
from modules.timeseries.training import evaluate_saved_artifact, train_timeseries


def _add_common_paths(parser: argparse.ArgumentParser) -> None:
    defaults = TimeseriesTrainingConfig()
    parser.add_argument("--dataset-root", type=Path, default=defaults.dataset_root)
    parser.add_argument("--artifact", type=Path, default=defaults.artifact_path)


def _config_from_args(args: argparse.Namespace) -> TimeseriesTrainingConfig:
    defaults = TimeseriesTrainingConfig()
    return TimeseriesTrainingConfig(
        dataset_root=args.dataset_root,
        artifact_path=args.artifact,
        evaluation_path=getattr(args, "output", defaults.evaluation_path),
    )


def _train(args: argparse.Namespace) -> None:
    outcome = train_timeseries(_config_from_args(args))
    print(
        json.dumps(
            {
                "selected_model": outcome.selected_model,
                "validation_macro_f1": outcome.validation_results[outcome.selected_model].macro_f1,
                "test_macro_f1": outcome.test_result.macro_f1,
                "artifact": outcome.artifact_path,
                "evaluation": outcome.evaluation_path,
            },
            indent=2,
        )
    )


def _evaluate(args: argparse.Namespace) -> None:
    result = evaluate_saved_artifact(_config_from_args(args))
    print(json.dumps(result.to_dict(), indent=2))


def _predict(args: argparse.Namespace) -> None:
    frame = pd.read_csv(args.input_csv)
    if "timestamp" not in frame:
        raise ValueError("Input CSV must contain a timestamp column")
    timestamps = pd.to_datetime(frame["timestamp"], errors="coerce")
    if timestamps.notna().sum() == 0:
        raise ValueError("Input CSV does not contain a valid timestamp")
    first_timestamp = timestamps.dropna().iloc[0]
    window = frame.loc[timestamps == first_timestamp]
    features = extract_window_features(window)
    prediction = TimeseriesPredictor(args.artifact).predict(features)
    print(
        json.dumps(
            {
                "modality": prediction.modality.value,
                "label": prediction.label,
                "confidence": prediction.confidence,
                "timestamp": first_timestamp.isoformat(),
            },
            indent=2,
        )
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="SentinelAI time-series baseline")
    commands = parser.add_subparsers(dest="command", required=True)

    train_parser = commands.add_parser("train", help="Train baselines and save the selected model")
    _add_common_paths(train_parser)
    train_parser.add_argument(
        "--output",
        type=Path,
        default=TimeseriesTrainingConfig().evaluation_path,
    )
    train_parser.set_defaults(handler=_train)

    evaluate_parser = commands.add_parser(
        "evaluate", help="Evaluate the saved model on the test split"
    )
    _add_common_paths(evaluate_parser)
    evaluate_parser.set_defaults(handler=_evaluate)

    predict_parser = commands.add_parser(
        "predict", help="Predict the first timestamp window in a CSV"
    )
    predict_parser.add_argument(
        "--artifact", type=Path, default=TimeseriesTrainingConfig().artifact_path
    )
    predict_parser.add_argument("--input-csv", type=Path, required=True)
    predict_parser.set_defaults(handler=_predict)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    args.handler(args)


if __name__ == "__main__":
    main()
