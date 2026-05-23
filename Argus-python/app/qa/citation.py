from typing import List
from dataclasses import dataclass


@dataclass
class Citation:
    index: int
    file_name: str
    chunk_ids: List[int]


class CitationAssembler:
    @staticmethod
    def assemble(documents: list) -> List[Citation]:
        seen = set()
        citations = []
        for i, doc in enumerate(documents):
            source = doc.source_file
            if hasattr(doc, "metadata") and isinstance(doc.metadata, dict):
                source = doc.metadata.get("source", f"doc_{i}")
            if source not in seen:
                seen.add(source)
                citations.append(Citation(
                    index=len(citations) + 1,
                    file_name=source,
                    chunk_ids=getattr(doc, "chunk_ids", []),
                ))
        return citations
