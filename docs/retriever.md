# Knowledge Base and Retriever V1

## Purpose and trust boundary

Retriever V1 answers: "Which verified maintenance or interpretive knowledge is relevant
to the evidence SentinelAI already produced?" It never decides what is wrong with a
machine. The deterministic path is:

```text
EvidencePackage -> RetrievalQueryPlanner -> KnowledgeRetriever -> RetrievalBundle
    -> future Maintenance Copilot
```

`EvidencePackage` remains the evidence boundary. Retrieval validates its digest and uses
only its machine snapshot, Analysis, model provenance, claim-support flags, and
limitations. It does not reopen raw sensor/media data, predictors, model artifacts, or
datasets. It does not modify evidence, run a Decision Engine, call an LLM, synthesize a
diagnosis, or generate a maintenance instruction.

There is no public retrieval API, EventBus event/subscriber, PostgreSQL model, startup
hook, or automatic index build. Existing health, machine, inference, capability, and
Alembic paths do not import or initialize the encoder or Chroma.

## Rebuildable knowledge corpus

Only entries in `knowledge/sources/manifest.json` are ingested. Each entry records:

- stable `source_id`, title, publisher, and source URI;
- `source_kind` (`external_authoritative` or `project_internal`);
- repository-relative Markdown `document_path` and scalar `asset_type`;
- one or more canonical `fault_codes` expanded to one filterable code per chunk;
- version, usage/licensing note, retrieval date, and curation notes.

External cards are concise SentinelAI-authored paraphrases of authoritative OEM,
government, standards-catalogue, or peer-reviewed sources. Third-party manuals, tables,
figures, and PDFs are not copied into the repository. Internal cards curate exact
semantics from tracked SentinelAI documents rather than blindly indexing the repository.
[Knowledge source provenance](knowledge_sources.md) records the curation audit.

The exact UTF-8 Markdown bytes are SHA-256 hashed. This digest identifies SentinelAI's
project-authored representation; it does not authenticate the third-party publication.

## Deterministic chunking and corpus identity

`heading_aware_character_v1` preserves Markdown headings and paragraphs. A card at or
below 1,200 characters remains intact. Longer cards are grouped at heading boundaries;
an individual oversized section is split deterministically at paragraph/word boundaries
with a 120-character overlap. Chunk identity derives from source ID, exact source digest,
fault code, asset type, section, and chunk index—never `uuid4()`.

When one card covers several model codes, equivalent chunk records receive one scalar
`fault_code` each. This keeps Chroma filters simple without merging runtime labels. The
current corpus has 13 sources (six external, seven internal), 28 expanded chunks, and
full coverage of the declared V1 fault and interpretation codes.

The corpus digest hashes a canonical representation of schema version, sorted source
identities/digests and metadata, chunking configuration, and embedding identity. Current
corpus digest:

```text
e39bf83004c75b71fd09e0221941823d989b1661668a37cade519431a14c59fb
```

## Explicit offline embedding

The embedding abstraction is `TextEmbedder`, with separate document and query methods.
Production uses `SentenceTransformerEmbedder`; ordinary tests use an eight-dimensional
deterministic fake. Chroma never receives a default embedding function.

V1 pins:

- model: `sentence-transformers/all-MiniLM-L6-v2`;
- Hugging Face revision: `1110a243fdf4706b3f48f1d95db1a4f5529b4d41`;
- dimension: 384;
- prepared SentenceTransformers version: 5.7.0;
- local asset digest: `4827adf7fa3e57011cc56ace0835d4c142fae764205cfb56a78a8b4651281d67`.

Prepare assets explicitly:

```shell
uv run python -m scripts.download_retriever_encoder
```

The preparation script verifies the resolved commit, downloads only required model and
tokenizer files, records per-file SHA-256 values, and writes an ignored local identity.
Normal loading uses `local_files_only=True`. Missing or mismatched local assets raise a
clear internal availability error and never trigger a query-time download.

## Chroma search index

`ChromaKnowledgeStore` is the only Chroma-facing component. It uses an explicit
`PersistentClient`, one stable collection named `sentinelai_maintenance_v1`, and HNSW
cosine distance. Code computes document/query embeddings before calling Chroma.

Collection metadata records corpus digest, embedding model/revision/dimension, schema,
distance metric, source count, and chunk count. A corpus or embedding mismatch makes
retrieval fail stale; an explicit build clears and rebuilds the small collection. An
unchanged build upserts deterministic IDs, produces no duplicates, and leaves the
collection identity unchanged.

Build and inspect explicitly:

```shell
uv run python -m modules.retriever.cli build
uv run python -m modules.retriever.cli query --text "bearing fault inspection" --fault-code bearing_fault --asset-type bearing
```

