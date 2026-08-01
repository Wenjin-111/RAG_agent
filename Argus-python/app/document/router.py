import io
import uuid
from urllib.parse import quote
from fastapi import APIRouter, Depends, UploadFile, File, Form, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import log_audit
from app.auth.dependencies import get_current_user, require_admin
from app.auth.models import User
from app.common.response import ApiResponse
from app.common.security.context import AuthenticatedUser
from app.common.exception.exceptions import BusinessException, ForbiddenException
from app.dependencies import get_db
from app.document.service import DocumentUploadService, DocumentQueryService
from app.group.service import require_group_access

router = APIRouter()


@router.get("/documents")
async def list_documents(
    group_id: int = Query(..., alias="groupId"),
    status: str = Query(default=""),
    file_name: str = Query(default="", alias="fileName"),
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await require_group_access(db, current_user.user_id, current_user.system_role, group_id)
    service = DocumentQueryService(db)
    docs = await service.list_documents(group_id, status=status or None, file_name=file_name or None)
    return ApiResponse.ok(data=docs)


@router.get("/documents/{document_id}")
async def get_document(
    document_id: int,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _check_document_access(db, current_user, document_id)
    service = DocumentQueryService(db)
    detail = await service.get_detail(document_id)
    return ApiResponse.ok(data=detail)


@router.get("/documents/{document_id}/preview")
async def get_preview(
    document_id: int,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _check_document_access(db, current_user, document_id)
    service = DocumentQueryService(db)
    result = await service.get_preview(document_id)
    return ApiResponse.ok(data=result)


@router.get("/documents/{document_id}/download")
async def download(
    document_id: int,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _check_document_access(db, current_user, document_id)
    service = DocumentQueryService(db)
    data, file_name, content_type = await service.download(document_id)
    return StreamingResponse(
        io.BytesIO(data),
        media_type=content_type,
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(file_name)}"},
    )


@router.get("/documents/{document_id}/chunks")
async def list_chunks(
    document_id: int,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from app.ingestion.models import DocumentChunk
    await _check_document_access(db, current_user, document_id)
    result = await db.execute(
        select(DocumentChunk)
        .where(DocumentChunk.document_id == document_id)
        .order_by(DocumentChunk.chunk_index)
    )
    chunks = result.scalars().all()
    return ApiResponse.ok(data=[
        {
            "chunkId": c.id,
            "chunkIndex": c.chunk_index,
            "chunkText": c.chunk_text,
            "charStart": c.char_start,
            "charEnd": c.char_end,
        }
        for c in chunks
    ])


@router.delete("/documents/{document_id}")
async def delete_document(
    document_id: int,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _check_document_access(db, current_user, document_id)
    service = DocumentQueryService(db)
    cleanup = await service.delete(current_user.user_id, document_id)
    await log_audit(db, current_user, "DOCUMENT_DELETE", "document", document_id)
    if all(cleanup.values()):
        return ApiResponse.ok(message="文档已删除")
    return ApiResponse.ok(message="文档已删除，但部分索引清理失败（向量/搜索/存储），可能残留影响检索，建议联系管理员")


@router.post("/documents/{document_id}/retry-ingestion")
async def retry_ingestion(
    document_id: int,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from app.ingestion.models import IngestionJob
    from app.document.models import Document

    await _check_document_access(db, current_user, document_id)

    result = await db.execute(select(Document).where(Document.id == document_id))
    doc = result.scalar_one_or_none()
    if doc is None:
        raise BusinessException("文档不存在")

    if doc.status != "FAILED":
        raise BusinessException("只有处理失败的文档才能重试")

    doc.status = "UPLOADED"
    job = IngestionJob(
        document_id=document_id,
        group_id=doc.group_id,
        job_type="INGEST_DOCUMENT",
        status="PENDING",
        max_retries=3,
    )
    db.add(job)
    await db.flush()
    await log_audit(db, current_user, "DOCUMENT_RETRY", "document", document_id)
    return ApiResponse.ok(message="已重新提交处理")


# ---- Direct Upload ----

@router.post("/documents/upload")
async def direct_upload(
    group_id: int = Form(..., alias="groupId"),
    file: UploadFile = File(...),
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    import hashlib
    await require_group_access(db, current_user.user_id, current_user.system_role, group_id)

    file_data = await file.read()
    file_hash = hashlib.sha256(file_data).hexdigest()
    content_type = file.content_type or "application/octet-stream"

    service = DocumentUploadService(db)
    result = await service.direct_upload(
        current_user.user_id, group_id, file_data, file.filename, content_type, file_hash
    )
    return ApiResponse.ok(data={
        "documentId": result["document_id"],
        "fileName": result["file_name"],
        "isDuplicate": result.get("is_duplicate", False),
    })


# ---- Chunked Upload ----

@router.post("/documents/upload/init")
async def init_upload(
    body: dict,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from app.document.schemas import UploadInitRequest
    req = UploadInitRequest(**body, group_id=body.get("groupId", 0))
    await require_group_access(db, current_user.user_id, current_user.system_role, req.group_id)
    service = DocumentUploadService(db)
    result = await service.init_upload(current_user.user_id, req)
    return ApiResponse.ok(data={
        "instantUpload": result.get("reused", False),
        "documentId": result.get("document_id"),
        "uploadId": result["upload_id"],
        "uploadedChunks": [],
        "chunkSize": result.get("chunk_size"),
        "chunkCount": None,
    })


@router.post("/documents/upload/chunks")
async def upload_chunk(
    upload_id: str = Form(..., alias="uploadId"),
    chunk_index: int = Form(..., alias="chunkIndex"),
    chunk_hash: str = Form(default="", alias="chunkHash"),
    chunk: UploadFile = File(...),
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    chunk_data = await chunk.read()
    service = DocumentUploadService(db)
    result = await service.upload_chunk(
        current_user.user_id, current_user.system_role, upload_id, chunk_index, chunk_data, chunk_hash
    )
    return ApiResponse.ok(data={
        "status": result["status"],
        "uploadedChunks": list(range(result["uploaded_chunks"])),
        "uploadedChunkCount": result["uploaded_chunks"],
        "chunkCount": None,
    })


@router.get("/documents/upload/{upload_id}")
async def get_upload_status(
    upload_id: str,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import select, func
    from app.document.models import DocumentUploadSession, DocumentUploadChunk

    result = await db.execute(
        select(DocumentUploadSession).where(DocumentUploadSession.upload_id == upload_id)
    )
    session_entity = result.scalar_one_or_none()
    if session_entity is None:
        return ApiResponse.fail("上传会话不存在")
    if session_entity.uploader_user_id != current_user.user_id and current_user.system_role != "ADMIN":
        raise ForbiddenException("无权操作该上传会话")
    result = await db.execute(
        select(func.count()).select_from(DocumentUploadChunk).where(
            DocumentUploadChunk.upload_id == upload_id
        )
    )
    uploaded = result.scalar() or 0
    return ApiResponse.ok(data={
        "status": session_entity.status,
        "uploadedChunks": list(range(uploaded)),
        "uploadedChunkCount": uploaded,
        "chunkCount": session_entity.chunk_count,
    })


@router.post("/documents/upload/{upload_id}/complete")
async def complete_upload(
    upload_id: str,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = DocumentUploadService(db)
    result = await service.complete_upload(current_user.user_id, current_user.system_role, upload_id)
    return ApiResponse.ok(data={
        "documentId": result["document_id"],
        "fileName": result["file_name"],
        "isDuplicate": result.get("is_duplicate", False),
    })


async def _check_document_access(db: AsyncSession, current_user: AuthenticatedUser, document_id: int) -> None:
    """按文档归属群组校验访问权限。"""
    from app.document.models import Document

    result = await db.execute(select(Document).where(Document.id == document_id, Document.deleted == False))
    doc = result.scalar_one_or_none()
    if doc is None:
        raise BusinessException("文档不存在")
    await require_group_access(db, current_user.user_id, current_user.system_role, doc.group_id)


# ---- Admin: global document management (requires admin) ----

admin_router = APIRouter()


@admin_router.get("/documents")
async def admin_list_documents(
    status: str = Query(default=""),
    group_id: int | None = Query(default=None, alias="groupId"),
    file_name: str = Query(default="", alias="fileName"),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    _admin: AuthenticatedUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import func
    from app.document.models import Document
    from app.group.models import Group

    conditions = [Document.deleted == False]
    if status:
        conditions.append(Document.status == status)
    if group_id:
        conditions.append(Document.group_id == group_id)
    if file_name:
        conditions.append(Document.file_name.ilike(f"%{file_name}%"))

    count_result = await db.execute(
        select(func.count()).select_from(Document).where(*conditions)
    )
    total = count_result.scalar() or 0

    result = await db.execute(
        select(Document, Group.group_name, User.display_name, User.user_code)
        .join(Group, Document.group_id == Group.id)
        .join(User, Document.uploader_user_id == User.id)
        .where(*conditions)
        .order_by(Document.created_at.desc())
        .offset((page - 1) * limit)
        .limit(limit)
    )
    items = []
    for doc, gname, uname, ucode in result:
        items.append({
            "documentId": doc.id,
            "fileName": doc.file_name,
            "fileExt": doc.file_ext,
            "fileSize": doc.file_size,
            "status": doc.status,
            "groupId": doc.group_id,
            "groupName": gname,
            "uploaderUserId": doc.uploader_user_id,
            "uploaderDisplayName": uname,
            "uploaderUserCode": ucode,
            "failureReason": doc.failure_reason,
            "uploadedAt": doc.uploaded_at.isoformat() + "Z" if doc.uploaded_at else None,
            "processedAt": doc.processed_at.isoformat() + "Z" if doc.processed_at else None,
        })
    return ApiResponse.ok(data={"items": items, "total": total, "page": page, "limit": limit})


@admin_router.get("/documents/stats")
async def admin_document_stats(
    _admin: AuthenticatedUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import func, case
    from app.document.models import Document

    result = await db.execute(
        select(
            func.count().label("total"),
            func.sum(case((Document.status == "READY", 1), else_=0)).label("ready"),
            func.sum(case((Document.status == "PROCESSING", 1), else_=0)).label("processing"),
            func.sum(case((Document.status == "UPLOADED", 1), else_=0)).label("pending"),
            func.sum(case((Document.status == "FAILED", 1), else_=0)).label("failed"),
            func.sum(case((Document.deleted == False, Document.file_size), else_=0)).label("storage_bytes"),
        ).where(Document.deleted == False)
    )
    r = result.one()
    return ApiResponse.ok(data={
        "total": r.total or 0,
        "ready": r.ready or 0,
        "processing": r.processing or 0,
        "pending": r.pending or 0,
        "failed": r.failed or 0,
        "storageBytes": r.storage_bytes or 0,
    })


@admin_router.post("/documents/{document_id}/retry")
async def admin_retry_document(
    document_id: int,
    _admin: AuthenticatedUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    from app.ingestion.models import IngestionJob
    from app.document.models import Document

    result = await db.execute(select(Document).where(Document.id == document_id))
    doc = result.scalar_one_or_none()
    if doc is None or doc.deleted:
        raise BusinessException("文档不存在")
    if doc.status != "FAILED":
        raise BusinessException("只有处理失败的文档才能重试")

    doc.status = "UPLOADED"
    db.add(IngestionJob(
        document_id=document_id,
        group_id=doc.group_id,
        job_type="INGEST_DOCUMENT",
        status="PENDING",
        max_retries=3,
    ))
    await db.flush()
    await log_audit(db, _admin, "DOCUMENT_RETRY", "document", document_id)
    return ApiResponse.ok(message="已重新提交处理")


@admin_router.delete("/documents/{document_id}")
async def admin_delete_document(
    document_id: int,
    _admin: AuthenticatedUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    service = DocumentQueryService(db)
    cleanup = await service.delete(1, document_id)
    await log_audit(db, _admin, "DOCUMENT_DELETE", "document", document_id)
    if all(cleanup.values()):
        return ApiResponse.ok(message="文档已删除")
    return ApiResponse.ok(message="文档已删除，但部分索引清理失败（向量/搜索/存储），可能残留影响检索，建议检查系统日志")
