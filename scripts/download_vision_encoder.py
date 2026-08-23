import argparse
import hashlib
import json
import shutil
import urllib.request
from pathlib import Path

import torchvision

from modules.vision.config import (
    RESNET_MODEL_ID,
    RESNET_WEIGHTS_BYTES,
    RESNET_WEIGHTS_FILENAME,
    RESNET_WEIGHTS_ID,
    RESNET_WEIGHTS_URL,
    VisionPreprocessingConfig,
)
from modules.vision.encoder import ENCODER_IDENTITY_FILENAME, preprocessing_metadata


def prepare_resnet18(model_path: Path) -> dict[str, object]:
    model_path.mkdir(parents=True, exist_ok=True)
    weights_path = model_path / RESNET_WEIGHTS_FILENAME
    temporary = weights_path.with_suffix(weights_path.suffix + ".part")
    if not weights_path.is_file() or weights_path.stat().st_size != RESNET_WEIGHTS_BYTES:
        with urllib.request.urlopen(RESNET_WEIGHTS_URL, timeout=60) as response:
            with temporary.open("wb") as output:
                shutil.copyfileobj(response, output, length=1024 * 1024)
        if temporary.stat().st_size != RESNET_WEIGHTS_BYTES:
            raise ValueError("Downloaded ResNet-18 weights have an unexpected size")
        temporary.replace(weights_path)

    checksum = _sha256(weights_path)
    identity = {
        "model_id": RESNET_MODEL_ID,
        "weights_id": RESNET_WEIGHTS_ID,
        "weights_url": RESNET_WEIGHTS_URL,
        "weights_filename": RESNET_WEIGHTS_FILENAME,
        "weights_sha256": checksum,
        "weights_bytes": weights_path.stat().st_size,
        "torchvision_version": torchvision.__version__,
        "global_layer": "layer4_adaptive_average_pool",
        "global_dimension": 512,
        "patch_layers": ["layer2", "layer3"],
        "patch_alignment": "adaptive_average_pool_layer2_to_layer3_grid_then_concatenate",
        "patch_dimension": 384,
        "patch_grid": [16, 16],
        "preprocessing": preprocessing_metadata(VisionPreprocessingConfig()),
        "classification_logits_used": False,
    }
    (model_path / ENCODER_IDENTITY_FILENAME).write_text(
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
    parser = argparse.ArgumentParser(description="Prepare frozen ResNet-18 Vision weights")
    parser.add_argument(
        "--model-path",
        type=Path,
        default=Path("models/pretrained/resnet18"),
    )
    args = parser.parse_args()
    print(json.dumps(prepare_resnet18(args.model_path), indent=2))


if __name__ == "__main__":
    main()
