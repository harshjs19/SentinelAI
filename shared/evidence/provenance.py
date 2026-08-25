import hashlib
import re
from dataclasses import dataclass
from enum import StrEnum

from domain.enums.modality import Modality
from shared.evidence.canonical import canonical_json_bytes

_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_CONTENT_TYPE_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.+_-]*/[A-Za-z0-9][A-Za-z0-9.+_-]*$")


class SourceKind(StrEnum):
    STRUCTURED = "structured"
    FILE = "file"


@dataclass(frozen=True)
class SourceProvenance:
    modality: Modality
    source_kind: SourceKind
    sha256: str
    size_bytes: int
    content_type: str

    def __post_init__(self) -> None:
        if _SHA256_PATTERN.fullmatch(self.sha256) is None:
            raise ValueError("Source provenance sha256 must be 64 lowercase hexadecimal digits")
        if isinstance(self.size_bytes, bool) or self.size_bytes < 0:
            raise ValueError("Source provenance size_bytes cannot be negative")
        if _CONTENT_TYPE_PATTERN.fullmatch(self.content_type) is None:
            raise ValueError("Source provenance content_type must be a concise MIME-style value")


def file_source_provenance(
    modality: Modality,
    content: bytes,
    content_type: str,
) -> SourceProvenance:
    if not isinstance(content, bytes):
        raise TypeError("File source content must be exact bytes")
    return SourceProvenance(
        modality=modality,
        source_kind=SourceKind.FILE,
        sha256=hashlib.sha256(content).hexdigest(),
        size_bytes=len(content),
        content_type=content_type,
    )


def structured_source_provenance(
    modality: Modality,
    value: object,
    content_type: str = "application/json",
) -> SourceProvenance:
    content = canonical_json_bytes(value)
    return SourceProvenance(
        modality=modality,
        source_kind=SourceKind.STRUCTURED,
        sha256=hashlib.sha256(content).hexdigest(),
        size_bytes=len(content),
        content_type=content_type,
    )
