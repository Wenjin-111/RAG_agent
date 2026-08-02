import json
import logging
import math
from typing import List, Optional
from dataclasses import dataclass

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


@dataclass
class KeywordHit:
    chunk_id: int
    document_id: int
    chunk_index: int
    chunk_text: str
    score: float


class ElasticsearchChunkIndexService:
    def __init__(self):
        es = settings.elasticsearch
        self.base_url = f"{es.scheme}://{es.host}:{es.port}"
        self.index_name = es.index_name
        self._client: Optional[httpx.AsyncClient] = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=httpx.Timeout(10.0))
        return self._client

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    async def ensure_index(self) -> None:
        try:
            resp = await self.client.head(f"{self.base_url}/{self.index_name}")
            if resp.status_code == 200:
                return
        except Exception:
            pass

        body = {
            "settings": {
                "index": {"number_of_shards": 1, "number_of_replicas": 0},
                "analysis": {
                    "analyzer": {
                        "ik_max_word_analyzer": {"type": "custom", "tokenizer": "ik_max_word"},
                        "ik_smart_analyzer": {"type": "custom", "tokenizer": "ik_smart"},
                    }
                },
            },
            "mappings": {
                "properties": {
                    "documentId": {"type": "long"},
                    "groupId": {"type": "long"},
                    "chunkId": {"type": "long"},
                    "chunkIndex": {"type": "integer"},
                    "chunkText": {"type": "text", "analyzer": "ik_max_word", "search_analyzer": "ik_smart"},
                    "fileName": {"type": "text", "analyzer": "ik_max_word", "search_analyzer": "ik_smart"},
                    "status": {"type": "keyword"},
                    "deleted": {"type": "boolean"},
                }
            },
        }
        resp = await self.client.put(f"{self.base_url}/{self.index_name}", json=body)
        if resp.status_code >= 400:
            logger.warning("ES index creation may have failed: %s", resp.text)
        else:
            logger.info("ES index initialized: %s", self.index_name)

    async def search(self, group_id: int, query: str, top_k: int = 50) -> List[KeywordHit]:
        body = {
            "size": top_k,
            "query": {
                "bool": {
                    "filter": [
                        {"term": {"groupId": group_id}},
                        {"term": {"status": "READY"}},
                        {"term": {"deleted": False}},
                    ],
                    "should": [
                        {"match_phrase": {"chunkText": {"query": query, "boost": 3.0}}},
                        {"match": {"chunkText": {"query": query, "boost": 2.0}}},
                        {"match_phrase": {"fileName": {"query": query, "boost": 1.5}}},
                        {"match": {"fileName": {"query": query, "boost": 1.0}}},
                    ],
                    "minimum_should_match": 1,
                }
            },
            "rescore": {
                "window_size": 100,
                "query": {
                    "rescore_query": {
                        "match": {"chunkText": {"query": query, "operator": "and"}},
                    },
                    "query_weight": 0.7,
                    "rescore_query_weight": 0.3,
                },
            },
        }

        try:
            resp = await self.client.post(
                f"{self.base_url}/{self.index_name}/_search",
                json=body,
                headers={"Content-Type": "application/json"},
            )
            if resp.status_code >= 400:
                logger.error("ES search error: %s", resp.text)
                return []

            raw = resp.json()
            hits = []
            for h in raw.get("hits", {}).get("hits", []):
                src = h.get("_source", {})
                raw_score = h.get("_score", 0)
                norm_score = self._normalize_score(raw_score)
                hits.append(KeywordHit(
                    chunk_id=src.get("chunkId", 0),
                    document_id=src.get("documentId", 0),
                    chunk_index=src.get("chunkIndex", 0),
                    chunk_text=src.get("chunkText", ""),
                    score=norm_score,
                ))
            return hits
        except Exception as e:
            logger.error("ES search failed: %s", e)
            return []

    async def index_chunks(self, file_name: str, chunks: list) -> None:
        if not chunks:
            return
        # Bulk API: NDJSON (action line + source line), batched to bound memory
        BULK_BATCH = 100
        for i in range(0, len(chunks), BULK_BATCH):
            batch = chunks[i:i + BULK_BATCH]
            lines = []
            for chunk in batch:
                lines.append(json.dumps({"index": {"_index": self.index_name, "_id": chunk.id}}))
                lines.append(json.dumps({
                    "documentId": chunk.document_id,
                    "groupId": chunk.group_id,
                    "chunkId": chunk.id,
                    "chunkIndex": chunk.chunk_index,
                    "chunkText": chunk.chunk_text,
                    "fileName": file_name,
                    "status": "READY",
                    "deleted": False,
                }))
            try:
                resp = await self.client.post(
                    f"{self.base_url}/_bulk",
                    content="\n".join(lines) + "\n",
                    headers={"Content-Type": "application/x-ndjson"},
                )
                if resp.status_code >= 400:
                    logger.error("ES bulk index error: %s", resp.text[:500])
                    continue
                data = resp.json()
                errors = [item for item in data.get("items", [])
                          if (item.get("index") or {}).get("error")]
                if errors:
                    logger.error("ES bulk partial errors: %d/%d",
                                 len(errors), len(batch))
            except Exception as e:
                logger.error("ES bulk index failed (batch at %d): %s", i, e)

    async def delete_by_document_ids(self, document_ids: List[int]) -> None:
        body = {"query": {"terms": {"documentId": document_ids}}}
        try:
            resp = await self.client.post(
                f"{self.base_url}/{self.index_name}/_delete_by_query",
                json=body,
            )
            if resp.status_code < 400:
                logger.info("ES deleted docs: %s", document_ids)
        except Exception as e:
            logger.error("ES delete by query failed: %s", e)

    @staticmethod
    def _normalize_score(raw_score: float, reference: float = 100.0) -> float:
        if raw_score <= 0:
            return 0.0
        return min(1.0, math.log1p(raw_score) / math.log1p(reference))


es_service = ElasticsearchChunkIndexService()
