from abc import ABC, abstractmethod

from edge_simulator.models import EdgeObservation


class EdgeObservationSource(ABC):
    """Adapter boundary for acquiring one labelled, single-modality observation."""

    @abstractmethod
    def capture(self) -> EdgeObservation:
        """Return a validated observation without performing inference."""
