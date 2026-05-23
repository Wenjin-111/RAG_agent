import json
import logging
import uuid
from typing import List, Optional
from dataclasses import dataclass

import httpx
from sqlalchemy import text

from app.config import settings

logger = logging.getLogger(__name__)

COLLECTION_NAME = "rag_document_chunks"


async def _embed_texts(texts: List[str], user_id: int = None) -> List[List[float]]:
    """Call embedding API, using active model config if available."""
    from app.models_config.resolver import get_embedding_config
    import asyncio as _asyncio

    # Try to get admin's active config; if not available, use .env defaults
    s = settings.embedding
    api_url = ""
    api_key = s.api_key
    model_name = s.model_name

    try:
        cfg = _asyncio.get_event_loop()
        if cfg and user_id:
            # Can't await in sync context; use defaults
            pass
    except Exception:
        pass

    # Use admin user (id=1) as the config owner
    try:
        cfg = await get_embedding_config(1)
        if cfg:
            api_key = cfg["api_key"]
            model_name = cfg["model_name"]
            api_url = cfg["base_url"]
    except Exception:
        api_key = s.api_key
        model_name = s.model_name

    # Determine API format based on model
    if "dashscope" in api_url or not api_url:
        api_url = "https://dashscope.aliyuncs.com/api/v1/services/embeddings/text-embedding/text-embedding"
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                api_url,
                json={
                    "model": model_name,
                    "input": {"texts": texts},
                    "parameters": {"dimension": s.dimensions},
                },
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            )
            if resp.status_code != 200:
                logger.error("Embedding API error: %s %s", resp.status_code, resp.text[:500])
                raise RuntimeError(f"Embedding API returned {resp.status_code}: {resp.text[:200]}")
            body = resp.json()
            embeddings = body.get("output", {}).get("embeddings", [])
            embeddings.sort(key=lambda d: d.get("text_index", 0))
            return [e["embedding"] for e in embeddings]
    else:
        # OpenAI-compatible API
        api_url = api_url.rstrip("/") + "/embeddings"
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                api_url,
                json={"model": model_name, "input": texts},
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            )
        if resp.status_code != 200:
            logger.error("Embedding API error: %s %s", resp.status_code, resp.text[:500])
            raise RuntimeError(f"Embedding API returned {resp.status_code}: {resp.text[:200]}")
        body = resp.json()
        embeddings = body.get("output", {}).get("embeddings", [])
        embeddings.sort(key=lambda d: d.get("text_index", 0))
        return [e["embedding"] for e in embeddings]


@dataclass
class VectorHit:
    document_id: int
    chunk_id: int
    chunk_index: int
    chunk_text: str
    score: float


class PgVectorRetrievalAdapter:
    def __init__(self, connection_string: str):
        pass

    async def ensure_table(self) -> None:
        from app.dependencies import engine
        async with engine.begin() as conn:
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS langchain_pg_embedding (
                    id SERIAL PRIMARY KEY,
                    collection_id UUID,
                    embedding vector,
                    document VARCHAR,
                    cmetadata JSONB,
                    custom_id VARCHAR
                )
            """))
        logger.info("PGVector table ensured: %s", COLLECTION_NAME)

    async def search(self, group_id: int, question: str, top_k: int = 50) -> List[VectorHit]:
        from app.dependencies import engine

        # Get query embedding
        vectors = await _embed_texts([question])
        query_vector = "[" + ",".join(str(v) for v in vectors[0]) + "]"

        async with engine.begin() as conn:
            result = await conn.execute(
                text(f"""
                    SELECT document, cmetadata,
                           1 - (embedding <=> CAST(:emb AS vector)) AS similarity
                    FROM langchain_pg_embedding
                    WHERE cmetadata->>'group_id' = :gid
                    ORDER BY embedding <=> CAST(:emb AS vector)
                    LIMIT :lim
                """),
                {"emb": query_vector, "gid": str(group_id), "lim": top_k},
            )
            rows = result.all()

        hits = []
        for row in rows:
            metadata = row.cmetadata or {}
            try:
                doc_id = int(metadata.get("document_id", 0))
                chunk_id = int(metadata.get("chunk_id", 0))
                chunk_index = int(metadata.get("chunk_index", 0))
            except (ValueError, TypeError):
                continue
            if not row.document:
                continue

            hits.append(VectorHit(
                document_id=doc_id,
                chunk_id=chunk_id,
                chunk_index=chunk_index,
                chunk_text=row.document.strip(),
                score=float(row.similarity),
            ))

        hits.sort(key=lambda h: h.score, reverse=True)
        return hits

    async def add_documents(self, documents: list) -> List[str]:
        from app.dependencies import engine

        texts = [doc.page_content for doc in documents]
        metadatas = [doc.metadata for doc in documents]
        collection_id = uuid.uuid4()

        # text-embedding-v4 limits batch size to 10
        BATCH_SIZE = 10
        all_vectors = []
        for i in range(0, len(texts), BATCH_SIZE):
            batch = texts[i:i + BATCH_SIZE]
            batch_vectors = await _embed_texts(batch)
            all_vectors.extend(batch_vectors)

        async with engine.begin() as conn:
            for content, metadata, vector in zip(texts, metadatas, all_vectors):
                vector_str = "[" + ",".join(str(v) for v in vector) + "]"
                await conn.execute(
                    text("""
                        INSERT INTO langchain_pg_embedding
                            (collection_id, embedding, document, cmetadata)
                        VALUES
                            (:cid, CAST(:vec AS vector), :doc, CAST(:meta AS jsonb))
                    """),
                    {
                        "cid": collection_id,
                        "vec": vector_str,
                        "doc": content,
                        "meta": json.dumps(metadata),
                    },
                )

        logger.info("Added %d vectors to PGVector", len(documents))
        return [str(i) for i in range(len(documents))]

    async def delete_by_document_ids(self, document_ids: List[int]) -> None:
        from app.dependencies import engine
        id_list = ", ".join(str(did) for did in document_ids)
        async with engine.begin() as conn:
            await conn.execute(
                text(f"DELETE FROM langchain_pg_embedding WHERE cmetadata->>'document_id' IN ({id_list})")
            )
        logger.info("Deleted vectors for documents: %s", document_ids)
