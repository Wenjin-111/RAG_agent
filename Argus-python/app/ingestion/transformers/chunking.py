import re
import logging
from dataclasses import dataclass
from typing import List, Optional
from langchain_core.documents import Document

logger = logging.getLogger(__name__)

BLANK_LINES = re.compile(r"\n\s*\n+")
HEADING = re.compile(r"(?m)^(#{1,6})\s+(.+)$")
SENTENCE_BREAK = re.compile(r"[。！？；!?;]\s*")
CODE_FENCE = re.compile(r"^```", re.MULTILINE)

STRATEGY = "structure-aware-token-budget-v1"
CHARS_PER_TOKEN = 3.5


@dataclass
class ChunkingConfig:
    target_tokens: int = 240
    max_tokens: int = 320
    overlap_tokens: int = 32


@dataclass
class Section:
    start: int
    end: int
    title: str


@dataclass
class ChunkRange:
    start: int
    end: int
    heading_path: str


class StructureAwareChunkTransformer:
    TOKEN_DIVISOR = 4  # rough estimate

    def __init__(self, config: ChunkingConfig | None = None):
        self.config = config or ChunkingConfig()

    def transform(self, documents: List[Document]) -> List[Document]:
        chunks = []
        for doc in documents:
            chunks.extend(self._chunk_document(doc))
        return chunks

    def _chunk_document(self, document: Document) -> List[Document]:
        text = document.page_content
        if not text or not text.strip():
            return []

        sections = self._split_by_sections(text)
        ranges = []
        for section in sections:
            ranges.extend(self._split_section(text, section))

        return self._build_documents(document, text, ranges)

    def _split_by_sections(self, text: str) -> List[Section]:
        headings = []
        for m in HEADING.finditer(text):
            headings.append((m.start(), m.group()))

        if not headings:
            return [Section(0, len(text), "")]

        sections = []
        if headings[0][0] > 0:
            sections.append(Section(0, headings[0][0], ""))

        for i, (start, title) in enumerate(headings):
            end = headings[i + 1][0] if i + 1 < len(headings) else len(text)
            sections.append(Section(start, end, title))

        return sections

    def _split_section(self, text: str, section: Section) -> List[ChunkRange]:
        section_text = text[section.start:section.end]
        segments = self._split_by_structural_boundaries(section_text)

        # Split oversized segments by sentences
        pieces = []
        for seg in segments:
            seg_len = len(seg)
            if seg_len > self.config.max_tokens * CHARS_PER_TOKEN:
                pieces.extend(self._split_by_sentences(seg))
            else:
                pieces.append(seg)

        # Greedy merge with overlap
        ranges = self._greedy_merge(pieces, section)
        return ranges

    def _split_by_structural_boundaries(self, text: str) -> list[str]:
        """Split by blank lines (paragraphs), respecting code fences."""
        in_fence = False
        segments = []
        current = []

        for line in text.split("\n"):
            if CODE_FENCE.match(line):
                in_fence = not in_fence
            current.append(line)
            if not in_fence and line.strip() == "":
                if current:
                    segments.append("\n".join(current))
                    current = []

        if current:
            segments.append("\n".join(current))

        # Merge short segments
        return self._merge_short_segments(segments)

    def _merge_short_segments(self, segments: list[str]) -> list[str]:
        result = []
        pending = ""
        for seg in segments:
            if len(pending) + len(seg) < self.config.target_tokens * CHARS_PER_TOKEN:
                pending += "\n" + seg if pending else seg
            else:
                if pending:
                    result.append(pending)
                pending = seg
        if pending:
            result.append(pending)
        return result if result else segments

    def _split_by_sentences(self, text: str) -> list[str]:
        result = []
        start = 0
        for m in SENTENCE_BREAK.finditer(text):
            end = m.end()
            result.append(text[start:end])
            start = end
        if start < len(text):
            result.append(text[start:])
        return result if result else [text]

    def _greedy_merge(self, pieces: list[str], section: Section) -> List[ChunkRange]:
        target = self.config.target_tokens * CHARS_PER_TOKEN
        max_len = self.config.max_tokens * CHARS_PER_TOKEN
        overlap = self.config.overlap_tokens * CHARS_PER_TOKEN

        ranges = []
        offset = section.start
        current_start = 0
        current_len = 0

        for piece in pieces:
            piece_len = len(piece)
            if current_len + piece_len > max_len and current_len > 0:
                ranges.append(ChunkRange(
                    start=offset + current_start,
                    end=offset + current_start + current_len,
                    heading_path=section.title,
                ))
                # back-walk for overlap
                overlap_start = int(max(0, current_start + current_len - overlap))
                current_start = overlap_start
                current_len = 0

            current_len += piece_len

        if current_len > 0:
            ranges.append(ChunkRange(
                start=offset + current_start,
                end=offset + current_start + current_len,
                heading_path=section.title,
            ))

        return ranges

    def _build_documents(self, original: Document, text: str,
                         ranges: List[ChunkRange]) -> List[Document]:
        chunks = []
        for i, r in enumerate(ranges):
            chunk_text = text[r.start:r.end].strip()
            if not chunk_text:
                continue
            chunks.append(Document(
                page_content=chunk_text,
                metadata={
                    **original.metadata,
                    "chunk_index": i,
                    "char_start": r.start,
                    "char_end": r.end,
                    "heading_path": r.heading_path,
                    "chunk_strategy": STRATEGY,
                },
            ))
        return chunks
