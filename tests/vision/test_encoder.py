import numpy as np
import pytest

from modules.vision.encoder import VisionEncoderMetadata, VisionFeatures, validate_features


def metadata() -> VisionEncoderMetadata:
    return VisionEncoderMetadata(
        model_id="fake-resnet18",
        weights_id="fake-v1",
        weights_filename="fake.pth",
        weights_sha256="abc",
        weights_bytes=1,
        torchvision_version="test",
        global_layer="layer4",
        global_dimension=3,
        patch_layers=("layer2", "layer3"),
        patch_dimension=2,
        patch_grid=(2, 2),
        preprocessing={"canvas_size": 8},
    )


def test_validates_feature_shapes_without_mutating_arrays() -> None:
    global_embeddings = np.ones((2, 3), dtype=np.float64)
    patches = np.ones((2, 2, 2, 2), dtype=np.float64)
    original = patches.copy()

    validate_features(VisionFeatures(global_embeddings, patches), 2, metadata())

    assert np.array_equal(patches, original)


@pytest.mark.parametrize(
    "features, message",
    [
        (VisionFeatures(np.ones((1, 4)), np.ones((1, 2, 2, 2))), "global"),
        (VisionFeatures(np.ones((1, 3)), np.ones((1, 1, 2, 2))), "patch"),
        (
            VisionFeatures(np.asarray([[np.nan, 0.0, 0.0]]), np.ones((1, 2, 2, 2))),
            "non-finite",
        ),
    ],
)
def test_rejects_invalid_encoder_outputs(features: VisionFeatures, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        validate_features(features, 1, metadata())
