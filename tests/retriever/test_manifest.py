import json
from pathlib import Path

import pytest

from modules.retriever.exceptions import CorpusValidationError
from modules.retriever.manifest import load_manifest


def test_valid_manifest_is_sorted_and_uses_repository_relative_document(tmp_path: Path) -> None:
    manifest_path, entry = _valid_manifest(tmp_path)
    second = dict(entry, source_id="a_source")
    _write_manifest(manifest_path, [entry, second])

    sources = load_manifest(manifest_path, repository_root=tmp_path)

    assert [source.source_id for source in sources] == ["a_source", "test_source"]
    assert sources[0].document_path == "knowledge/sources/card.md"


def test_duplicate_source_ids_and_entries_are_rejected(tmp_path: Path) -> None:
    manifest_path, entry = _valid_manifest(tmp_path)
    _write_manifest(manifest_path, [entry, entry])

    with pytest.raises(CorpusValidationError, match="source IDs|duplicate entry"):
        load_manifest(manifest_path, repository_root=tmp_path)


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"document_path": "knowledge/sources/missing.md"}, "does not exist"),
        ({"document_path": "C:/private/card.md"}, "repository-relative"),
        ({"title": " "}, "title cannot be empty"),
        ({"publisher": ""}, "publisher cannot be empty"),
        ({"source_kind": "blog"}, "Unsupported knowledge source_kind"),
        ({"fault_codes": []}, "non-empty list"),
        ({"asset_type": "secret_machine"}, "Unsupported knowledge asset_type"),
        ({"retrieved_at": "today"}, "YYYY-MM-DD"),
    ],
)
def test_invalid_manifest_metadata_is_rejected(
    tmp_path: Path,
    change: dict[str, object],
    message: str,
) -> None:
    manifest_path, entry = _valid_manifest(tmp_path)
    _write_manifest(manifest_path, [{**entry, **change}])

    with pytest.raises(CorpusValidationError, match=message):
        load_manifest(manifest_path, repository_root=tmp_path)


def test_malformed_or_extra_metadata_is_rejected(tmp_path: Path) -> None:
    manifest_path, entry = _valid_manifest(tmp_path)
    entry["private_path"] = "C:/private"
    _write_manifest(manifest_path, [entry])

    with pytest.raises(CorpusValidationError, match="exactly"):
        load_manifest(manifest_path, repository_root=tmp_path)


def _valid_manifest(root: Path) -> tuple[Path, dict[str, object]]:
    source_dir = root / "knowledge" / "sources"
    source_dir.mkdir(parents=True)
    (source_dir / "card.md").write_text("# Test\n\nUseful text.", encoding="utf-8")
    manifest_path = source_dir / "manifest.json"
    entry: dict[str, object] = {
        "source_id": "test_source",
        "title": "Test source",
        "publisher": "SentinelAI",
        "source_uri": "repo://docs/test.md",
        "source_kind": "project_internal",
        "document_path": "knowledge/sources/card.md",
        "asset_type": "generic",
        "fault_codes": ["healthy"],
        "version": "1",
        "license_or_usage_note": "Test summary.",
        "retrieved_at": "2026-08-25",
        "notes": "",
    }
    _write_manifest(manifest_path, [entry])
    return manifest_path, entry


def _write_manifest(path: Path, entries: list[dict[str, object]]) -> None:
    path.write_text(
        json.dumps({"schema_version": "1", "sources": entries}),
        encoding="utf-8",
    )
