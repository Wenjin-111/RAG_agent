from __future__ import annotations

import logging
import math
from collections import defaultdict
from dataclasses import dataclass, field
from typing import List, Dict, Optional

from app.engine.vector_store import PgVectorRetrievalAdapter, VectorHit
from app.engine.es_service import es_service, KeywordHit
from app.config import settings

logger = logging.getLogger(__name__)

CHANNEL_TOP_K = 50
RRF_K = 0
DEFAULT_NEIGHBOR_WINDOW = 1


@dataclass
class RetrievalCandidate:
    chunk_id: int
    document_id: int
    chunk_index: int
    chunk_text: str = ""
    vector_score: float = 0.0
    keyword_score: float = 0.0
    ranking_score: float = 0.0
    raw_similarity: float = 0.0  # actual cosine similarity before RRF


@dataclass
class EvidenceDocument:
    evidence_id: str
    content: str
    chunk_ids: List[int] = field(default_factory=list)
    source_file: str = ""
    evidence_level: str = ""
    rrf_score: float = 0.0


@dataclass
class RetrievedEvidenceBundle:
    documents: List[EvidenceDocument]
    evidence_level: EvidenceLevel
    evidence_guidance: str

    @classmethod
    def empty(cls):
        from app.qa.query_planning import EvidenceLevel
        return cls(documents=[], evidence_level=EvidenceLevel.NONE, evidence_guidance="")


