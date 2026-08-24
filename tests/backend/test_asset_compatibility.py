import pytest

from backend.app.services.asset_compatibility import ensure_supported_asset_type


class UnsupportedTestAssetTypeError(ValueError):
    pass


def test_asset_compatibility_normalizes_a_supported_type() -> None:
    ensure_supported_asset_type(
        "  BEARING  ",
        ("bearing",),
        "Audio",
        UnsupportedTestAssetTypeError,
    )


def test_asset_compatibility_preserves_public_error_contract() -> None:
    with pytest.raises(
        UnsupportedTestAssetTypeError,
        match="^Audio model supports these asset types: bearing, pump$",
    ):
        ensure_supported_asset_type(
            "fan",
            ("bearing", "pump"),
            "Audio",
            UnsupportedTestAssetTypeError,
        )
