from dataclasses import replace

from modules.retriever.chunking import ChunkingConfig, chunk_source
from modules.retriever.models import KnowledgeSource, KnowledgeSourceKind


def test_chunking_is_deterministic_heading_aware_and_preserves_metadata() -> None:
    content = b"# Topic\n\n## Scope\n\nAlpha evidence.\n\n## Limits\n\nBeta limitation."

    first = chunk_source(_source(), content)
    second = chunk_source(_source(), content)

    assert first == second
    assert first[0].chunk_id == second[0].chunk_id
    assert "# Topic" in first[0].text
    assert first[0].section == "Topic"
    assert first[0].source_id == "test_source"
    assert first[0].publisher == "SentinelAI"


def test_long_section_obeys_max_size_and_uses_overlap() -> None:
    repeated = " ".join(f"word{index}" for index in range(100))
    content = f"# Long\n\n## Detail\n\n{repeated}".encode()

    chunks = chunk_source(
        _source(),
        content,
        config=ChunkingConfig(max_characters=180, overlap_characters=30),
    )

    assert len(chunks) > 1
    assert all(len(chunk.text) <= 180 for chunk in chunks)
    assert all(chunk.section == "Detail" for chunk in chunks)
    assert set(chunks[0].text.split()) & set(chunks[1].text.split())


def test_fault_code_expansion_has_unique_ids_and_shared_source_provenance() -> None:
    source = replace(_source(), fault_codes=("broken_rotor_bar", "half_broken_rotor_bar"))

    chunks = chunk_source(source, b"# Rotor bars\n\nCondition reference.")

    assert {chunk.fault_code for chunk in chunks} == {
        "broken_rotor_bar",
        "half_broken_rotor_bar",
    }
    assert len({chunk.chunk_id for chunk in chunks}) == 2
    assert len({chunk.source_digest_sha256 for chunk in chunks}) == 1


def test_source_byte_change_changes_digest_and_chunk_identity() -> None:
    first = chunk_source(_source(), b"# Topic\n\nFirst exact bytes.")
    second = chunk_source(_source(), b"# Topic\n\nSecond exact bytes.")

    assert first[0].source_digest_sha256 != second[0].source_digest_sha256
    assert first[0].chunk_id != second[0].chunk_id


def _source() -> KnowledgeSource:
    return KnowledgeSource(
        source_id="test_source",
        title="Test title",
        publisher="SentinelAI",
        source_uri="repo://docs/test.md",
        source_kind=KnowledgeSourceKind.PROJECT_INTERNAL,
        document_path="knowledge/sources/test.md",
        asset_type="generic",
        fault_codes=("healthy",),
        version="1",
        license_or_usage_note="Test use.",
        retrieved_at="2026-08-25",
        notes="",
    )
