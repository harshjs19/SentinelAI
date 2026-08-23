from collections.abc import Sequence
from uuid import UUID, uuid4

from domain.entities.analysis import Analysis
from domain.entities.finding import Finding
from domain.entities.prediction import Prediction
from domain.enums.analysis_limitation import AnalysisLimitation
from domain.enums.analysis_status import AnalysisStatus
from domain.enums.condition_state import ConditionState
from domain.enums.confidence_kind import ConfidenceKind
from modules.decision.exceptions import DuplicateModalityPredictionError
from modules.decision.normalizer import normalize_prediction


class DecisionEngine:
    def evaluate(self, machine_id: UUID, predictions: Sequence[Prediction]) -> Analysis:
        prediction_tuple = tuple(predictions)
        self._reject_duplicate_modalities(prediction_tuple)

        findings = tuple(normalize_prediction(prediction) for prediction in prediction_tuple)
        condition = self._condition(findings)
        status = (
            AnalysisStatus.PROVISIONAL if prediction_tuple else AnalysisStatus.INSUFFICIENT_EVIDENCE
        )

        return Analysis(
            id=uuid4(),
            machine_id=machine_id,
            predictions=prediction_tuple,
            findings=findings,
            condition=condition,
            status=status,
            health_score=None,
            risk_level=None,
            limitations=self._limitations(findings),
        )

    @staticmethod
    def _reject_duplicate_modalities(predictions: tuple[Prediction, ...]) -> None:
        seen = set()
        for prediction in predictions:
            if prediction.modality in seen:
                raise DuplicateModalityPredictionError(
                    f"Multiple predictions supplied for modality: {prediction.modality.value}"
                )
            seen.add(prediction.modality)

    @staticmethod
    def _condition(findings: tuple[Finding, ...]) -> ConditionState:
        if any(finding.condition is ConditionState.ABNORMAL for finding in findings):
            return ConditionState.ABNORMAL
        if findings and all(finding.condition is ConditionState.NORMAL for finding in findings):
            return ConditionState.NORMAL
        return ConditionState.INDETERMINATE

    @staticmethod
    def _limitations(findings: tuple[Finding, ...]) -> tuple[AnalysisLimitation, ...]:
        if not findings:
            return ()

        limitations: list[AnalysisLimitation] = []
        if any(finding.confidence_kind is ConfidenceKind.RAW for finding in findings):
            limitations.append(AnalysisLimitation.UNCALIBRATED_CONFIDENCE)
        if any(finding.condition is ConditionState.ABNORMAL for finding in findings):
            limitations.append(AnalysisLimitation.FAULT_SEVERITY_UNAVAILABLE)
        limitations.append(AnalysisLimitation.RISK_CONTEXT_UNAVAILABLE)
        if len({finding.modality for finding in findings}) == 1:
            limitations.append(AnalysisLimitation.SINGLE_MODALITY_EVIDENCE)
        return tuple(limitations)
