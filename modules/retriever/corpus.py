import hashlib
from dataclasses import dataclass
from pathlib import Path

from modules.retriever.chunking import ChunkingConfig, chunk_source
from modules.retriever.config import KNOWLEDGE_SCHEMA_VERSION, REPOSITORY_ROOT
from modules.retriever.manifest import load_manifest, resolve_document_path
from modules.retriever.models import EmbeddingIdentity, KnowledgeChunk, KnowledgeSource
from shared.evidence.canonical import canonical_json_bytes


@dataclass(frozen=True)
class KnowledgeCorpus:
    schema_version: str
    corpus_digest_sha256: str
    sources: tuple[KnowledgeSource, ...]
    chunks: tuple[KnowledgeChunk, ...]
    chunking: ChunkingConfig
    embedding_identity: EmbeddingIdentity


def load_corpus(
    manifest_path: Path,
    embedding_identity: EmbeddingIdentity,
    *,
    repository_root: Path = REPOSITORY_ROOT,
    chunking: ChunkingConfig = ChunkingConfig(),
) -> KnowledgeCorpus:
    sources = load_manifest(manifest_path, repository_root=repository_root)
    chunks: list[KnowledgeChunk] = []
    source_payloads: list[dict[str, object]] = []
    for source in sources:
        source_bytes = resolve_document_path(source, repository_root).read_bytes()
        source_chunks = chunk_source(source, source_bytes, config=chunking)
        chunks.extend(source_chunks)
        source_payloads.append(
            {
                "source_id": source.source_id,
                "source_digest_sha256": hashlib.sha256(source_bytes).hexdigest(),
                "title": source.title,
                "publisher": source.publisher,
                "source_uri": source.source_uri,
                "source_kind": source.source_kind,
                "document_path": source.document_path,
                "asset_type": source.asset_type,
                "fault_codes": list(source.fault_codes),
                "version": source.version,
                "license_or_usage_note": source.license_or_usage_note,
                "retrieved_at": source.retrieved_at,
                "notes": source.notes,
            }
        )
    chunks_tuple = tuple(sorted(chunks, key=lambda chunk: chunk.chunk_id))
    identity_payload = {
        "knowledge_schema_version": KNOWLEDGE_SCHEMA_VERSION,
        "sources": source_payloads,
        "chunking": {
            "strategy": "heading_aware_character_v1",
            "max_characters": chunking.max_characters,
            "overlap_characters": chunking.overlap_characters,
        },
        "embedding": {
            "model_id": embedding_identity.model_id,
            "revision": embedding_identity.revision,
            "dimension": embedding_identity.dimension,
        },
    }
    digest = hashlib.sha256(canonical_json_bytes(identity_payload)).hexdigest()
    return KnowledgeCorpus(
        schema_version=KNOWLEDGE_SCHEMA_VERSION,
        corpus_digest_sha256=digest,
        sources=sources,
        chunks=chunks_tuple,
        chunking=chunking,
        embedding_identity=embedding_identity,
    )
