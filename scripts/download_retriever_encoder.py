import argparse
import hashlib
import json
from importlib.metadata import version
from pathlib import Path

from huggingface_hub import HfApi, snapshot_download

from modules.retriever.config import (
    EMBEDDING_DIMENSION,
    EMBEDDING_MODEL_ID,
    EMBEDDING_MODEL_PATH,
    EMBEDDING_MODEL_REVISION,
)

IDENTITY_FILENAME = "retriever_encoder_identity.json"
REQUIRED_PATTERNS = (
    "1_Pooling/config.json",
    "README.md",
    "config.json",
    "config_sentence_transformers.json",
    "model.safetensors",
    "modules.json",
    "sentence_bert_config.json",
    "special_tokens_map.json",
    "tokenizer.json",
    "tokenizer_config.json",
    "vocab.txt",
)


def prepare_retriever_encoder(destination: Path) -> dict[str, object]:
    resolved_revision = (
        HfApi()
        .model_info(
            EMBEDDING_MODEL_ID,
            revision=EMBEDDING_MODEL_REVISION,
        )
        .sha
    )
    if resolved_revision != EMBEDDING_MODEL_REVISION:
        raise ValueError("Hugging Face resolved an unexpected retriever encoder revision")

    snapshot_download(
        repo_id=EMBEDDING_MODEL_ID,
        revision=EMBEDDING_MODEL_REVISION,
        local_dir=destination,
        allow_patterns=list(REQUIRED_PATTERNS),
    )
    config = json.loads((destination / "config.json").read_text(encoding="utf-8"))
    if int(config.get("hidden_size", 0)) != EMBEDDING_DIMENSION:
        raise ValueError("Downloaded retriever encoder has an unexpected hidden size")

    prepared_files = sorted(
        path
        for path in destination.rglob("*")
        if path.is_file()
        and IDENTITY_FILENAME not in path.name
        and ".cache" not in path.relative_to(destination).parts
    )
    files = {
        path.relative_to(destination).as_posix(): {
            "bytes": path.stat().st_size,
            "sha256": _sha256(path),
        }
        for path in prepared_files
    }
    checksum_payload = [
        {
            "path": relative_path,
            "bytes": metadata["bytes"],
            "sha256": metadata["sha256"],
        }
        for relative_path, metadata in files.items()
    ]
    identity = {
        "model_id": EMBEDDING_MODEL_ID,
        "revision": EMBEDDING_MODEL_REVISION,
        "sentence_transformers_version": version("sentence-transformers"),
        "embedding_dimension": EMBEDDING_DIMENSION,
        "files": files,
        "local_assets_digest_sha256": hashlib.sha256(
            json.dumps(
                checksum_payload,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest(),
        "total_prepared_bytes": sum(int(metadata["bytes"]) for metadata in files.values()),
    }
    (destination / IDENTITY_FILENAME).write_text(
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
    parser = argparse.ArgumentParser(description="Prepare the pinned Retriever V1 encoder")
    parser.add_argument(
        "--destination",
        type=Path,
        default=EMBEDDING_MODEL_PATH,
    )
    args = parser.parse_args()
    print(json.dumps(prepare_retriever_encoder(args.destination), indent=2))


if __name__ == "__main__":
    main()
