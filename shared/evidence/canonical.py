import json
import math
from collections.abc import Mapping
from dataclasses import is_dataclass
from datetime import UTC, datetime
from enum import Enum
from uuid import UUID


def utc_datetime_string(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Canonical datetimes must be timezone-aware")
    normalized = value.astimezone(UTC)
    return normalized.isoformat(timespec="microseconds").replace("+00:00", "Z")


def canonical_json_bytes(value: object) -> bytes:
    """Serialize using SentinelAI V1 canonical JSON rules, not RFC 8785/JCS."""
    normalized = _normalize(value)
    return json.dumps(
        normalized,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _normalize(value: object) -> object:
    if value is None:
        return value
    if isinstance(value, Enum):
        return _normalize(value.value)
    if isinstance(value, bool | int | str):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("Canonical JSON does not support NaN or Infinity")
        return value
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        return utc_datetime_string(value)
    if isinstance(value, Mapping):
        normalized: dict[str, object] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError("Canonical JSON object keys must be strings")
            normalized[key] = _normalize(item)
        return normalized
    if isinstance(value, list | tuple):
        return [_normalize(item) for item in value]
    if is_dataclass(value):
        raise TypeError("Dataclasses require an explicit Evidence Package serialization")
    raise TypeError(f"Unsupported canonical JSON value type: {type(value).__name__}")
