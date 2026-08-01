import hashlib
import uuid
import logging
from datetime import datetime, timedelta

from app.common.time_utils import utcnow
from typing import Optional, List

from sqlalchemy import select, update, delete, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.document.models import Document, DocumentUploadSession, DocumentUploadChunk
from app.engine.storage import storage_service
from app.common.exception.exceptions import BusinessException, ForbiddenException

logger = logging.getLogger(__name__)

DOC_STATUS_UPLOADED = "UPLOADED"
DOC_STATUS_PROCESSING = "PROCESSING"
DOC_STATUS_READY = "READY"
DOC_STATUS_FAILED = "FAILED"
UPLOAD_STATUS_INIT = "INIT"
UPLOAD_STATUS_UPLOADING = "UPLOADING"
UPLOAD_STATUS_COMPLETING = "COMPLETING"
UPLOAD_STATUS_COMPLETED = "COMPLETED"

DEFAULT_CHUNK_SIZE = 5 * 1024 * 1024  # 5MB
MAX_FILE_SIZE = 256 * 1024 * 1024  # 256MB
UPLOAD_SESSION_EXPIRE_HOURS = 24


def _fmt(dt) -> Optional[str]:
    return dt.isoformat() if dt else None


class DocumentUploadService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def init_upload(self, user_id: int, req) -> dict:
        group_id = req.group_id
        file_hash = req.file_hash

        # Check for existing reusable session
        result = await self.session.execute(
            select(DocumentUploadSession).where(
                DocumentUploadSession.group_id == group_id,
                DocumentUploadSession.uploader_user_id == user_id,
                DocumentUploadSession.file_hash == file_hash,
                DocumentUploadSession.status == UPLOAD_STATUS_COMPLETED,
                DocumentUploadSession.expires_at > func.now(),
            ).order_by(DocumentUploadSession.created_at.desc()).limit(1)
        )
        reusable = result.scalar_one_or_none()
        if reusable:
            return {"upload_id": reusable.upload_id, "reused": True}

        upload_id = uuid.uuid4().hex
        expires_at = utcnow() + timedelta(hours=UPLOAD_SESSION_EXPIRE_HOURS)

        session_entity = DocumentUploadSession(
            upload_id=upload_id,
            group_id=group_id,
            uploader_user_id=user_id,
            file_name=req.file_name,
            file_ext=req.file_ext,
            content_type=req.content_type,
            file_size=req.file_size,
            file_hash=file_hash,
            chunk_size=req.chunk_size,
            chunk_count=req.chunk_count,
            status=UPLOAD_STATUS_INIT,
            expires_at=expires_at,
        )
        self.session.add(session_entity)
        await self.session.flush()
        return {"upload_id": upload_id, "chunk_size": req.chunk_size}

    async def upload_chunk(self, user_id: int, system_role: str, upload_id: str,
                           chunk_index: int, chunk_data: bytes, chunk_hash: str) -> dict:
        result = await self.session.execute(
            select(DocumentUploadSession).where(DocumentUploadSession.upload_id == upload_id)
        )
        session_entity = result.scalar_one_or_none()
        if session_entity is None:
            raise BusinessException("上传会话不存在或已过期")
        if session_entity.uploader_user_id != user_id and system_role != "ADMIN":
            raise ForbiddenException("无权操作该上传会话")
        if session_entity.status in (UPLOAD_STATUS_COMPLETED, "EXPIRED"):
            raise BusinessException("上传会话已结束")

        if session_entity.status == UPLOAD_STATUS_INIT:
            session_entity.status = UPLOAD_STATUS_UPLOADING

        object_key = f"uploads/{upload_id}/chunks/{chunk_index:06d}"
        storage_service.upload(object_key, chunk_data, "application/octet-stream")

        chunk = DocumentUploadChunk(
            upload_id=upload_id,
            chunk_index=chunk_index,
            chunk_size=len(chunk_data),
            chunk_hash=chunk_hash,
            storage_object_key=object_key,
            uploaded_at=utcnow(),
        )
        self.session.add(chunk)
        await self.session.flush()

        # Count uploaded chunks
        result = await self.session.execute(
            select(func.count()).select_from(DocumentUploadChunk).where(
                DocumentUploadChunk.upload_id == upload_id
            )
        )
        uploaded = result.scalar() or 0

        return {"uploaded_chunks": uploaded, "status": session_entity.status}

    async def complete_upload(self, user_id: int, system_role: str, upload_id: str) -> dict:
        result = await self.session.execute(
            select(DocumentUploadSession).where(DocumentUploadSession.upload_id == upload_id)
        )
        session_entity = result.scalar_one_or_none()
        if session_entity is None:
            raise BusinessException("上传会话不存在或已过期")
        if session_entity.uploader_user_id != user_id and system_role != "ADMIN":
            raise ForbiddenException("无权操作该上传会话")

        session_entity.status = UPLOAD_STATUS_COMPLETING

        # Get chunks ordered by index
        result = await self.session.execute(
            select(DocumentUploadChunk).where(DocumentUploadChunk.upload_id == upload_id)
            .order_by(DocumentUploadChunk.chunk_index)
        )
        chunks = result.scalars().all()

        if len(chunks) < session_entity.chunk_count:
            raise BusinessException(f"分片不完整: {len(chunks)}/{session_entity.chunk_count}")

        # Compose in MinIO
        merged_key = f"documents/{session_entity.group_id}/{uuid.uuid4().hex}/{session_entity.file_name}"
        source_keys = [c.storage_object_key for c in chunks]
        storage_service.compose(merged_key, source_keys, session_entity.content_type)

        session_entity.merged_object_key = merged_key
        session_entity.status = UPLOAD_STATUS_COMPLETED
        session_entity.storage_bucket = storage_service.bucket

        # Dedup: same hash + same group + not deleted → skip
        existing = await self._find_existing(session_entity.group_id, session_entity.file_hash)
        if existing:
            return {"document_id": existing.id, "file_name": existing.file_name, "is_duplicate": True}

        # Create document record
        doc = Document(
            group_id=session_entity.group_id,
            uploader_user_id=user_id,
            file_name=session_entity.file_name,
            file_ext=session_entity.file_ext,
            content_type=session_entity.content_type,
            file_size=session_entity.file_size,
            file_hash=session_entity.file_hash,
            storage_bucket=storage_service.bucket,
            storage_object_key=merged_key,
            status=DOC_STATUS_UPLOADED,
            uploaded_at=utcnow(),
        )
        self.session.add(doc)
        await self.session.flush()

        # Trigger ingestion job
        await self._create_ingestion_job(doc.id, doc.group_id)
        await self.session.flush()
        logger.info("Upload completed: docId=%s, groupId=%s", doc.id, doc.group_id)

        return {"document_id": doc.id, "file_name": doc.file_name, "is_duplicate": False}

    async def _find_existing(self, group_id: int, file_hash: str):
        result = await self.session.execute(
            select(Document).where(
                Document.group_id == group_id,
                Document.file_hash == file_hash,
                Document.deleted == False,
            ).limit(1)
        )
        return result.scalar_one_or_none()

    async def direct_upload(self, user_id: int, group_id: int, file_data: bytes, file_name: str,
                            content_type: str, file_hash: str) -> dict:
        if len(file_data) > MAX_FILE_SIZE:
            raise BusinessException(f"文件过大，最大支持 {MAX_FILE_SIZE // 1024 // 1024}MB")

        # Dedup: same hash + same group + not deleted → skip
        existing = await self._find_existing(group_id, file_hash)
        if existing:
            return {"document_id": existing.id, "file_name": existing.file_name, "is_duplicate": True}

        object_key = f"documents/{group_id}/{uuid.uuid4().hex}/{file_name}"
        storage_service.upload(object_key, file_data, content_type)

        ext = file_name.rsplit(".", 1)[-1].lower() if "." in file_name else ""
        doc = Document(
            group_id=group_id,
            uploader_user_id=user_id,
            file_name=file_name,
            file_ext=ext,
            content_type=content_type,
            file_size=len(file_data),
            file_hash=file_hash,
            storage_bucket=storage_service.bucket,
            storage_object_key=object_key,
            status=DOC_STATUS_UPLOADED,
            uploaded_at=utcnow(),
        )
        self.session.add(doc)
        await self.session.flush()

        await self._create_ingestion_job(doc.id, doc.group_id)
        await self.session.flush()
        logger.info("Direct upload completed: docId=%s", doc.id)

        return {"document_id": doc.id, "file_name": doc.file_name, "is_duplicate": False}

    async def _create_ingestion_job(self, document_id: int, group_id: int):
        from app.ingestion.models import IngestionJob
        job = IngestionJob(
            document_id=document_id,
            group_id=group_id,
            job_type="INGEST_DOCUMENT",
            status="PENDING",
            max_retries=3,
        )
        self.session.add(job)


