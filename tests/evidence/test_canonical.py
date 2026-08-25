import hashlib
import math
from dataclasses import FrozenInstanceError, dataclass
from datetime import UTC, datetime, timedelta, timezone
from uuid import UUID

import pytest

from domain.enums.modality import Modality
from shared.evidence.canonical import canonical_json_bytes
from shared.evidence.provenance import (
    SourceKind,
    SourceProvenance,
    file_source_provenance,
    structured_source_provenance,
)


def test_canonical_json_sorts_object_keys_preserves_lists_and_uses_utf8() -> None:
    first = {"z": [2, 1], "name": "café", "nested": {"b": True, "a": None}}
    second = {"nested": {"a": None, "b": True}, "name": "café", "z": [2, 1]}

    assert canonical_json_bytes(first) == canonical_json_bytes(second)
    assert canonical_json_bytes(first) == (
        b'{"name":"caf\xc3\xa9","nested":{"a":null,"b":true},"z":[2,1]}'
    )
    assert canonical_json_bytes({"z": [1, 2]}) != canonical_json_bytes({"z": [2, 1]})


def test_canonical_json_normalizes_supported_identity_and_time_values() -> None:
    identifier = UUID("00000000-0000-0000-0000-000000000123")
    local_time = datetime(
        2026, 8, 25, 14, 0, 1, 2345, tzinfo=timezone(timedelta(hours=5, minutes=30))
    )

    result = canonical_json_bytes(
        {"id": identifier, "modality": Modality.THERMAL, "when": local_time}
    )

    assert result == (
        b'{"id":"00000000-0000-0000-0000-000000000123",'
        b'"modality":"thermal","when":"2026-08-25T08:30:01.002345Z"}'
    )


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_canonical_json_rejects_non_finite_numbers(value: float) -> None:
    with pytest.raises(ValueError, match="NaN or Infinity"):
        canonical_json_bytes({"value": value})


def test_canonical_json_rejects_naive_datetime_non_string_keys_and_arbitrary_dataclass() -> None:
    @dataclass(frozen=True)
    class Unsupported:
        value: int

    with pytest.raises(ValueError, match="timezone-aware"):
        canonical_json_bytes(datetime(2026, 8, 25))
    with pytest.raises(TypeError, match="object keys must be strings"):
        canonical_json_bytes({1: "not allowed"})
    with pytest.raises(TypeError, match="explicit Evidence Package serialization"):
        canonical_json_bytes(Unsupported(1))


def test_file_source_hashes_the_exact_bytes_without_retaining_them() -> None:
    first_content = b"same bytes\x00\xff"
    second_content = b"different bytes\x00\xff"

    first = file_source_provenance(Modality.AUDIO, first_content, "audio/wav")
    repeated = file_source_provenance(Modality.AUDIO, first_content, "audio/wav")
    different = file_source_provenance(Modality.AUDIO, second_content, "audio/wav")

    assert first == repeated
    assert first.source_kind is SourceKind.FILE
    assert first.sha256 == hashlib.sha256(first_content).hexdigest()
    assert first.size_bytes == len(first_content)
    assert first.sha256 != different.sha256
    assert not hasattr(first, "content")
    with pytest.raises(FrozenInstanceError):
        first.size_bytes = 1  # type: ignore[misc]


def test_structured_source_hash_uses_canonical_json_bytes() -> None:
    first = structured_source_provenance(
        Modality.TIMESERIES,
        {"samples": [{"b": 2.0, "a": 1.0}, {"a": 3.0}]},
    )
    reordered_keys = structured_source_provenance(
        Modality.TIMESERIES,
        {"samples": [{"a": 1.0, "b": 2.0}, {"a": 3.0}]},
    )
    reordered_list = structured_source_provenance(
        Modality.TIMESERIES,
        {"samples": [{"a": 3.0}, {"a": 1.0, "b": 2.0}]},
    )

    assert first == reordered_keys
    assert first.source_kind is SourceKind.STRUCTURED
    assert first.content_type == "application/json"
    assert first.sha256 != reordered_list.sha256


def test_structured_source_rejects_non_finite_sample_values() -> None:
    with pytest.raises(ValueError, match="NaN or Infinity"):
        structured_source_provenance(Modality.TIMESERIES, {"samples": [math.nan]})


def test_canonical_utc_datetime_keeps_fixed_microseconds() -> None:
    result = canonical_json_bytes(datetime(2026, 8, 25, 8, 30, tzinfo=UTC))

    assert result == b'"2026-08-25T08:30:00.000000Z"'


def test_source_provenance_rejects_path_like_content_type() -> None:
    with pytest.raises(ValueError, match="MIME-style"):
        SourceProvenance(
            modality=Modality.VISION,
            source_kind=SourceKind.FILE,
            sha256="0" * 64,
            size_bytes=10,
            content_type="D:\\uploads\\sample.png",
        )
