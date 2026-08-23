import argparse
import json
from pathlib import Path

from modules.audio.config import AudioTrainingConfig
from modules.audio.data import load_wav
from modules.audio.predictor import AudioPredictor
from modules.audio.training import evaluate_saved_audio_artifact, train_audio


def _add_common_paths(parser: argparse.ArgumentParser) -> None:
    defaults = AudioTrainingConfig()
    parser.add_argument("--dataset-root", type=Path, default=defaults.dataset_root)
    parser.add_argument("--artifact", type=Path, default=defaults.artifact_path)


def _config_from_args(args: argparse.Namespace) -> AudioTrainingConfig:
    defaults = AudioTrainingConfig()
    return AudioTrainingConfig(
        dataset_root=args.dataset_root,
        artifact_path=args.artifact,
        evaluation_path=getattr(args, "output", defaults.evaluation_path),
    )


def _train(args: argparse.Namespace) -> None:
    outcome = train_audio(_config_from_args(args))
    selected_validation = outcome.validation_results[outcome.selected_detector]
    print(
        json.dumps(
            {
                "selected_detector": outcome.selected_detector,
                "validation_selection_score": selected_validation.selection_score,
                "test_roc_auc": outcome.test_result.roc_auc,
                "artifact": outcome.artifact_path,
                "evaluation": outcome.evaluation_path,
            },
            indent=2,
        )
    )


def _evaluate(args: argparse.Namespace) -> None:
    result = evaluate_saved_audio_artifact(_config_from_args(args))
    print(json.dumps(result.to_dict(), indent=2))


def _predict(args: argparse.Namespace) -> None:
    prediction = AudioPredictor(args.artifact).predict(load_wav(args.input_wav))
    print(
        json.dumps(
            {
                "modality": prediction.modality.value,
                "label": prediction.label,
                "confidence": prediction.confidence,
            },
            indent=2,
        )
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="SentinelAI audio anomaly baseline")
    commands = parser.add_subparsers(dest="command", required=True)

    train_parser = commands.add_parser("train", help="Train and evaluate audio baselines")
    _add_common_paths(train_parser)
    train_parser.add_argument(
        "--output",
        type=Path,
        default=AudioTrainingConfig().evaluation_path,
    )
    train_parser.set_defaults(handler=_train)

    evaluate_parser = commands.add_parser("evaluate", help="Evaluate the saved audio artifact")
    _add_common_paths(evaluate_parser)
    evaluate_parser.set_defaults(handler=_evaluate)

    predict_parser = commands.add_parser("predict", help="Predict one WAV file")
    predict_parser.add_argument(
        "--artifact",
        type=Path,
        default=AudioTrainingConfig().artifact_path,
    )
    predict_parser.add_argument("--input-wav", type=Path, required=True)
    predict_parser.set_defaults(handler=_predict)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    args.handler(args)


if __name__ == "__main__":
    main()