class DocumentQueryService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_documents(self, group_id: int, status: str = None, file_name: str = None) -> List[dict]:
        from app.auth.models import User
        conditions = [Document.group_id == group_id, Document.deleted == False]
        if status:
            conditions.append(Document.status == status)
        if file_name:
            conditions.append(Document.file_name.ilike(f"%{file_name}%"))
        result = await self.session.execute(
            select(Document, User.display_name, User.user_code)
            .outerjoin(User, Document.uploader_user_id == User.id)
            .where(*conditions)
            .order_by(Document.created_at.desc())
        )
        return [self._to_list_item(doc, uname, ucode) for doc, uname, ucode in result]

    async def get_detail(self, document_id: int) -> dict:
        result = await self.session.execute(
            select(Document).where(Document.id == document_id, Document.deleted == False)
        )
        doc = result.scalar_one_or_none()
        if doc is None:
            raise BusinessException("文档不存在")
        return {
            "documentId": doc.id, "fileName": doc.file_name, "fileExt": doc.file_ext,
            "contentType": doc.content_type, "fileSize": doc.file_size,
            "status": doc.status, "previewText": doc.preview_text,
            "uploaderUserId": doc.uploader_user_id, "groupId": doc.group_id,
            "uploadedAt": _fmt(doc.uploaded_at), "processedAt": _fmt(doc.processed_at),
            "createdAt": _fmt(doc.created_at),
        }

    async def get_preview(self, document_id: int) -> dict:
        doc = await self._get_doc(document_id)
        # Load full text from stored object for preview
        try:
            data = storage_service.download(doc.storage_object_key)
            full_text = data.decode("utf-8", errors="replace")
        except Exception:
            full_text = doc.preview_text or ""
        return {
            "documentId": doc.id,
            "groupId": doc.group_id,
            "fileName": doc.file_name,
            "previewText": full_text,
            "status": doc.status,
        }

    async def download(self, document_id: int) -> tuple[bytes, str, str]:
        doc = await self._get_doc(document_id)
        data = storage_service.download(doc.storage_object_key)
        return data, doc.file_name, doc.content_type

    async def delete(self, user_id: int, document_id: int) -> dict:
        """Soft-delete a document and clean its indexes/storage.

        Returns per-step cleanup status so callers can surface failures
        (e.g. leftover vectors would resurface in retrieval).
        """
        result = await self.session.execute(select(Document).where(Document.id == document_id))
        doc = result.scalar_one_or_none()
        if doc is None or doc.deleted:
            raise BusinessException("文档不存在")

        # 1. Soft-delete document
        doc.deleted = True
        await self.session.flush()

        # 2. Delete document chunks from DB
        from app.ingestion.models import DocumentChunk
        from sqlalchemy import delete as sa_delete
        chunk_result = await self.session.execute(
            sa_delete(DocumentChunk).where(DocumentChunk.document_id == document_id)
        )
        logger.info("Deleted %d chunks for document %s", chunk_result.rowcount, document_id)

        cleanup = {"vector": True, "es": True, "storage": True}

        # 3. Clean vector embeddings
        try:
            from app.engine.vector_store import PgVectorRetrievalAdapter
            from app.config import settings
            adapter = PgVectorRetrievalAdapter(settings.database_url)
            await adapter.delete_by_document_ids([document_id])
        except Exception as e:
            cleanup["vector"] = False
            logger.error("Failed to delete vectors for document %s: %s", document_id, e)

        # 4. Clean ES index
        try:
            from app.engine.es_service import es_service
            await es_service.delete_by_document_ids([document_id])
        except Exception as e:
            cleanup["es"] = False
            logger.error("Failed to delete ES entries for document %s: %s", document_id, e)

        # 5. Delete MinIO object
        try:
            storage_service.delete(doc.storage_object_key)
        except Exception as e:
            cleanup["storage"] = False
            logger.error("Failed to delete MinIO object %s: %s", doc.storage_object_key, e)

        await self.session.flush()
        logger.info("Document deleted: id=%s, by=%s, cleanup=%s", document_id, user_id, cleanup)
        return cleanup

    async def _get_doc(self, document_id: int) -> Document:
        result = await self.session.execute(
            select(Document).where(Document.id == document_id, Document.deleted == False)
        )
        doc = result.scalar_one_or_none()
        if doc is None:
            raise BusinessException("文档不存在")
        return doc

    @staticmethod
    def _to_list_item(doc: Document, uploader_display_name: str = None, uploader_user_code: str = None) -> dict:
        return {
            "documentId": doc.id, "fileName": doc.file_name, "fileExt": doc.file_ext,
            "contentType": doc.content_type, "fileSize": doc.file_size,
            "status": doc.status, "uploaderUserId": doc.uploader_user_id,
            "uploaderDisplayName": uploader_display_name,
            "uploaderUserCode": uploader_user_code,
            "previewText": doc.preview_text or "",
            "processedAt": _fmt(doc.processed_at), "uploadedAt": _fmt(doc.uploaded_at),
            "createdAt": _fmt(doc.created_at),
        }
