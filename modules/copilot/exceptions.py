from enum import StrEnum


class CopilotInputErrorCode(StrEnum):
    INVALID_EVIDENCE_PACKAGE = "invalid_evidence_package"
    INVALID_RETRIEVAL_BUNDLE = "invalid_retrieval_bundle"
    EVIDENCE_RETRIEVAL_MISMATCH = "evidence_retrieval_mismatch"
    INCOMPLETE_CITATION_METADATA = "incomplete_citation_metadata"


_SAFE_MESSAGES = {
    CopilotInputErrorCode.INVALID_EVIDENCE_PACKAGE: (
        "Evidence Package integrity validation failed"
    ),
    CopilotInputErrorCode.INVALID_RETRIEVAL_BUNDLE: (
        "Retrieval Bundle integrity validation failed"
    ),
    CopilotInputErrorCode.EVIDENCE_RETRIEVAL_MISMATCH: (
        "Evidence Package and Retrieval Bundle do not match"
    ),
    CopilotInputErrorCode.INCOMPLETE_CITATION_METADATA: (
        "Retrieval Bundle citation metadata is incomplete"
    ),
}


class CopilotInputError(ValueError):
    def __init__(self, code: CopilotInputErrorCode) -> None:
        self.code = code
        super().__init__(_SAFE_MESSAGES[code])