Chroma distance uses `1 - cosine_similarity`; Retriever reports
`similarity = 1 - distance`, bounded to `[-1, 1]` only for floating-point noise. This is
retrieval similarity—not confidence, source correctness, fault probability, severity,
health, risk, or urgency.

The generated `knowledge/chroma/` directory is ignored. Chroma is a rebuildable search
index, not authoritative knowledge, Evidence Package persistence, audit storage, or a
transactional source of truth. Markdown plus manifest are the tracked source corpus.

## Deterministic query planner

The planner produces compact explicit intents from trusted fields. It never reads raw
source payloads or injects evaluation metrics.

The maintenance lane is available only for abnormal supported findings. Explicit code
mapping turns, for example, `bearing_fault` into bearing-condition inspection terms and
`misalignment` into shaft/coupling-alignment terms. `visual_anomaly` and
`acoustic_anomaly` receive only anomaly-specific interpretation/inspection queries with
an unidentified physical fault; neither can become a bearing or other diagnosis.

The interpretation lane retrieves model scope, lifecycle maturity, confidence semantics,
and evidence limitations. Experimental status adds maturity context without suppressing
supported fault knowledge. A normal Analysis adds only normal/model interpretation—never
an abnormal maintenance intent. An insufficient-evidence Analysis adds only insufficient
evidence and limitations intents.

Unavailable claim support is enforced before search. Queries never ask for failure
probability, fault severity, or operational risk when those claims are absent. Retrieval
does not reconstruct health, risk, severity, or probability indirectly.

## Filtering, ranking, and bounds

Each intent is searched in deterministic metadata tiers:

1. exact `fault_code` plus exact machine `asset_type`;
2. exact `fault_code` plus `asset_type = generic`;
3. separate generic interpretation intents only.

Unrelated fault codes are never admitted through embedding similarity. Within a tier,
results rank by cosine similarity, then exact ties by source ID and chunk ID. No learned
reranker or hand-built score bonus exists. Defaults are three chunks per intent and eight
total chunks. Repeated chunk IDs retain their best-ranked occurrence; final order follows
intent order, similarity, source ID, and chunk ID.

## Citation-ready immutable output

Every frozen `RetrievedChunk` contains chunk/source identity, source digest, title,
publisher, source URI, section, bounded text, scalar fault/asset metadata, similarity,
and matched intent. A future consumer can cite a result without reopening Chroma.

The frozen `RetrievalBundle` records schema version, Evidence Package ID/full digest,
corpus digest, embedding model/revision, collection name, planned queries, retrieved
chunks, and a deterministic SHA-256 digest over its canonical core. It contains no Chroma
client/path, encoder/model object, file-system source path, raw samples/media, base64, or
model-cache path.

Tampered Evidence Packages are rejected before planning or embedding. The digest is an
integrity check, not a digital signature or proof that the prediction is true.

## Internal regression baseline

`evaluation/retriever_queries.json` defines 11 synthetic EvidencePackage scenarios. The
real pinned encoder and local Chroma baseline in
`evaluation/retriever_baseline_results.json` achieved:

- Top-1 expected-topic accuracy: 1.0;
- Recall@3: 1.0;
- mean reciprocal rank: 1.0;
- citation completeness: 1.0;
- cross-fault contamination: 0.

Run the real benchmark explicitly:

```shell
uv run python -m scripts.evaluate_retriever
```

On the recorded Windows CPU run, cold encoder initialization was 7.316 s, mean warm query
embedding was 8.641 ms, mean Chroma search was 2.925 ms, and mean complete bundle
construction was 54.307 ms. The median bundle held five chunks, 5,313 text characters,
and 9,773 serialized bytes. These are local measurements, not production service-level
objectives.

## Limitations and future contract

- The V1 corpus is small, manually curated, and English-only.
- There is no general web search, live source refresh, or persisted retrieval history.
- There is no cross-encoder reranker, LLM rewriting, or production retrieval benchmark.
- Semantic embeddings can rank imperfectly; restrictive metadata filtering is deliberate.
- External source availability can change.
- Retrieved information does not validate or expand an upstream prediction or model scope.
- CORA fusion remains blocked; retrieval does not resume it.
- No Maintenance Copilot exists yet. A future Copilot may consume `RetrievalBundle` as
  deterministic grounding but must retain all evidence and citation boundaries.

Evidence Package V1 has one provenance limitation: it resolves model provenance from the
runtime-default capability for each prediction modality. Rebuilding historical packages
after runtime defaults change could therefore misattribute the producing model. Retriever
V1 does not reconstruct historical packages or change Prediction/domain identity; future
persistence/runtime provenance must resolve that before historical reconstruction.
