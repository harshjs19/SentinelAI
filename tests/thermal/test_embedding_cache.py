from pathlib import Path

import numpy as np
import pytest

import modules.thermal.embedding_cache as cache_module
from modules.thermal.data import ThermalExperiment
from modules.thermal.embedding_cache import load_or_extract_embeddings
from modules.thermal.input import ThermalInput
from modules.vision.encoder import VisionEncoderMetadata


def encoder_metadata() -> VisionEncoderMetadata:
    return VisionEncoderMetadata(
        model_id="fake-resnet18",
        weights_id="fake-v1",
        weights_filename="fake.pth",
        weights_sha256="abc",
        weights_bytes=1,
        torchvision_version="test",
        global_layer="layer4_pool",
        global_dimension=512,
        patch_layers=("layer2", "layer3"),
        patch_dimension=384,
        patch_grid=(16, 16),
        preprocessing={"canvas_size": 256},
        classification_logits_used=False,
    )


class FakeEncoder:
    metadata = encoder_metadata()
    device = "cpu"

    def __init__(self) -> None:
        self.calls = 0

    def encode_batch(self, inputs: tuple[ThermalInput, ...]) -> np.ndarray:
        self.calls += 1
        embeddings = np.zeros((len(inputs), 512), dtype=np.float64)
        for row, image in enumerate(inputs):
            embeddings[row, 0] = image.pixels.mean()
        return embeddings


def test_cache_keeps_filename_label_and_speed_outside_embedding_vector(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path.resolve()
    experiments = (
        ThermalExperiment(root / "H_F5_S.mat", "H", "healthy", "F5", 300),
        ThermalExperiment(
            root / "BD_F15_S.mat",
            "BD",
            "bearing_fault",
            "F15",
            900,
        ),
    )
    frames = {
        "H_F5_S": (ThermalInput(np.full((4, 5, 3), 10, dtype=np.uint8)),),
        "BD_F15_S": (ThermalInput(np.full((4, 5, 3), 20, dtype=np.uint8)),),
    }
    manifest = {
        "files": [
            {"filename": item.path.name, "checksum_algorithm": "MD5", "checksum": "abc"}
            for item in experiments
        ]
    }
    monkeypatch.setattr(cache_module, "_load_manifest", lambda _: manifest)
    monkeypatch.setattr(cache_module, "discover_experiments", lambda _: experiments)
    monkeypatch.setattr(
        cache_module,
        "load_thermal_frames",
        lambda path: frames[path.stem],
    )
    cache_path = root / "embeddings.npz"
    encoder = FakeEncoder()

    extracted = load_or_extract_embeddings(root, cache_path, encoder, batch_size=2)
    cached = load_or_extract_embeddings(root, cache_path, FakeEncoder(), batch_size=2)

    assert extracted.embeddings.shape == (2, 512)
    assert extracted.embeddings[:, 0].tolist() == [10.0, 20.0]
    assert np.count_nonzero(extracted.embeddings[:, 1:]) == 0
    assert extracted.labels.tolist() == ["healthy", "bearing_fault"]
    assert extracted.speeds.tolist() == ["F5", "F15"]
    assert extracted.relative_files.tolist() == ["H_F5_S.mat", "BD_F15_S.mat"]
    assert encoder.calls == 2
    assert not extracted.cache_hit
    assert cached.cache_hit
