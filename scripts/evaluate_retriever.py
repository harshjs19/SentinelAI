import argparse
import json
import platform
import statistics
import time
from collections import Counter
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from uuid import UUID

from ai_core.model_capabilities import get_runtime_default_capability
from ai_core.model_provenance import snapshot_producing_model_context
from backend.app.services.evidence_package_service import EvidencePackageService
from domain.entities.analysis import Analysis
from domain.entities.finding import Finding
from domain.entities.machine import Machine
from domain.entities.prediction import Prediction
from domain.enums.analysis_limitation import AnalysisLimitation
from domain.enums.analysis_status import AnalysisStatus
from domain.enums.condition_state import ConditionState
from domain.enums.confidence_kind import ConfidenceKind
from domain.enums.modality import Modality
from modules.retriever.config import (
    CHROMA_PATH,
    COLLECTION_NAME,
    DISTANCE_METRIC,
    EMBEDDING_DIMENSION,
    EMBEDDING_MODEL_ID,
    EMBEDDING_MODEL_PATH,
    EMBEDDING_MODEL_REVISION,
    MANIFEST_PATH,
    TOP_K_PER_INTENT,
)
from modules.retriever.corpus import load_corpus
from modules.retriever.embedding import SentenceTransformerEmbedder
from modules.retriever.models import EmbeddingIdentity, retrieval_bundle_payload
from modules.retriever.planner import RetrievalQueryPlanner
from modules.retriever.retriever import KnowledgeRetriever
from modules.retriever.store import ChromaKnowledgeStore
from shared.evidence.canonical import canonical_json_bytes
from shared.evidence.models import EvidencePackage
from shared.evidence.provenance import file_source_provenance, structured_source_provenance

DEFAULT_QUERIES = Path("evaluation/retriever_queries.json")
DEFAULT_OUTPUT = Path("evaluation/retriever_baseline_results.json")


