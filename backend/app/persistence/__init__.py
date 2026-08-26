"""Typed persistence mapping and integrity checks for maintenance artifacts."""

from backend.app.persistence.errors import (
    ArtifactIdentityConflictError,
    ArtifactPersistenceIntegrityError,
)

__all__ = [
    "ArtifactIdentityConflictError",
    "ArtifactPersistenceIntegrityError",
]
