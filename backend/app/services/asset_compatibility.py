def ensure_supported_asset_type(
    asset_type: str,
    supported_asset_types: tuple[str, ...],
    model_name: str,
    error_type: type[ValueError],
) -> None:
    if asset_type.strip().lower() not in supported_asset_types:
        supported = ", ".join(supported_asset_types)
        raise error_type(f"{model_name} model supports these asset types: {supported}")
