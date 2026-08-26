class ArtifactPersistenceIntegrityError(RuntimeError):
    """Stored or supplied maintenance artifacts failed authoritative validation."""


class ArtifactIdentityConflictError(ArtifactPersistenceIntegrityError):
    """An immutable artifact identity already exists with different content."""
