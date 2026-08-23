import hashlib
import json
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Protocol

import librosa
import numpy as np
from numpy.typing import NDArray

from modules.audio.config import (
    AST_EMBEDDING_DIMENSION,
    AST_MODEL_ID,
    AST_MODEL_LICENSE,
    AST_MODEL_REVISION,
    AST_PREPROCESSING_IDENTITY,
    AST_REPRESENTATION,
)
from modules.audio.input import AudioInput

ENCODER_IDENTITY_FILENAME = "sentinelai_encoder.json"


@dataclass(frozen=True)
class AudioEncoderMetadata:
    model_id: str
    revision: str
    license: str
    representation: str
    dimension: int
    preprocessing_identity: str
    preprocessing_config: dict[str, object]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class AudioEmbeddingEncoder(Protocol):
    @property
    def metadata(self) -> AudioEncoderMetadata: ...

    @property
    def device(self) -> str: ...

    def encode_batch(
        self,
        inputs: Sequence[AudioInput],
    ) -> NDArray[np.float64]: ...


class FrozenASTEncoder:
    def __init__(
        self,
        model_path: Path,
        device: str = "cpu",
        expected_metadata: AudioEncoderMetadata | None = None,
    ) -> None:
        try:
            import torch
            from transformers import ASTFeatureExtractor, ASTForAudioClassification
        except ImportError as error:  # pragma: no cover - dependency integrity failure
            raise RuntimeError("AST runtime dependencies are not installed") from error

        identity = load_encoder_identity(model_path)
        _verify_prepared_files(model_path, identity)
        self._metadata = _metadata_from_identity(identity)
        if expected_metadata is not None:
            validate_encoder_metadata(self._metadata, expected_metadata)

        self._device = _resolve_device(device, torch)
        self._torch = torch
        self._feature_extractor = ASTFeatureExtractor.from_pretrained(
            model_path,
            local_files_only=True,
        )
        self._model = ASTForAudioClassification.from_pretrained(
            model_path,
            local_files_only=True,
            use_safetensors=True,
        )
        self._model.requires_grad_(False)
        self._model.eval()
        self._model.to(self._device)

        actual_dimension = int(self._model.config.hidden_size)
        if actual_dimension != self._metadata.dimension:
            raise ValueError("Local AST hidden size does not match its prepared encoder identity")
        actual_preprocessing = _feature_extractor_config(self._feature_extractor)
        if actual_preprocessing != self._metadata.preprocessing_config:
            raise ValueError("Local AST preprocessing does not match its prepared encoder identity")

    @property
    def metadata(self) -> AudioEncoderMetadata:
        return self._metadata

    @property
    def device(self) -> str:
        return str(self._device)

    @property
    def parameters_require_grad(self) -> bool:
        return any(parameter.requires_grad for parameter in self._model.parameters())

    def encode_batch(
        self,
        inputs: Sequence[AudioInput],
    ) -> NDArray[np.float64]:
        if not inputs:
            raise ValueError("At least one audio input is required")

        sample_rate = int(self._metadata.preprocessing_config["sampling_rate"])
        waveforms = [_resampled_waveform(audio, sample_rate) for audio in inputs]
        extracted = self._feature_extractor(
            waveforms,
            sampling_rate=sample_rate,
            return_tensors="pt",
        )
        input_values = extracted["input_values"].to(self._device)
        with self._torch.inference_mode():
            hidden_state = self._model.audio_spectrogram_transformer(
                input_values=input_values
            ).last_hidden_state
            embeddings = hidden_state[:, :2, :].mean(dim=1)
        result = embeddings.detach().cpu().numpy().astype(np.float64, copy=False)
        _validate_embeddings(result, len(inputs), self._metadata.dimension)
        return result


def default_ast_metadata(preprocessing_config: dict[str, object]) -> AudioEncoderMetadata:
    return AudioEncoderMetadata(
        model_id=AST_MODEL_ID,
        revision=AST_MODEL_REVISION,
        license=AST_MODEL_LICENSE,
        representation=AST_REPRESENTATION,
        dimension=AST_EMBEDDING_DIMENSION,
        preprocessing_identity=AST_PREPROCESSING_IDENTITY,
        preprocessing_config=preprocessing_config,
    )


