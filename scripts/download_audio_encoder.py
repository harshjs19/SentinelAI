import argparse
import hashlib
import json
from pathlib import Path

import transformers
from huggingface_hub import HfApi, snapshot_download

from modules.audio.config import (
    AST_EMBEDDING_DIMENSION,
    AST_MODEL_ID,
    AST_MODEL_REVISION,
)
from modules.audio.encoder import (
    ENCODER_IDENTITY_FILENAME,
    ast_preprocessing_config,
    default_ast_metadata,
)

EXPECTED_SAFETENSORS_SHA256 = "ae0c1e2ad4e1381d851fa9bf298ba13ebc9c5a914cdee2dbe427a6583869924d"
REQUIRED_FILES = ("config.json", "preprocessor_config.json", "model.safetensors")


def prepare_audio_encoder(destination: Path) -> dict[str, object]:
    resolved_revision = (
        HfApi()
        .model_info(
            AST_MODEL_ID,
            revision=AST_MODEL_REVISION,
        )
        .sha
    )
    if resolved_revision != AST_MODEL_REVISION:
        raise ValueError("Hugging Face resolved an unexpected AST revision")

    snapshot_download(
        repo_id=AST_MODEL_ID,
        revision=AST_MODEL_REVISION,
        local_dir=destination,
        allow_patterns=list(REQUIRED_FILES),
    )

    config = json.loads((destination / "config.json").read_text(encoding="utf-8"))
    if config.get("architectures") != ["ASTForAudioClassification"]:
        raise ValueError("Downloaded model is not the expected AST architecture")
    if int(config.get("hidden_size", 0)) != AST_EMBEDDING_DIMENSION:
        raise ValueError("Downloaded AST has an unexpected hidden size")

    files = {
        name: {
            "bytes": (destination / name).stat().st_size,
            "sha256": _sha256(destination / name),
        }
        for name in REQUIRED_FILES
    }
    if files["model.safetensors"]["sha256"] != EXPECTED_SAFETENSORS_SHA256:
        raise ValueError("Downloaded AST safetensors checksum does not match")

    encoder = default_ast_metadata(ast_preprocessing_config(destination))
    identity = {
        **encoder.to_dict(),
        "checkpoint_format": "safetensors",
        "transformers_version_at_preparation": transformers.__version__,
        "files": files,
        "total_prepared_bytes": sum(int(file["bytes"]) for file in files.values()),
    }
    destination.mkdir(parents=True, exist_ok=True)
    (destination / ENCODER_IDENTITY_FILENAME).write_text(
        json.dumps(identity, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return identity


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare the pinned frozen AST encoder")
    parser.add_argument(
        "--destination",
        type=Path,
        default=Path("models/pretrained/ast-audioset"),
    )
    args = parser.parse_args()
    print(json.dumps(prepare_audio_encoder(args.destination), indent=2))


if __name__ == "__main__":
    main()
