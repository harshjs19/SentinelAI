from uuid import UUID

from backend.app.services.asset_compatibility import ensure_supported_asset_type
from domain.enums.modality import Modality
from inference.orchestrator import InferenceOrchestrator
from inference.result import InferenceResult
from modules.vision.preprocessing import decode_image


class UnsupportedVisionAssetTypeError(ValueError):
    pass


class VisionInferenceService:
    def __init__(
        self,
        orchestrator: InferenceOrchestrator,
        supported_asset_types: tuple[str, ...],
    ) -> None:
        self._orchestrator = orchestrator
        self._supported_asset_types = supported_asset_types

    def validate_asset_type(self, asset_type: str) -> None:
        ensure_supported_asset_type(
            asset_type,
            self._supported_asset_types,
            "Vision",
            UnsupportedVisionAssetTypeError,
        )

    async def predict(self, machine_id: UUID, content: bytes) -> InferenceResult:
        image = decode_image(content)
        return await self._orchestrator.predict(machine_id, Modality.VISION, image)
