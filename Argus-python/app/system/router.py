from fastapi import APIRouter, Depends
from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_admin
from app.common.response import ApiResponse
from app.common.security.context import AuthenticatedUser
from app.dependencies import get_db

router = APIRouter()


def _fmt(dt):
    return dt.isoformat() + "Z" if dt else None


@router.get("/health")
async def system_health(
    _admin: AuthenticatedUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    # PostgreSQL
    try:
        await db.execute(text("SELECT 1"))
        pg = {"ok": True, "message": "正常"}
    except Exception as e:
        pg = {"ok": False, "message": str(e)[:120]}

    # Elasticsearch
    try:
        from app.engine.es_service import es_service
        resp = await es_service.client.head(f"{es_service.base_url}/{es_service.index_name}")
        es = {"ok": resp.status_code < 400,
              "message": "正常" if resp.status_code < 400 else f"HTTP {resp.status_code}"}
    except Exception as e:
        es = {"ok": False, "message": str(e)[:120]}

    # MinIO
    try:
        from app.engine.storage import storage_service
        exists = storage_service.client.bucket_exists(storage_service.bucket)
        minio = {"ok": exists, "message": "正常" if exists else f"bucket {storage_service.bucket} 不存在"}
    except Exception as e:
        minio = {"ok": False, "message": str(e)[:120]}

    # Embedding API config (no live call — avoid cost on every health check)
    from app.config import settings
    embed_ok = bool(settings.embedding.api_key)
    embed = {"ok": embed_ok,
             "message": f"已配置 {settings.embedding.model_name}" if embed_ok else "未配置 API Key"}

    # Ingestion queue
    from app.ingestion.models import IngestionJob
    pending = (await db.execute(
        select(func.count()).select_from(IngestionJob).where(IngestionJob.status == "PENDING")
    )).scalar() or 0
    running = (await db.execute(
        select(func.count()).select_from(IngestionJob).where(IngestionJob.status == "RUNNING")
    )).scalar() or 0
    failed_result = await db.execute(
        select(IngestionJob)
        .where(IngestionJob.status == "FAILED")
        .order_by(IngestionJob.created_at.desc())
        .limit(5)
    )
    recent_failures = [
        {
            "jobId": j.id,
            "documentId": j.document_id,
            "error": (j.last_error or "")[:200],
            "createdAt": _fmt(j.created_at),
        }
        for j in failed_result.scalars()
    ]
    from app.ingestion.job_service import worker

    return ApiResponse.ok(data={
        "postgresql": pg,
        "elasticsearch": es,
        "minio": minio,
        "embedding": embed,
        "ingestion": {
            "pendingJobs": pending,
            "runningJobs": running,
            "workerRunning": getattr(worker, "_running", False),
            "recentFailures": recent_failures,
        },
    })
