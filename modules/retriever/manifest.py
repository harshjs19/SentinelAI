import json
from datetime import date
from pathlib import Path, PurePosixPath, PureWindowsPath
from urllib.parse import urlparse

from modules.retriever.config import (
    KNOWLEDGE_SCHEMA_VERSION,
    REPOSITORY_ROOT,
    SUPPORTED_ASSET_TYPES,
    SUPPORTED_FAULT_CODES,
)
from modules.retriever.exceptions import CorpusValidationError
from modules.retriever.models import KnowledgeSource, KnowledgeSourceKind

_SOURCE_FIELDS = {
    "source_id",
    "title",
    "publisher",
    "source_uri",
    "source_kind",
    "document_path",
    "asset_type",
    "fault_codes",
    "version",
    "license_or_usage_note",
    "retrieved_at",
    "notes",
}


def load_manifest(
    manifest_path: Path,
    *,
    repository_root: Path = REPOSITORY_ROOT,
) -> tuple[KnowledgeSource, ...]:
    try:
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CorpusValidationError(f"Cannot read knowledge manifest: {exc}") from exc

    if not isinstance(raw, dict) or set(raw) != {"schema_version", "sources"}:
        raise CorpusValidationError("Manifest must contain only schema_version and sources")
    if raw["schema_version"] != KNOWLEDGE_SCHEMA_VERSION:
        raise CorpusValidationError(
            f"Knowledge manifest schema_version must be {KNOWLEDGE_SCHEMA_VERSION}"
        )
    entries = raw["sources"]
    if not isinstance(entries, list) or not entries:
        raise CorpusValidationError("Knowledge manifest sources must be a non-empty list")

    sources = tuple(_parse_source(entry, repository_root=repository_root) for entry in entries)
    source_ids = [source.source_id for source in sources]
    if len(set(source_ids)) != len(source_ids):
        raise CorpusValidationError("Knowledge source IDs must be unique")
    if len({json.dumps(entry, sort_keys=True) for entry in entries}) != len(entries):
        raise CorpusValidationError("Knowledge manifest contains a duplicate entry")
    return tuple(sorted(sources, key=lambda source: source.source_id))


def resolve_document_path(source: KnowledgeSource, repository_root: Path) -> Path:
    return repository_root / PurePosixPath(source.document_path)


def _parse_source(entry: object, *, repository_root: Path) -> KnowledgeSource:
    if not isinstance(entry, dict) or set(entry) != _SOURCE_FIELDS:
        raise CorpusValidationError(
            "Each source entry must contain exactly the documented manifest fields"
        )

    strings: dict[str, str] = {}
    for field in _SOURCE_FIELDS - {"fault_codes"}:
        value = entry[field]
        if not isinstance(value, str):
            raise CorpusValidationError(f"Knowledge source {field} must be a string")
        if field not in {"notes"} and not value.strip():
            raise CorpusValidationError(f"Knowledge source {field} cannot be empty")
        strings[field] = value.strip()

    try:
        source_kind = KnowledgeSourceKind(strings["source_kind"])
    except ValueError as exc:
        raise CorpusValidationError("Unsupported knowledge source_kind") from exc

    fault_codes = entry["fault_codes"]
    if not isinstance(fault_codes, list) or not fault_codes:
        raise CorpusValidationError("Knowledge source fault_codes must be a non-empty list")
    if not all(isinstance(code, str) and code.strip() for code in fault_codes):
        raise CorpusValidationError("Knowledge source fault_codes must contain non-empty strings")
    normalized_fault_codes = tuple(sorted(code.strip() for code in fault_codes))
    if len(set(normalized_fault_codes)) != len(normalized_fault_codes):
        raise CorpusValidationError("Knowledge source fault_codes cannot contain duplicates")
    unsupported = set(normalized_fault_codes) - SUPPORTED_FAULT_CODES
    if unsupported:
        raise CorpusValidationError(f"Unsupported knowledge fault_code: {sorted(unsupported)[0]}")

    asset_type = strings["asset_type"]
    if asset_type not in SUPPORTED_ASSET_TYPES:
        raise CorpusValidationError(f"Unsupported knowledge asset_type: {asset_type}")

    document_path = strings["document_path"]
    _validate_document_path(document_path, repository_root)
    _validate_source_uri(strings["source_uri"], source_kind)
    try:
        date.fromisoformat(strings["retrieved_at"])
    except ValueError as exc:
        raise CorpusValidationError("Knowledge source retrieved_at must be YYYY-MM-DD") from exc

    return KnowledgeSource(
        source_id=strings["source_id"],
        title=strings["title"],
        publisher=strings["publisher"],
        source_uri=strings["source_uri"],
        source_kind=source_kind,
        document_path=document_path,
        asset_type=asset_type,
        fault_codes=normalized_fault_codes,
        version=strings["version"],
        license_or_usage_note=strings["license_or_usage_note"],
        retrieved_at=strings["retrieved_at"],
        notes=strings["notes"],
    )


def _validate_document_path(value: str, repository_root: Path) -> None:
    posix = PurePosixPath(value)
    windows = PureWindowsPath(value)
    if (
        "\\" in value
        or posix.is_absolute()
        or windows.is_absolute()
        or windows.drive
        or ".." in posix.parts
        or posix.parts[:2] != ("knowledge", "sources")
        or posix.suffix.lower() != ".md"
    ):
        raise CorpusValidationError(
            "Knowledge document_path must be a repository-relative knowledge/sources/*.md path"
        )
    document = repository_root / posix
    if not document.is_file():
        raise CorpusValidationError(f"Knowledge source file does not exist: {value}")
    try:
        content = document.read_bytes()
    except OSError as exc:
        raise CorpusValidationError(f"Cannot read knowledge source file: {value}") from exc
    if not content.strip():
        raise CorpusValidationError(f"Knowledge source file cannot be empty: {value}")


def _validate_source_uri(value: str, source_kind: KnowledgeSourceKind) -> None:
    parsed = urlparse(value)
    if source_kind is KnowledgeSourceKind.EXTERNAL_AUTHORITATIVE:
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise CorpusValidationError("External source_uri must be an absolute HTTP(S) URL")
    elif not value.startswith("repo://") or not parsed.netloc:
        raise CorpusValidationError("Internal source_uri must use the repo:// convention")
