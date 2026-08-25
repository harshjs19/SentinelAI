from collections.abc import Sequence

from ai_core.model_capabilities import get_runtime_default_capability
from domain.entities.analysis import Analysis
from domain.entities.machine import Machine
from shared.evidence.models import (
    EvidencePackage,
    claim_support_for_analysis,
    create_evidence_package,
    snapshot_analysis,
    snapshot_machine,
    snapshot_model,
)
from shared.evidence.provenance import SourceProvenance


class EvidencePackageService:
    """Package already-produced evidence without inference, decisions, I/O, or persistence."""

    def build(
        self,
        machine: Machine,
        analysis: Analysis,
        sources: Sequence[SourceProvenance],
    ) -> EvidencePackage:
        if machine.id != analysis.machine_id:
            raise ValueError("Machine ID must match Analysis machine_id")

        prediction_modalities = [prediction.modality for prediction in analysis.predictions]
        if len(set(prediction_modalities)) != len(prediction_modalities):
            raise ValueError("Analysis contains duplicate prediction modalities")

        source_tuple = tuple(sources)
        source_modalities = [source.modality for source in source_tuple]
        if len(set(source_modalities)) != len(source_modalities):
            raise ValueError("Duplicate source provenance modality")
        if set(source_modalities) != set(prediction_modalities):
            raise ValueError("Source provenance modalities must match Analysis predictions")

        analysis_snapshot = snapshot_analysis(analysis)
        model_provenance = tuple(
            snapshot_model(get_runtime_default_capability(modality))
            for modality in sorted(set(prediction_modalities), key=lambda item: item.value)
        )
        return create_evidence_package(
            machine=snapshot_machine(machine),
            analysis=analysis_snapshot,
            sources=source_tuple,
            models=model_provenance,
            claim_support=claim_support_for_analysis(analysis_snapshot),
        )
