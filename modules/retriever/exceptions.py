class CorpusValidationError(ValueError):
    """The tracked knowledge source corpus is invalid."""


class RetrievalUnavailableError(RuntimeError):
    """Required local retrieval assets are unavailable."""


class StaleKnowledgeIndexError(RetrievalUnavailableError):
    """The prepared Chroma collection does not match the current corpus."""


class InvalidEvidencePackageError(ValueError):
    """Retrieval was requested for an Evidence Package that failed integrity checks."""
