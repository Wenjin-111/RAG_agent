import logging
from datetime import datetime

from app.common.time_utils import utcnow
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.document.models import Document
from app.engine.storage import storage_service
from app.engine.vector_store import PgVectorRetrievalAdapter
from app.engine.es_service import es_service
from app.ingestion.models import IngestionJob
from app.ingestion.parsers.factory import DocumentParserFactory
from app.ingestion.transformers.text_cleanup import TextCleanupTransformer
from app.ingestion.transformers.chunking import StructureAwareChunkTransformer, ChunkingConfig
from app.ingestion.chunk_service import ChunkService
from app.config import settings

logger = logging.getLogger(__name__)

DOC_STATUS_PROCESSING = "PROCESSING"
DOC_STATUS_READY = "READY"
DOC_STATUS_FAILED = "FAILED"


class EtlDocumentIngestionProcessor:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.cleaner = TextCleanupTransformer()
        self.chunker = StructureAwareChunkTransformer(ChunkingConfig(
            target_tokens=settings.ingestion.chunking.target_tokens,
            max_tokens=settings.ingestion.chunking.max_tokens,
            overlap_tokens=settings.ingestion.chunking.overlap_tokens,
        ))
        self.chunk_service = ChunkService(session)
        self._vector_adapter = None

    async def process(self, document_id: int, group_id: int) -> None:
        result = await self.session.execute(
            select(Document).where(Document.id == document_id, Document.deleted == False)
        )
        doc = result.scalar_one_or_none()
        if doc is None:
            raise RuntimeError(f"Document not found: {document_id}")

        await self.session.execute(
            update(Document).where(Document.id == document_id).values(status=DOC_STATUS_PROCESSING)
        )
        await self.session.flush()

        try:
            # 1. Read file from MinIO
            file_data = storage_service.download(doc.storage_object_key)
            logger.info("Read file: %s, size=%d", doc.file_name, len(file_data))

            # 2. Parse
            parser = DocumentParserFactory.get(doc.file_ext)
            raw_docs = await parser.parse(file_data, doc.file_name)
            if not raw_docs:
                raise RuntimeError(f"No text extracted from {doc.file_name}")
            logger.info("Parsed %d pages/documents from %s", len(raw_docs), doc.file_name)

            # 3. Clean
            cleaned_docs = self.cleaner.transform(raw_docs)

            # 4. Persist preview text (first 200 chars)
            full_text = " ".join(d.page_content for d in cleaned_docs if d.page_content)
            preview = full_text[:200] if len(full_text) > 200 else full_text

            # 5. Chunk
            chunks = self.chunker.transform(cleaned_docs)
            logger.info("Created %d chunks from %s", len(chunks), doc.file_name)

            # 6. Save chunks to DB
            chunk_entities = await self.chunk_service.save_chunks(document_id, group_id, chunks)
            logger.info("Saved %d chunks to DB", len(chunk_entities))

            # 7. Vectorize and store
            from langchain_core.documents import Document as LCDocument
            vector_docs = []
            for entity in chunk_entities:
                vector_docs.append(LCDocument(
                    id=str(entity.id),
                    page_content=entity.chunk_text,
                    metadata={
                        "document_id": entity.document_id,
                        "group_id": entity.group_id,
                        "chunk_id": entity.id,
                        "chunk_index": entity.chunk_index,
                        "source": doc.file_name,
                    },
                ))

            vector_adapter = PgVectorRetrievalAdapter(settings.database_url)
            await vector_adapter.ensure_table()
            await vector_adapter.add_documents(vector_docs)
            logger.info("Vectorized %d chunks", len(vector_docs))

            # 8. Index in ES
            await es_service.index_chunks(doc.file_name, chunk_entities)
            logger.info("Indexed %d chunks in ES", len(chunk_entities))

            # 9. Mark document READY (clear any stale failure reason)
            await self.session.execute(
                update(Document).where(Document.id == document_id).values(
                    status=DOC_STATUS_READY,
                    preview_text=preview,
                    processed_at=utcnow(),
                    failure_reason=None,
                )
            )
            await self.session.flush()
            logger.info("Document %d processed successfully", document_id)

        except Exception as e:
            logger.error("Document %d processing failed: %s", document_id, e)
            await self.session.execute(
                update(Document).where(Document.id == document_id).values(
                    status=DOC_STATUS_FAILED,
                    failure_reason=str(e),
                )
            )
            await self.session.flush()
            raise


def create_ingestion_processor(session: AsyncSession) -> EtlDocumentIngestionProcessor:
    return EtlDocumentIngestionProcessor(session)
