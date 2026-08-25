import hashlib
import re
from dataclasses import dataclass

from modules.retriever.config import CHUNK_MAX_CHARACTERS, CHUNK_OVERLAP_CHARACTERS
from modules.retriever.models import KnowledgeChunk, KnowledgeSource
from shared.evidence.canonical import canonical_json_bytes

_HEADING_PATTERN = re.compile(r"^(#{1,2})\s+(.+?)\s*$", re.MULTILINE)


@dataclass(frozen=True)
class ChunkingConfig:
    max_characters: int = CHUNK_MAX_CHARACTERS
    overlap_characters: int = CHUNK_OVERLAP_CHARACTERS

    def __post_init__(self) -> None:
        if self.max_characters <= 0:
            raise ValueError("Chunk max_characters must be positive")
        if not 0 <= self.overlap_characters < self.max_characters:
            raise ValueError("Chunk overlap must be non-negative and smaller than max size")


def chunk_source(
    source: KnowledgeSource,
    source_bytes: bytes,
    *,
    config: ChunkingConfig = ChunkingConfig(),
) -> tuple[KnowledgeChunk, ...]:
    source_digest = hashlib.sha256(source_bytes).hexdigest()
    text = source_bytes.decode("utf-8").strip()
    sections = _heading_aware_segments(text, config)
    chunks: list[KnowledgeChunk] = []
    for fault_code in source.fault_codes:
        for chunk_index, (section, chunk_text) in enumerate(sections):
            identity = {
                "source_id": source.source_id,
                "source_digest_sha256": source_digest,
                "fault_code": fault_code,
                "asset_type": source.asset_type,
                "section": section,
                "chunk_index": chunk_index,
            }
            digest = hashlib.sha256(canonical_json_bytes(identity)).hexdigest()
            chunks.append(
                KnowledgeChunk(
                    chunk_id=f"kch1_{digest[:40]}",
                    source_id=source.source_id,
                    source_digest_sha256=source_digest,
                    title=source.title,
                    publisher=source.publisher,
                    source_uri=source.source_uri,
                    section=section,
                    text=chunk_text,
                    asset_type=source.asset_type,
                    fault_code=fault_code,
                    source_kind=source.source_kind,
                    license_or_usage_note=source.license_or_usage_note,
                    chunk_index=chunk_index,
                    document_version=source.version,
                )
            )
    return tuple(chunks)


def _heading_aware_segments(
    text: str,
    config: ChunkingConfig,
) -> tuple[tuple[str, str], ...]:
    title_match = re.search(r"^#\s+(.+?)\s*$", text, re.MULTILINE)
    title = title_match.group(1) if title_match else "Document"
    if len(text) <= config.max_characters:
        return ((title, text),)

    matches = list(_HEADING_PATTERN.finditer(text))
    blocks: list[tuple[str, str]] = []
    for index, match in enumerate(matches):
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        section = match.group(2)
        block = text[start:end].strip()
        if match.group(1) == "#" and len(block) < config.max_characters // 4:
            continue
        blocks.append((section, block))
    if not blocks:
        blocks = [(title, text)]

    small_blocks: list[tuple[str, str]] = []
    segments: list[tuple[str, str]] = []
    for section, block in blocks:
        if len(block) <= config.max_characters:
            small_blocks.append((section, block))
        else:
            segments.extend(
                (section, part)
                for part in _split_with_overlap(
                    block,
                    max_characters=config.max_characters,
                    overlap_characters=config.overlap_characters,
                )
            )
    return tuple(_pack_blocks(small_blocks, config.max_characters) + segments)


def _pack_blocks(
    blocks: list[tuple[str, str]],
    max_characters: int,
) -> list[tuple[str, str]]:
    groups: list[list[tuple[str, str]]] = []
    current: list[tuple[str, str]] = []
    for block in blocks:
        candidate = current + [block]
        if current and len(_joined_text(candidate)) > max_characters:
            groups.append(current)
            current = [block]
        else:
            current = candidate
    if current:
        groups.append(current)

    if len(groups) > 1 and len(_joined_text(groups[-1])) < max_characters // 2:
        while len(groups[-2]) > 1:
            moved = groups[-2][-1]
            candidate = [moved] + groups[-1]
            if len(_joined_text(candidate)) > max_characters:
                break
            groups[-2].pop()
            groups[-1] = candidate
            if len(_joined_text(groups[-1])) >= max_characters // 2:
                break

    return [
        (
            " / ".join(block[0] for block in group),
            _joined_text(group),
        )
        for group in groups
    ]


def _joined_text(blocks: list[tuple[str, str]]) -> str:
    return "\n\n".join(block[1] for block in blocks)


def _split_with_overlap(
    text: str,
    *,
    max_characters: int,
    overlap_characters: int,
) -> tuple[str, ...]:
    parts: list[str] = []
    start = 0
    while start < len(text):
        hard_end = min(start + max_characters, len(text))
        end = hard_end
        if hard_end < len(text):
            search_start = start + max_characters // 2
            paragraph_end = text.rfind("\n\n", search_start, hard_end)
            word_end = text.rfind(" ", search_start, hard_end)
            end = max(paragraph_end, word_end)
            if end <= start:
                end = hard_end
        part = text[start:end].strip()
        if part:
            parts.append(part)
        if end >= len(text):
            break
        next_start = max(0, end - overlap_characters)
        if next_start <= start:
            next_start = end
        start = next_start
    return tuple(parts)
