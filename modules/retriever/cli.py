import argparse
import json
import time
from pathlib import Path

from modules.retriever.config import (
    CHROMA_PATH,
    COLLECTION_NAME,
    EMBEDDING_DIMENSION,
    EMBEDDING_MODEL_ID,
    EMBEDDING_MODEL_PATH,
    EMBEDDING_MODEL_REVISION,
    MANIFEST_PATH,
)
from modules.retriever.corpus import load_corpus
from modules.retriever.embedding import SentenceTransformerEmbedder
from modules.retriever.models import EmbeddingIdentity
from modules.retriever.store import ChromaKnowledgeStore


def main() -> None:
    parser = argparse.ArgumentParser(description="Build or inspect SentinelAI Retriever V1")
    subparsers = parser.add_subparsers(dest="command", required=True)
    build = subparsers.add_parser("build", help="Build the prepared local Chroma index")
    build.add_argument("--manifest", type=Path, default=MANIFEST_PATH)
    build.add_argument("--chroma-path", type=Path, default=CHROMA_PATH)
    build.add_argument("--model-path", type=Path, default=EMBEDDING_MODEL_PATH)

    query = subparsers.add_parser("query", help="Run a source-attributed debug query")
    query.add_argument("--text", required=True)
    query.add_argument("--fault-code", required=True)
    query.add_argument("--asset-type", default="generic")
    query.add_argument("--chroma-path", type=Path, default=CHROMA_PATH)
    query.add_argument("--model-path", type=Path, default=EMBEDDING_MODEL_PATH)
    query.add_argument("--manifest", type=Path, default=MANIFEST_PATH)
    args = parser.parse_args()

    identity = EmbeddingIdentity(
        model_id=EMBEDDING_MODEL_ID,
        revision=EMBEDDING_MODEL_REVISION,
        dimension=EMBEDDING_DIMENSION,
    )
    embedder = SentenceTransformerEmbedder(args.model_path, identity)
    corpus = load_corpus(args.manifest, identity)
    store = ChromaKnowledgeStore(args.chroma_path, COLLECTION_NAME)

    if args.command == "build":
        started = time.perf_counter()
        embeddings = embedder.embed_documents([chunk.text for chunk in corpus.chunks])
        result = store.build(corpus, embeddings)
        print(
            json.dumps(
                {
                    "source_count": len(corpus.sources),
                    "chunk_count": result.chunk_count,
                    "corpus_digest_sha256": corpus.corpus_digest_sha256,
                    "rebuilt": result.rebuilt,
                    "build_seconds": round(time.perf_counter() - started, 6),
                    "collection_metadata": dict(result.collection_metadata),
                },
                indent=2,
                sort_keys=True,
            )
        )
        return

    store.validate_identity(
        corpus_digest_sha256=corpus.corpus_digest_sha256,
        embedding_identity=identity,
    )
    matches = store.query_tiered(
        embedder.embed_query(args.text),
        fault_code=args.fault_code,
        asset_type=args.asset_type,
        n_results=3,
        embedding_dimension=identity.dimension,
    )
    print(
        json.dumps(
            [
                {
                    "chunk_id": match.chunk.chunk_id,
                    "source_id": match.chunk.source_id,
                    "title": match.chunk.title,
                    "publisher": match.chunk.publisher,
                    "source_uri": match.chunk.source_uri,
                    "section": match.chunk.section,
                    "similarity": match.similarity,
                }
                for match in matches
            ],
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