def load_encoder_identity(model_path: Path) -> dict[str, object]:
    identity_path = model_path / ENCODER_IDENTITY_FILENAME
    if not identity_path.is_file():
        raise FileNotFoundError("Prepared AST encoder identity is missing")
    try:
        identity = json.loads(identity_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as error:
        raise ValueError("Prepared AST encoder identity is invalid") from error
    if not isinstance(identity, dict):
        raise ValueError("Prepared AST encoder identity is invalid")
    return identity


def validate_encoder_metadata(
    actual: AudioEncoderMetadata,
    expected: AudioEncoderMetadata,
) -> None:
    checks = {
        "model ID": (actual.model_id, expected.model_id),
        "revision": (actual.revision, expected.revision),
        "representation": (actual.representation, expected.representation),
        "dimension": (actual.dimension, expected.dimension),
        "preprocessing identity": (
            actual.preprocessing_identity,
            expected.preprocessing_identity,
        ),
        "preprocessing config": (
            actual.preprocessing_config,
            expected.preprocessing_config,
        ),
    }
    for name, (actual_value, expected_value) in checks.items():
        if actual_value != expected_value:
            raise ValueError(f"AST encoder {name} does not match the audio artifact")


def validate_embedding_matrix(
    embeddings: NDArray[np.float64],
    expected_rows: int,
    expected_dimension: int,
) -> None:
    _validate_embeddings(embeddings, expected_rows, expected_dimension)


def ast_preprocessing_config(model_path: Path) -> dict[str, object]:
    try:
        data = json.loads((model_path / "preprocessor_config.json").read_text("utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError) as error:
        raise ValueError("AST preprocessor configuration is missing or invalid") from error
    return {
        "sampling_rate": int(data["sampling_rate"]),
        "num_mel_bins": int(data["num_mel_bins"]),
        "max_length": int(data["max_length"]),
        "do_normalize": bool(data["do_normalize"]),
        "mean": float(data["mean"]),
        "std": float(data["std"]),
        "return_attention_mask": bool(data.get("return_attention_mask", False)),
    }


def _metadata_from_identity(identity: dict[str, object]) -> AudioEncoderMetadata:
    try:
        return AudioEncoderMetadata(
            model_id=str(identity["model_id"]),
            revision=str(identity["revision"]),
            license=str(identity["license"]),
            representation=str(identity["representation"]),
            dimension=int(identity["dimension"]),
            preprocessing_identity=str(identity["preprocessing_identity"]),
            preprocessing_config=dict(identity["preprocessing_config"]),  # type: ignore[arg-type]
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("Prepared AST encoder identity is incomplete") from error


def _verify_prepared_files(model_path: Path, identity: dict[str, object]) -> None:
    try:
        files = dict(identity["files"])  # type: ignore[arg-type]
        for name in ("config.json", "preprocessor_config.json", "model.safetensors"):
            expected = dict(files[name])
            path = model_path / name
            if path.stat().st_size != int(expected["bytes"]):
                raise ValueError("Prepared AST file size does not match its identity")
            digest = hashlib.sha256()
            with path.open("rb") as file:
                for chunk in iter(lambda: file.read(1024 * 1024), b""):
                    digest.update(chunk)
            if digest.hexdigest() != str(expected["sha256"]):
                raise ValueError("Prepared AST file checksum does not match its identity")
    except FileNotFoundError as error:
        raise FileNotFoundError("Prepared AST encoder files are missing") from error
    except (KeyError, TypeError, ValueError) as error:
        if isinstance(error, ValueError) and str(error).startswith("Prepared AST file"):
            raise
        raise ValueError("Prepared AST file identity is incomplete") from error


def _feature_extractor_config(feature_extractor: object) -> dict[str, object]:
    return {
        "sampling_rate": int(feature_extractor.sampling_rate),  # type: ignore[attr-defined]
        "num_mel_bins": int(feature_extractor.num_mel_bins),  # type: ignore[attr-defined]
        "max_length": int(feature_extractor.max_length),  # type: ignore[attr-defined]
        "do_normalize": bool(feature_extractor.do_normalize),  # type: ignore[attr-defined]
        "mean": float(feature_extractor.mean),  # type: ignore[attr-defined]
        "std": float(feature_extractor.std),  # type: ignore[attr-defined]
        "return_attention_mask": bool(  # type: ignore[attr-defined]
            feature_extractor.return_attention_mask
        ),
    }


def _resampled_waveform(audio: AudioInput, sample_rate: int) -> NDArray[np.float32]:
    if audio.sample_rate == sample_rate:
        return audio.waveform
    return librosa.resample(
        audio.waveform,
        orig_sr=audio.sample_rate,
        target_sr=sample_rate,
    ).astype(np.float32, copy=False)


def _validate_embeddings(
    embeddings: NDArray[np.float64],
    expected_rows: int,
    expected_dimension: int,
) -> None:
    if embeddings.shape != (expected_rows, expected_dimension):
        raise ValueError(
            "Audio encoder produced an invalid embedding shape: "
            f"expected {(expected_rows, expected_dimension)}, got {embeddings.shape}"
        )
    if not np.isfinite(embeddings).all():
        raise ValueError("Audio encoder produced non-finite embeddings")


def _resolve_device(requested: str, torch: object) -> object:
    normalized = requested.lower()
    if normalized == "auto":
        normalized = "cuda" if torch.cuda.is_available() else "cpu"  # type: ignore[attr-defined]
    if normalized not in {"cpu", "cuda"}:
        raise ValueError("Audio encoder device must be 'cpu', 'cuda', or 'auto'")
    if normalized == "cuda" and not torch.cuda.is_available():  # type: ignore[attr-defined]
        raise RuntimeError("CUDA was requested for AST but is not available")
    return torch.device(normalized)  # type: ignore[attr-defined]
