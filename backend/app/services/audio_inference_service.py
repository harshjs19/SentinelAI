from uuid import UUID

from domain.entities.prediction import Prediction
from domain.enums.modality import Modality
from inference.orchestrator import InferenceOrchestrator
from modules.audio.data import decode_wav


class UnsupportedAudioAssetTypeError(ValueError):
    pass


class AudioInferenceService:
    def __init__(
        self,
        orchestrator: InferenceOrchestrator,
        supported_asset_types: tuple[str, ...],
    ) -> None:
        self._orchestrator = orchestrator
        self._supported_asset_types = supported_asset_types

    def validate_asset_type(self, asset_type: str) -> None:
        if asset_type.strip().lower() not in self._supported_asset_types:
            supported = ", ".join(self._supported_asset_types)
            raise UnsupportedAudioAssetTypeError(
                f"Audio model supports these asset types: {supported}"
            )

    async def predict(self, machine_id: UUID, content: bytes) -> Prediction:
        audio = decode_wav(content)
        return await self._orchestrator.predict(machine_id, Modality.AUDIO, audio)