def evaluate(
    *,
    queries_path: Path,
    output_path: Path,
    model_path: Path,
    chroma_path: Path,
) -> dict[str, object]:
    benchmark = json.loads(queries_path.read_text(encoding="utf-8"))
    cases = benchmark["cases"]
    identity = EmbeddingIdentity(
        EMBEDDING_MODEL_ID,
        EMBEDDING_MODEL_REVISION,
        EMBEDDING_DIMENSION,
    )

    cold_start = time.perf_counter()
    embedder = SentenceTransformerEmbedder(model_path, identity)
    cold_initialization_seconds = time.perf_counter() - cold_start
    corpus = load_corpus(MANIFEST_PATH, identity)
    store = ChromaKnowledgeStore(chroma_path, COLLECTION_NAME)

    build_started = time.perf_counter()
    document_embeddings = embedder.embed_documents([chunk.text for chunk in corpus.chunks])
    first_build = store.build(corpus, document_embeddings)
    index_build_seconds = time.perf_counter() - build_started
    second_build = store.build(corpus, document_embeddings)

    planner = RetrievalQueryPlanner()
    retriever = KnowledgeRetriever(
        store=store,
        embedder=embedder,
        corpus_digest_sha256=corpus.corpus_digest_sha256,
        planner=planner,
    )
    embedder.embed_query("retriever warmup")
    warm_latencies: list[float] = []
    search_latencies: list[float] = []
    complete_latencies: list[float] = []
    reciprocal_ranks: list[float] = []
    top_one_hits = 0
    recall_three_hits = 0
    contamination_count = 0
    citation_fields = 0
    citation_fields_present = 0
    bundle_sizes: list[int] = []
    bundle_text_characters: list[int] = []
    bundle_chunk_counts: list[int] = []
    case_results: list[dict[str, object]] = []

    for index, case in enumerate(cases):
        package = _package_for_case(index, case["scenario"])
        planner_queries = planner.plan(package)
        target_query = next(
            query for query in planner_queries if query.fault_code == case["target_fault_code"]
        )
        embed_started = time.perf_counter()
        target_embedding = embedder.embed_query(target_query.text)
        warm_latencies.append(time.perf_counter() - embed_started)
        search_started = time.perf_counter()
        store.query_tiered(
            target_embedding,
            fault_code=target_query.fault_code,
            asset_type=target_query.asset_type,
            n_results=TOP_K_PER_INTENT,
            embedding_dimension=identity.dimension,
        )
        search_latencies.append(time.perf_counter() - search_started)

        complete_started = time.perf_counter()
        bundle = retriever.retrieve(package)
        complete_latencies.append(time.perf_counter() - complete_started)
        target_chunks = [
            chunk for chunk in bundle.chunks if chunk.matched_intent == target_query.intent_id
        ]
        expected_sources = set(case["expected_source_ids"])
        rank = next(
            (
                result_index
                for result_index, chunk in enumerate(target_chunks, start=1)
                if chunk.source_id in expected_sources
            ),
            None,
        )
        top_one_hits += int(rank == 1)
        recall_three_hits += int(rank is not None and rank <= 3)
        reciprocal_ranks.append(0.0 if rank is None else 1.0 / rank)

        query_by_intent = {query.intent_id: query for query in bundle.queries}
        contamination_count += sum(
            chunk.fault_code != query_by_intent[chunk.matched_intent].fault_code
            for chunk in bundle.chunks
        )
        for chunk in bundle.chunks:
            citation_values = (chunk.title, chunk.publisher, chunk.source_uri, chunk.section)
            citation_fields += len(citation_values)
            citation_fields_present += sum(bool(value.strip()) for value in citation_values)
        serialized = canonical_json_bytes(retrieval_bundle_payload(bundle))
        bundle_sizes.append(len(serialized))
        bundle_text_characters.append(sum(len(chunk.text) for chunk in bundle.chunks))
        bundle_chunk_counts.append(len(bundle.chunks))
        case_results.append(
            {
                "query_case_id": case["query_case_id"],
                "target_fault_code": case["target_fault_code"],
                "rank_of_expected_source": rank,
                "intents": [
                    {
                        "intent_id": query.intent_id,
                        "lane": query.lane.value,
                        "fault_code": query.fault_code,
                        "text": query.text,
                    }
                    for query in bundle.queries
                ],
                "top_target_chunks": [
                    {
                        "source_id": chunk.source_id,
                        "title": chunk.title,
                        "publisher": chunk.publisher,
                        "source_uri": chunk.source_uri,
                        "section": chunk.section,
                        "fault_code": chunk.fault_code,
                        "asset_type": chunk.asset_type,
                        "similarity": round(chunk.similarity, 6),
                    }
                    for chunk in target_chunks[:3]
                ],
                "bundle_chunk_count": len(bundle.chunks),
                "bundle_text_characters": bundle_text_characters[-1],
                "bundle_serialized_bytes": bundle_sizes[-1],
                "has_fault_specific_maintenance": any(
                    chunk.matched_intent.startswith("maintenance:") for chunk in bundle.chunks
                ),
            }
        )

    case_count = len(cases)
    prepared_identity = json.loads(
        (model_path / "retriever_encoder_identity.json").read_text(encoding="utf-8")
    )
    results: dict[str, object] = {
        "schema_version": "1",
        "benchmark_name": "SentinelAI Retriever V1 curated regression",
        "corpus": {
            "source_count": len(corpus.sources),
            "chunk_count": len(corpus.chunks),
            "source_type_counts": dict(
                sorted(Counter(source.source_kind.value for source in corpus.sources).items())
            ),
            "fault_code_coverage": sorted(
                {fault_code for source in corpus.sources for fault_code in source.fault_codes}
            ),
            "asset_type_coverage": sorted({source.asset_type for source in corpus.sources}),
            "corpus_digest_sha256": corpus.corpus_digest_sha256,
        },
        "embedding": {
            "model_id": identity.model_id,
            "revision": identity.revision,
            "dimension": identity.dimension,
            "sentence_transformers_version": version("sentence-transformers"),
            "local_assets_digest_sha256": prepared_identity["local_assets_digest_sha256"],
            "prepared_bytes": prepared_identity["total_prepared_bytes"],
            "device": "cpu",
        },
        "index": {
            "chroma_version": version("chromadb"),
            "collection_name": COLLECTION_NAME,
            "distance_metric": DISTANCE_METRIC,
            "chunking": {
                "strategy": "heading_aware_character_v1",
                "max_characters": corpus.chunking.max_characters,
                "overlap_characters": corpus.chunking.overlap_characters,
            },
            "disk_bytes": _directory_size(chroma_path),
            "build_seconds": round(index_build_seconds, 6),
            "first_build_rebuilt": first_build.rebuilt,
            "unchanged_second_build_rebuilt": second_build.rebuilt,
            "unchanged_second_build_chunk_count": second_build.chunk_count,
            "collection_metadata": store.metadata(),
        },
        "metrics": {
            "query_case_count": case_count,
            "top_1_expected_topic_accuracy": top_one_hits / case_count,
            "recall_at_3": recall_three_hits / case_count,
            "mean_reciprocal_rank": statistics.fmean(reciprocal_ranks),
            "citation_completeness": citation_fields_present / citation_fields,
            "cross_fault_contamination_count": contamination_count,
        },
        "latency_seconds": {
            "cold_embedder_initialization": round(cold_initialization_seconds, 6),
            "warm_query_embedding_mean": round(statistics.fmean(warm_latencies), 6),
            "chroma_search_mean": round(statistics.fmean(search_latencies), 6),
            "complete_retrieval_bundle_mean": round(statistics.fmean(complete_latencies), 6),
        },
        "typical_bundle": {
            "median_chunk_count": statistics.median(bundle_chunk_counts),
            "median_text_characters": statistics.median(bundle_text_characters),
            "median_serialized_bytes": statistics.median(bundle_sizes),
        },
        "environment": {
            "platform": platform.platform(),
            "processor": platform.processor() or "not reported by platform",
            "python": platform.python_version(),
        },
        "cases": case_results,
        "known_limitations": [
            "Small manually curated English-only corpus.",
            "No general web search or live source refresh.",
            "No cross-encoder reranker or LLM query rewriting.",
            "Curated regression benchmark is not a production retrieval benchmark.",
            "Semantic embeddings can rank imperfectly; restrictive metadata filters "
            "limit contamination.",
            "Retrieved knowledge does not validate or expand upstream model predictions.",
        ],
    }
    output_path.write_text(json.dumps(results, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return results


def _package_for_case(index: int, scenario: dict[str, object]) -> EvidencePackage:
    machine_id = UUID(int=1000 + index)
    machine = Machine(
        machine_id,
        f"Retriever benchmark {index + 1}",
        str(scenario["asset_type"]),
    )
    finding_code = scenario["finding_code"]
    modality = Modality(str(scenario["modality"]))
    created_at = datetime(2026, 8, 25, 12, index, tzinfo=UTC)
    if finding_code is None:
        analysis = Analysis(
            id=UUID(int=2000 + index),
            machine_id=machine_id,
            predictions=(),
            findings=(),
            condition=ConditionState.INDETERMINATE,
            status=AnalysisStatus.INSUFFICIENT_EVIDENCE,
            health_score=None,
            risk_level=None,
            limitations=(),
            created_at=created_at,
        )
        return EvidencePackageService().build(machine, analysis, [])

    code = str(finding_code)
    condition = ConditionState.NORMAL if code == "healthy" else ConditionState.ABNORMAL
    prediction = Prediction(modality, code, 0.8)
    finding = Finding(modality, code, condition, 0.8, ConfidenceKind.RAW)
    limitations = [
        AnalysisLimitation.UNCALIBRATED_CONFIDENCE,
        AnalysisLimitation.RISK_CONTEXT_UNAVAILABLE,
        AnalysisLimitation.SINGLE_MODALITY_EVIDENCE,
    ]
    if condition is ConditionState.ABNORMAL:
        limitations.insert(1, AnalysisLimitation.FAULT_SEVERITY_UNAVAILABLE)
    analysis = Analysis(
        id=UUID(int=2000 + index),
        machine_id=machine_id,
        predictions=(prediction,),
        findings=(finding,),
        condition=condition,
        status=AnalysisStatus.PROVISIONAL,
        health_score=None,
        risk_level=None,
        limitations=tuple(limitations),
        created_at=created_at,
    )
    if modality is Modality.TIMESERIES:
        source = structured_source_provenance(modality, {"samples": [{"value": 1.0}]})
    else:
        content_types = {
            Modality.AUDIO: "audio/wav",
            Modality.VISION: "image/png",
            Modality.THERMAL: "image/png",
        }
        source = file_source_provenance(
            modality,
            b"synthetic public benchmark evidence",
            content_types[modality],
        )
    return EvidencePackageService().build(
        machine,
        analysis,
        [source],
        producing_models=(
            snapshot_producing_model_context(get_runtime_default_capability(modality)),
        ),
    )


def _directory_size(path: Path) -> int:
    return sum(file.stat().st_size for file in path.rglob("*") if file.is_file())


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate the real Retriever V1 baseline")
    parser.add_argument("--queries", type=Path, default=DEFAULT_QUERIES)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--model-path", type=Path, default=EMBEDDING_MODEL_PATH)
    parser.add_argument("--chroma-path", type=Path, default=CHROMA_PATH)
    args = parser.parse_args()
    results = evaluate(
        queries_path=args.queries,
        output_path=args.output,
        model_path=args.model_path,
        chroma_path=args.chroma_path,
    )
    print(json.dumps(results["metrics"], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
