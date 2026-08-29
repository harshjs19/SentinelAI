from pathlib import Path

from edge_simulator.models import EdgeObservation, InputLabel, Modality
from edge_simulator.sources.base import EdgeObservationSource

MAX_REPLAY_ASSET_BYTES = 25 * 1024 * 1024


class _ReplayMediaSource(EdgeObservationSource):
    modality: Modality
    content_types: dict[str, str]

    def __init__(self, asset_path: Path) -> None:
        self._asset_path = asset_path

    def capture(self) -> EdgeObservation:
        if not self._asset_path.is_file():
            raise ValueError("Replay asset was not found; check the --asset file")
        size = self._asset_path.stat().st_size
        if size == 0:
            raise ValueError("Replay asset is empty")
        if size > MAX_REPLAY_ASSET_BYTES:
            raise ValueError("Replay asset exceeds the 25 MiB simulator limit")
        content_type = self.content_types.get(self._asset_path.suffix.lower())
        if content_type is None:
            extensions = ", ".join(sorted(self.content_types))
            raise ValueError(f"Replay asset type is unsupported; expected one of: {extensions}")
        return EdgeObservation(
            modality=self.modality,
            input_label=InputLabel.RECORDED_REPLAY,
            asset_path=self._asset_path,
            content_type=content_type,
        )


class ReplayAudioSource(_ReplayMediaSource):
    modality = Modality.AUDIO
    content_types = {".wav": "audio/wav"}


class ReplayVisionSource(_ReplayMediaSource):
    modality = Modality.VISION
    content_types = {".jpeg": "image/jpeg", ".jpg": "image/jpeg", ".png": "image/png"}


class ReplayThermalSource(_ReplayMediaSource):
    modality = Modality.THERMAL
    content_types = {".jpeg": "image/jpeg", ".jpg": "image/jpeg", ".png": "image/png"}
