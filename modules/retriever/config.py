from pathlib import Path

KNOWLEDGE_SCHEMA_VERSION = "1"
RETRIEVAL_BUNDLE_SCHEMA_VERSION = "1"
COLLECTION_NAME = "sentinelai_maintenance_v1"
DISTANCE_METRIC = "cosine"

EMBEDDING_MODEL_ID = "sentence-transformers/all-MiniLM-L6-v2"
EMBEDDING_MODEL_REVISION = "1110a243fdf4706b3f48f1d95db1a4f5529b4d41"
EMBEDDING_DIMENSION = 384

CHUNK_MAX_CHARACTERS = 1200
CHUNK_OVERLAP_CHARACTERS = 120
TOP_K_PER_INTENT = 3
MAXIMUM_TOTAL_CHUNKS = 8

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
KNOWLEDGE_ROOT = REPOSITORY_ROOT / "knowledge"
MANIFEST_PATH = KNOWLEDGE_ROOT / "sources" / "manifest.json"
CHROMA_PATH = KNOWLEDGE_ROOT / "chroma"
EMBEDDING_MODEL_PATH = KNOWLEDGE_ROOT / "embeddings" / "all-MiniLM-L6-v2"

SUPPORTED_ASSET_TYPES = frozenset(
    {
        "generic",
        "bearing",
        "pcb1",
        "rotating_electromechanical_system",
    }
)

SUPPORTED_FAULT_CODES = frozenset(
    {
        "acoustic_anomaly",
        "bearing_fault",
        "bent_shaft",
        "blocked_multimodal_fusion",
        "broken_rotor_bar",
        "confidence_semantics",
        "coupling_fault",
        "eccentric_rotor",
        "evidence_limitations",
        "experimental_model",
        "gear_wear_25",
        "gear_wear_50",
        "gear_wear_75",
        "half_broken_rotor_bar",
        "healthy",
        "imbalance",
        "insufficient_evidence",
        "misalignment",
        "model_scope",
        "visual_anomaly",
    }
)
