import io
import uuid
from urllib.parse import quote
from fastapi import APIRouter, Depends, UploadFile, File, Form, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
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
    group_id: int = Query(..., alias="groupId"),
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await require_group_access(db, current_user.user_id, current_user.system_role, group_id)
    service = DocumentQueryService(db)
    result = await service.get_preview(document_id)
    return ApiResponse.ok(data=result)


@router.get("/documents/{document_id}/download")
async def download(
    document_id: int,
    group_id: int = Query(..., alias="groupId"),
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await require_group_access(db, current_user.user_id, current_user.system_role, group_id)
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
    group_id: int = Query(..., alias="groupId"),
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await require_group_access(db, current_user.user_id, current_user.system_role, group_id)
    service = DocumentQueryService(db)
    await service.delete(current_user.user_id, document_id)
    return ApiResponse.ok(message="文档已删除")


@router.post("/documents/{document_id}/retry-ingestion")
async def retry_ingestion(
    document_id: int,
    group_id: int = Query(..., alias="groupId"),
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from app.ingestion.models import IngestionJob
    from app.document.models import Document

    await require_group_access(db, current_user.user_id, current_user.system_role, group_id)

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
