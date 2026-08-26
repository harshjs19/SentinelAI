import json

import pytest

from backend.app.persistence.errors import ArtifactPersistenceIntegrityError
from backend.app.persistence.maintenance_artifact_mapper import (
    deserialize_analysis,
    deserialize_evidence_package,
    deserialize_maintenance_report,
    deserialize_retrieval_bundle,
    serialize_analysis,
    serialize_evidence_package,
    serialize_maintenance_report,
    serialize_retrieval_bundle,
    validate_artifact_chain,
)
from tests.backend.maintenance_persistence_support import make_vision_workflow_result


def test_all_maintenance_artifact_mappers_round_trip_authoritative_types() -> None:
    _, result = make_vision_workflow_result(generated=True)

    analysis = deserialize_analysis(serialize_analysis(result.analysis))
    package = deserialize_evidence_package(serialize_evidence_package(result.evidence_package))
    bundle = deserialize_retrieval_bundle(serialize_retrieval_bundle(result.retrieval_bundle))
    report = deserialize_maintenance_report(serialize_maintenance_report(result.maintenance_report))

    assert analysis == result.analysis
    assert package == result.evidence_package
    assert bundle == result.retrieval_bundle
    assert report == result.maintenance_report
    validate_artifact_chain(analysis, package, bundle, report)


def test_evidence_json_contains_only_source_provenance_not_raw_source_bytes() -> None:
    _, result = make_vision_workflow_result()

    payload = serialize_evidence_package(result.evidence_package)
    encoded = json.dumps(payload)

    assert "private fixture bytes" not in encoded
    assert set(payload["sources"][0]) == {  # type: ignore[index]
        "modality",
        "source_kind",
        "sha256",
        "size_bytes",
        "content_type",
    }


def test_non_json_object_payload_fails_closed() -> None:
    with pytest.raises(ArtifactPersistenceIntegrityError, match="not a JSON object"):
        deserialize_analysis(b"\x80pickle is not JSON")  # type: ignore[arg-type]