class HybridChunkRetrievalService:
    def __init__(self, vector_adapter: PgVectorRetrievalAdapter):
        self.vector_adapter = vector_adapter

    async def retrieve(self, group_id: int, question: str,
                       planned_queries: List[str], top_k: int = 5) -> RetrievedEvidenceBundle:
        candidates: Dict[int, RetrievalCandidate] = {}

        for query in planned_queries:
            await self._merge_vector_hits(candidates, group_id, query)
            await self._merge_keyword_hits(candidates, group_id, query)

        if not candidates:
            return RetrievedEvidenceBundle.empty()

        ranked = sorted(candidates.values(), key=lambda c: c.ranking_score, reverse=True)
        ranked = ranked[:top_k]

        # Normalize RRF scores to 0-1 range (top hit = 1.0)
        if ranked:
            max_score = max(c.ranking_score for c in ranked)
            if max_score > 0:
                for c in ranked:
                    c.ranking_score = c.ranking_score / max_score

        clusters = self._build_clusters(ranked)
        chunk_ids = [c.chunk_id for c in ranked]

        # Fetch actual chunk text from DB
        db_rows = await self._fetch_chunk_rows(group_id, chunk_ids)

        documents = []
        for i, cluster in enumerate(clusters):
            doc = await self._build_document(f"E{i+1}", db_rows, cluster)
            if doc:
                documents.append(doc)

        evidence_level = self._assess_evidence(documents, ranked)
        guidance = self._build_guidance(evidence_level)

        return RetrievedEvidenceBundle(
            documents=documents,
            evidence_level=evidence_level,
            evidence_guidance=guidance,
        )

    async def _merge_vector_hits(self, candidates: dict, group_id: int, query: str):
        hits = await self.vector_adapter.search(group_id, query, CHANNEL_TOP_K)
        for rank, hit in enumerate(hits, start=1):
            c = candidates.setdefault(hit.chunk_id, RetrievalCandidate(
                chunk_id=hit.chunk_id, document_id=hit.document_id,
                chunk_index=hit.chunk_index, chunk_text=hit.chunk_text,
            ))
            rrf_score = 1.0 / (RRF_K + rank)
            c.vector_score = max(c.vector_score, rrf_score)
            c.ranking_score += rrf_score
            c.raw_similarity = max(c.raw_similarity, hit.score)

    async def _merge_keyword_hits(self, candidates: dict, group_id: int, query: str):
        hits = await es_service.search(group_id, query, CHANNEL_TOP_K)
        for rank, hit in enumerate(hits, start=1):
            c = candidates.setdefault(hit.chunk_id, RetrievalCandidate(
                chunk_id=hit.chunk_id, document_id=hit.document_id,
                chunk_index=hit.chunk_index, chunk_text=hit.chunk_text,
            ))
            rrf_score = 1.0 / (RRF_K + rank)
            c.keyword_score = max(c.keyword_score, rrf_score)
            c.ranking_score += rrf_score

    def _build_clusters(self, ranked: List[RetrievalCandidate]) -> List[List[RetrievalCandidate]]:
        if not ranked:
            return []
        clusters = []
        current_cluster = [ranked[0]]

        for c in ranked[1:]:
            prev = current_cluster[-1]
            if c.document_id == prev.document_id and c.chunk_index <= prev.chunk_index + DEFAULT_NEIGHBOR_WINDOW + 1:
                current_cluster.append(c)
            else:
                clusters.append(current_cluster)
                current_cluster = [c]

        clusters.append(current_cluster)
        return clusters

    async def _fetch_chunk_rows(self, group_id: int, chunk_ids: List[int]) -> dict:
        from app.dependencies import async_session_factory
        from app.ingestion.models import DocumentChunk
        from app.document.models import Document
        from sqlalchemy import select

        async with async_session_factory() as session:
            result = await session.execute(
                select(DocumentChunk, Document.file_name)
                .outerjoin(Document, DocumentChunk.document_id == Document.id)
                .where(DocumentChunk.id.in_(chunk_ids))
            )
            return {row.id: (row, file_name or "未知文件") for row, file_name in result}

    async def _build_document(self, evidence_id: str, db_rows: dict,
                              cluster: List[RetrievalCandidate]) -> Optional[EvidenceDocument]:
        if not cluster:
            return None

        # Expand with neighbor window
        all_chunk_ids = set()
        for c in cluster:
            all_chunk_ids.add(c.chunk_id)
            for offset in range(-DEFAULT_NEIGHBOR_WINDOW, DEFAULT_NEIGHBOR_WINDOW + 1):
                if offset != 0:
                    all_chunk_ids.add(c.chunk_id + offset)

        valid_rows = {}
        for chunk_id in all_chunk_ids:
            if chunk_id in db_rows:
                valid_rows[chunk_id] = db_rows[chunk_id]

        sorted_ids = sorted(valid_rows.keys())
        content = "\n\n".join(valid_rows[cid][0].chunk_text for cid in sorted_ids if valid_rows[cid][0].chunk_text)

        if not content.strip():
            return None

        # Get source file name, chunk index, and RRF score
        entry = db_rows.get(cluster[0].chunk_id)
        source_file = entry[1] if entry else "未知文件"
        main_chunk_index = entry[0].chunk_index if entry else 0

        return EvidenceDocument(
            evidence_id=evidence_id,
            content=content,
            chunk_ids=[main_chunk_index],
            source_file=source_file,
            rrf_score=cluster[0].ranking_score,
        )

    def _assess_evidence(self, documents: List[EvidenceDocument],
                         candidates: List[RetrievalCandidate]) -> EvidenceLevel:
        from app.qa.query_planning import EvidenceLevel

        if not documents:
            return EvidenceLevel.NONE

        # Check if the content is actually semantically relevant
        max_raw_sim = max((c.raw_similarity for c in candidates), default=0)
        if max_raw_sim < 0.65:
            return EvidenceLevel.NONE  # vector similarity too low, content is irrelevant

        has_vector = any(c.vector_score > 0 for c in candidates)
        has_keyword = any(c.keyword_score > 0 for c in candidates)
        both = has_vector and has_keyword
        top_score = max(c.ranking_score for c in candidates) if candidates else 0

        if len(documents) >= 2 and (both or (has_vector and top_score >= 0.85)):
            return EvidenceLevel.SUFFICIENT
        elif both or len(documents) >= 2:
            return EvidenceLevel.PARTIAL
        else:
            return EvidenceLevel.WEAK

    def _build_guidance(self, level) -> str:
        from app.qa.query_planning import EvidenceLevel
        if level == EvidenceLevel.SUFFICIENT:
            return "证据充分"
        elif level == EvidenceLevel.PARTIAL:
            return "证据部分充分，回答时请注明不确定性"
        elif level == EvidenceLevel.WEAK:
            return "证据较弱"
        return "无相关证据"
