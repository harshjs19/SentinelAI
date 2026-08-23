import argparse
import json
import time
from pathlib import Path

import numpy as np

from modules.audio.config import AudioTrainingConfig, AudioV2TrainingConfig
from modules.audio.data import load_wav
from modules.audio.encoder import FrozenASTEncoder
from modules.audio.predictor import AudioPredictor
from modules.audio.training import evaluate_saved_audio_artifact, train_audio
from modules.audio.v2_training import evaluate_saved_audio_v2_artifact, train_audio_v2


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
    prediction = AudioPredictor(
        args.artifact,
        encoder_path=args.encoder,
        device=args.device,
    ).predict(load_wav(args.input_wav))
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


def _v2_config_from_args(args: argparse.Namespace) -> AudioV2TrainingConfig:
    defaults = AudioV2TrainingConfig()
    return AudioV2TrainingConfig(
        dataset_root=args.dataset_root,
        encoder_path=args.encoder,
        embedding_cache_path=args.embedding_cache,
        artifact_path=args.artifact,
        runtime_artifact_path=defaults.runtime_artifact_path,
        evaluation_path=getattr(args, "output", defaults.evaluation_path),
        device=args.device,
        embedding_batch_size=getattr(
            args,
            "embedding_batch_size",
            defaults.embedding_batch_size,
        ),
    )


def _train_v2(args: argparse.Namespace) -> None:
    outcome = train_audio_v2(_v2_config_from_args(args))
    selected_validation = outcome.validation_results[outcome.selected_detector]
    print(
        json.dumps(
            {
                "selected_detector": outcome.selected_detector,
                "validation_selection_score": selected_validation.selection_score,
                "promoted": outcome.promoted,
                "section_02_roc_auc": outcome.benchmark_result.roc_auc,
                "artifact": outcome.artifact_path,
                "evaluation": outcome.evaluation_path,
            },
            indent=2,
        )
    )


def _evaluate_v2(args: argparse.Namespace) -> None:
    result = evaluate_saved_audio_v2_artifact(_v2_config_from_args(args))
    print(json.dumps(result.to_dict(), indent=2))


def _validate_encoder(args: argparse.Namespace) -> None:
    audio = load_wav(args.input_wav)
    encoder = FrozenASTEncoder(args.encoder, args.device)
    started = time.perf_counter()
    first = encoder.encode_batch((audio,))
    second = encoder.encode_batch((audio,))
    print(
        json.dumps(
            {
                "input_sample_rate": audio.sample_rate,
                "embedding_shape": list(first.shape),
                "embedding_dtype": str(first.dtype),
                "finite": bool(np.isfinite(first).all()),
                "deterministic": bool(np.array_equal(first, second)),
                "device": encoder.device,
                "two_pass_seconds": time.perf_counter() - started,
                "parameters_require_grad": encoder.parameters_require_grad,
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
    predict_parser.add_argument(
        "--encoder",
        type=Path,
        default=AudioV2TrainingConfig().encoder_path,
    )
    predict_parser.add_argument("--device", default=AudioV2TrainingConfig().device)
    predict_parser.add_argument("--input-wav", type=Path, required=True)
    predict_parser.set_defaults(handler=_predict)

    v2_defaults = AudioV2TrainingConfig()
    train_v2_parser = commands.add_parser("train-v2", help="Train and evaluate Audio V2")
    train_v2_parser.add_argument("--dataset-root", type=Path, default=v2_defaults.dataset_root)
    train_v2_parser.add_argument("--encoder", type=Path, default=v2_defaults.encoder_path)
    train_v2_parser.add_argument(
        "--embedding-cache",
        type=Path,
        default=v2_defaults.embedding_cache_path,
    )
    train_v2_parser.add_argument("--artifact", type=Path, default=v2_defaults.artifact_path)
    train_v2_parser.add_argument("--output", type=Path, default=v2_defaults.evaluation_path)
    train_v2_parser.add_argument("--device", default=v2_defaults.device)
    train_v2_parser.add_argument(
        "--embedding-batch-size",
        type=int,
        default=v2_defaults.embedding_batch_size,
    )
    train_v2_parser.set_defaults(handler=_train_v2)

    evaluate_v2_parser = commands.add_parser(
        "evaluate-v2",
        help="Evaluate the saved Audio V2 artifact",
    )
    evaluate_v2_parser.add_argument(
        "--dataset-root",
        type=Path,
        default=v2_defaults.dataset_root,
    )
    evaluate_v2_parser.add_argument("--encoder", type=Path, default=v2_defaults.encoder_path)
    evaluate_v2_parser.add_argument(
        "--embedding-cache",
        type=Path,
        default=v2_defaults.embedding_cache_path,
    )
    evaluate_v2_parser.add_argument("--artifact", type=Path, default=v2_defaults.artifact_path)
    evaluate_v2_parser.add_argument("--device", default=v2_defaults.device)
    evaluate_v2_parser.set_defaults(handler=_evaluate_v2)

    validate_encoder_parser = commands.add_parser(
        "validate-encoder",
        help="Run a local real-AST embedding smoke test",
    )
    validate_encoder_parser.add_argument(
        "--encoder",
        type=Path,
        default=v2_defaults.encoder_path,
    )
    validate_encoder_parser.add_argument("--device", default=v2_defaults.device)
    validate_encoder_parser.add_argument("--input-wav", type=Path, required=True)
    validate_encoder_parser.set_defaults(handler=_validate_encoder)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    args.handler(args)


if __name__ == "__main__":
    main()
