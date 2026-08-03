import json
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user, require_admin
from app.common.exception.exceptions import BusinessException
from app.common.response import ApiResponse
from app.common.security.context import AuthenticatedUser
from app.dependencies import get_db
from app.group.service import require_group_access
from app.qa.service import QaService
from pydantic import BaseModel, Field

router = APIRouter()
qa_service = QaService()


class AskRequest(BaseModel):
    group_id: int = Field(..., alias="groupId")
    question: str = Field(..., min_length=1, max_length=5000)
    session_id: Optional[int] = Field(default=None, alias="sessionId")

    model_config = {"populate_by_name": True}


@router.post("/ask")
async def ask(
    request: AskRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await require_group_access(db, current_user.user_id, current_user.system_role, request.group_id)
    result = await qa_service.ask(current_user.user_id, request.group_id, request.question,
                                  session_id=request.session_id)
    # Frontend expects direct AskQuestionResponse, not ApiResponse-wrapped
    return result


# ---- My QA history (user-facing, backed by persisted sessions) ----

@router.get("/sessions")
async def my_qa_sessions(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=30, ge=1, le=100),
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from app.qa.history_service import QaHistoryService
    service = QaHistoryService(db)
    result = await service.list_sessions(user_id=current_user.user_id, page=page, limit=limit)
    return ApiResponse.ok(data=result)


@router.get("/sessions/{session_id}")
async def my_qa_session_detail(
    session_id: int,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from app.qa.history_service import QaHistoryService
    service = QaHistoryService(db)
    result = await service.get_session(session_id)
    if result is None or result["userId"] != current_user.user_id:
        raise BusinessException("问答记录不存在")
    return ApiResponse.ok(data=result)


@router.delete("/sessions/{session_id}")
async def delete_my_qa_session(
    session_id: int,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import delete
    from app.qa.models import QaSession, QaMessage

    result = await db.execute(
        select(QaSession.id).where(
            QaSession.id == session_id,
            QaSession.user_id == current_user.user_id,
        )
    )
    if result.scalar_one_or_none() is None:
        raise BusinessException("问答记录不存在")
    await db.execute(delete(QaMessage).where(QaMessage.session_id == session_id))
    await db.execute(delete(QaSession).where(QaSession.id == session_id))
    await db.flush()
    return ApiResponse.ok(message="已删除")


# ---- Admin QA history (requires admin) ----
admin_router = APIRouter()


@admin_router.get("/qa/sessions")
async def admin_list_sessions(
    user_id: int | None = Query(default=None, alias="userId"),
    group_id: int | None = Query(default=None, alias="groupId"),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    _admin: AuthenticatedUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    from app.qa.history_service import QaHistoryService
    service = QaHistoryService(db)
    result = await service.list_sessions(user_id=user_id, group_id=group_id, page=page, limit=limit)
    return ApiResponse.ok(data=result)


@admin_router.get("/qa/sessions/{session_id}")
async def admin_get_session(
    session_id: int,
    _admin: AuthenticatedUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    from app.qa.history_service import QaHistoryService
    service = QaHistoryService(db)
    result = await service.get_session(session_id)
    if result is None:
        raise BusinessException("问答记录不存在")
    return ApiResponse.ok(data=result)


@router.post("/stream-ask")
async def stream_ask(
    request: AskRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # 权限检查必须在响应开始前，否则 SSE 已启动后抛 403 无法返回错误码
    await require_group_access(db, current_user.user_id, current_user.system_role, request.group_id)

    async def event_generator():
        async for event in qa_service.ask_stream(
            current_user.user_id, request.group_id, request.question,
            session_id=request.session_id,
        ):
            event_type = event["event"]
            data = event["data"]
            yield f"event: {event_type}\ndata: {data}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
        },
    )
