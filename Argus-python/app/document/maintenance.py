import logging

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.time_utils import utcnow
from app.document.models import DocumentUploadSession, DocumentUploadChunk

logger = logging.getLogger(__name__)

INCOMPLETE_STATUSES = ("INIT", "UPLOADING", "COMPLETING")


class DocumentMaintenanceService:
    """Housekeeping for documents (expired upload sessions, etc.)."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def cleanup_expired_uploads(self) -> int:
        """Delete expired, incomplete upload sessions and their MinIO chunks."""
        now = utcnow()
        result = await self.session.execute(
            select(DocumentUploadSession).where(
                DocumentUploadSession.expires_at < now,
                DocumentUploadSession.status.in_(INCOMPLETE_STATUSES),
            )
        )
        sessions = result.scalars().all()
        if not sessions:
            return 0

        chunk_keys = []
        for s in sessions:
            chunk_result = await self.session.execute(
                select(DocumentUploadChunk).where(
                    DocumentUploadChunk.upload_id == s.upload_id
                )
            )
            chunk_keys.extend(c.storage_object_key for c in chunk_result.scalars())
            await self.session.execute(
                delete(DocumentUploadChunk).where(
                    DocumentUploadChunk.upload_id == s.upload_id
                )
            )
            await self.session.execute(
                delete(DocumentUploadSession).where(
                    DocumentUploadSession.id == s.id
                )
            )
        await self.session.flush()

        # Best-effort MinIO cleanup (failures are swallowed)
        try:
            from app.engine.storage import storage_service
            for key in chunk_keys:
                try:
                    storage_service.delete(key)
                except Exception:
                    pass
        except Exception:
            pass

        logger.info("Cleaned %d expired upload sessions", len(sessions))
        return len(sessions)
