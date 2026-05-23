import asyncio
import logging
from datetime import datetime, timedelta

from app.common.time_utils import utcnow
from sqlalchemy import select, update, func, or_

from app.config import settings
from app.ingestion.models import IngestionJob
from app.ingestion.pipeline import create_ingestion_processor

logger = logging.getLogger(__name__)


class IngestionJobWorker:
    def __init__(self):
        self._running = False
        self._task: asyncio.Task | None = None
        self.worker_id = settings.ingestion.worker_id
        self.poll_interval = settings.ingestion.worker_poll_interval_seconds

    async def start(self) -> None:
        self._running = True
        self._task = asyncio.create_task(self._poll_loop())
        logger.info("IngestionJobWorker started: workerId=%s", self.worker_id)

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("IngestionJobWorker stopped")

    async def _poll_loop(self) -> None:
        from app.dependencies import async_session_factory

        while self._running:
            try:
                async with async_session_factory() as session:
                    result = await session.execute(
                        select(IngestionJob)
                        .where(
                            IngestionJob.status == "PENDING",
                            or_(
                                IngestionJob.next_retry_at.is_(None),
                                IngestionJob.next_retry_at <= func.now(),
                            ),
                        )
                        .order_by(IngestionJob.created_at)
                        .with_for_update(skip_locked=True)
                        .limit(1)
                    )
                    job = result.scalar_one_or_none()

                    if job:
                        await self._execute_job(session, job)
                    await session.commit()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error("Job poll error: %s", e)

            await asyncio.sleep(self.poll_interval)

    async def _execute_job(self, session, job: IngestionJob) -> None:
        now = utcnow()
        job.status = "RUNNING"
        job.worker_id = self.worker_id
        job.started_at = now
        await session.flush()

        try:
            processor = create_ingestion_processor(session)
            await processor.process(job.document_id, job.group_id)
            job.status = "SUCCEEDED"
            job.finished_at = utcnow()
            logger.info("Job %s succeeded: docId=%s", job.id, job.document_id)
        except Exception as e:
            job.retry_count += 1
            if job.retry_count < job.max_retries:
                job.status = "PENDING"
                delay = 30 * (2 ** job.retry_count)
                job.next_retry_at = utcnow() + timedelta(seconds=delay)
                logger.warning("Job %s retry %d/%d: docId=%s, delay=%ds",
                               job.id, job.retry_count, job.max_retries, job.document_id, delay)
            else:
                job.status = "FAILED"
                logger.error("Job %s failed permanently: docId=%s", job.id, job.document_id)
            job.last_error = str(e)
            job.finished_at = utcnow()

        await session.flush()


worker = IngestionJobWorker()
