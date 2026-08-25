from domain.enums.analysis_limitation import AnalysisLimitation
from domain.enums.analysis_status import AnalysisStatus
from domain.enums.condition_state import ConditionState
from modules.retriever.models import RetrievalLane, RetrievalQuery
from shared.evidence.models import EvidencePackage

_FAULT_QUERY_TEXT = {
    "bearing_fault": "bearing fault bearing condition inspection",
    "coupling_fault": "mechanical coupling condition alignment inspection",
    "bent_shaft": "rotating machinery bent shaft runout inspection",
    "eccentric_rotor": "induction motor rotor eccentricity condition inspection",
    "imbalance": "rotating machinery imbalance inspection",
    "misalignment": "shaft coupling misalignment inspection",
    "half_broken_rotor_bar": "induction motor partial broken rotor bar condition",
    "broken_rotor_bar": "induction motor broken rotor bar condition",
    "gear_wear_25": "gear tooth wear condition inspection",
    "gear_wear_50": "gear tooth wear condition inspection",
    "gear_wear_75": "gear tooth wear condition inspection",
    "acoustic_anomaly": "acoustic anomaly inspection unidentified physical fault",
    "visual_anomaly": "visual anomaly inspection unidentified physical fault",
}


class RetrievalQueryPlanner:
    """Create bounded retrieval intents from trusted Evidence Package fields only."""

    def plan(self, package: EvidencePackage) -> tuple[RetrievalQuery, ...]:
        asset_type = package.machine.asset_type
        if (
            not package.claim_support.condition_available
            or package.analysis.status is AnalysisStatus.INSUFFICIENT_EVIDENCE
        ):
            return (
                RetrievalQuery(
                    intent_id="interpretation:insufficient_evidence",
                    lane=RetrievalLane.INTERPRETATION,
                    text="insufficient evidence interpretation evidence limitations",
                    fault_code="insufficient_evidence",
                    asset_type=asset_type,
                ),
                RetrievalQuery(
                    intent_id="interpretation:evidence_limitations",
                    lane=RetrievalLane.INTERPRETATION,
                    text="SentinelAI unsupported claim boundaries evidence limitations",
                    fault_code="evidence_limitations",
                    asset_type=asset_type,
                ),
            )

        queries: list[RetrievalQuery] = []
        if package.analysis.condition is ConditionState.NORMAL:
            queries.append(
                RetrievalQuery(
                    intent_id="interpretation:healthy",
                    lane=RetrievalLane.INTERPRETATION,
                    text="normal condition healthy interpretation within validated model scope",
                    fault_code="healthy",
                    asset_type=asset_type,
                )
            )
        elif package.analysis.condition is ConditionState.ABNORMAL:
            seen_codes: set[str] = set()
            findings = package.analysis.top_findings + package.analysis.findings
            for finding in findings:
                if (
                    finding.condition is not ConditionState.ABNORMAL
                    or finding.code in seen_codes
                    or finding.code not in _FAULT_QUERY_TEXT
                ):
                    continue
                seen_codes.add(finding.code)
                queries.append(
                    RetrievalQuery(
                        intent_id=f"maintenance:{finding.code}",
                        lane=RetrievalLane.MAINTENANCE,
                        text=_FAULT_QUERY_TEXT[finding.code],
                        fault_code=finding.code,
                        asset_type=asset_type,
                    )
                )

        for model in package.models:
            queries.append(
                RetrievalQuery(
                    intent_id=f"interpretation:model_scope:{model.model_id}",
                    lane=RetrievalLane.INTERPRETATION,
                    text=(
                        f"{model.status.value} {model.modality.value} model "
                        f"validated scope {model.validated_scope}"
                    ),
                    fault_code="model_scope",
                    asset_type=asset_type,
                )
            )
            if model.status.value == "experimental":
                queries.append(
                    RetrievalQuery(
                        intent_id=f"interpretation:experimental_model:{model.model_id}",
                        lane=RetrievalLane.INTERPRETATION,
                        text=(
                            f"experimental {model.modality.value} model "
                            "maturity interpretation limitations"
                        ),
                        fault_code="experimental_model",
                        asset_type=asset_type,
                    )
                )
            queries.append(
                RetrievalQuery(
                    intent_id=f"interpretation:confidence:{model.model_id}",
                    lane=RetrievalLane.INTERPRETATION,
                    text=(
                        f"{model.modality.value} model confidence semantics "
                        f"{model.confidence_semantics}"
                    ),
                    fault_code="confidence_semantics",
                    asset_type=asset_type,
                )
            )

        if package.analysis.limitations or not all(
            (
                package.claim_support.failure_probability_available,
                package.claim_support.fault_severity_available,
                package.claim_support.operational_risk_available,
            )
        ):
            limitation_terms = " ".join(
                limitation.value
                for limitation in package.analysis.limitations
                if limitation is AnalysisLimitation.SINGLE_MODALITY_EVIDENCE
            )
            queries.append(
                RetrievalQuery(
                    intent_id="interpretation:evidence_limitations",
                    lane=RetrievalLane.INTERPRETATION,
                    text=(
                        "SentinelAI unavailable evidence claims limitations " + limitation_terms
                    ).strip(),
                    fault_code="evidence_limitations",
                    asset_type=asset_type,
                )
            )
        return _deduplicate_queries(queries)


def _deduplicate_queries(queries: list[RetrievalQuery]) -> tuple[RetrievalQuery, ...]:
    deduplicated: list[RetrievalQuery] = []
    seen: set[str] = set()
    for query in queries:
        if query.intent_id not in seen:
            seen.add(query.intent_id)
            deduplicated.append(query)
    return tuple(deduplicated)
