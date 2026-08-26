from collections.abc import Sequence

from ai_core.model_provenance import ProducingModelContext
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


class ProducingModelProvenanceUnavailable(RuntimeError):
    pass


class EvidencePackageService:
    """Package already-produced evidence without inference, decisions, I/O, or persistence."""

    def build(
        self,
        machine: Machine,
        analysis: Analysis,
        sources: Sequence[SourceProvenance],
        *,
        producing_models: Sequence[ProducingModelContext] = (),
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

        model_contexts = tuple(producing_models)
        model_modalities = [context.modality for context in model_contexts]
        if len(set(model_modalities)) != len(model_modalities):
            raise ValueError("Duplicate producing-model context modality")
        prediction_modality_set = set(prediction_modalities)
        model_modality_set = set(model_modalities)
        if not model_contexts and prediction_modalities:
            raise ProducingModelProvenanceUnavailable(
                "Exact producing-model provenance is required for evidence-bearing Analysis"
            )
        missing = prediction_modality_set - model_modality_set
        extra = model_modality_set - prediction_modality_set
        if missing and extra:
            raise ValueError("Producing-model context modalities must match Analysis predictions")
        if missing:
            missing_names = ", ".join(sorted(modality.value for modality in missing))
            raise ProducingModelProvenanceUnavailable(
                f"Exact producing-model provenance unavailable for: {missing_names}"
            )
        if extra:
            raise ValueError("Producing-model contexts contain modalities absent from Analysis")

        analysis_snapshot = snapshot_analysis(analysis)
        model_provenance = tuple(snapshot_model(context) for context in model_contexts)
        return create_evidence_package(
            machine=snapshot_machine(machine),
            analysis=analysis_snapshot,
            sources=source_tuple,
            models=model_provenance,
            claim_support=claim_support_for_analysis(analysis_snapshot),
        )
