import logging
from typing import List

from sqlalchemy import delete, insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ingestion.models import DocumentChunk

logger = logging.getLogger(__name__)

POSTGRES_PARAMETER_LIMIT = 65535
INSERT_BATCH_PARAM_COUNT = 10
MAX_INSERT_BATCH_SIZE = (POSTGRES_PARAMETER_LIMIT - 128) // INSERT_BATCH_PARAM_COUNT


class ChunkService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def save_chunks(self, document_id: int, group_id: int,
                          chunks: list) -> List[DocumentChunk]:
        await self.session.execute(
            delete(DocumentChunk).where(DocumentChunk.document_id == document_id)
        )

        entities = []
        for i, chunk in enumerate(chunks):
            entity = DocumentChunk(
                document_id=document_id,
                group_id=group_id,
                chunk_index=i,
                chunk_text=chunk.page_content,
                char_start=chunk.metadata.get("char_start", 0),
                char_end=chunk.metadata.get("char_end", 0),
                metadata_json=chunk.metadata,
            )
            entities.append(entity)

        for batch in self._batch(entities, MAX_INSERT_BATCH_SIZE):
            self.session.add_all(batch)
            await self.session.flush()

        # Backfill IDs
        result = await self.session.execute(
            select(DocumentChunk).where(
                DocumentChunk.document_id == document_id
            ).order_by(DocumentChunk.chunk_index)
        )
        return list(result.scalars())

    @staticmethod
    def _batch(items: list, size: int):
        for i in range(0, len(items), size):
            yield items[i:i + size]
