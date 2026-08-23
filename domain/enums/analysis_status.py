from enum import StrEnum


class AnalysisStatus(StrEnum):
    COMPLETE = "complete"
    PROVISIONAL = "provisional"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
