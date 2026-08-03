import json

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user, require_admin
from app.common.response import ApiResponse
from app.common.security.context import AuthenticatedUser
from app.dependencies import get_db
from app.assistant.schemas import ChatRequest
from app.assistant.service import AssistantService
from app.group.service import require_group_access

router = APIRouter()


@router.get("/sessions")
async def list_sessions(
    status: str = Query(default="ACTIVE"),
    mode: str | None = Query(default=None),
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if mode == "ADMIN" and current_user.system_role != "ADMIN":
        from app.common.exception.exceptions import ForbiddenException
        raise ForbiddenException("无权访问管理会话")
    service = AssistantService(db)
    sessions = await service.list_sessions(current_user.user_id, status=status, mode=mode)
    return sessions  # Frontend expects direct array


@router.post("/sessions/{session_id}/archive")
async def archive_session(
    session_id: int,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = AssistantService(db)
    await service.archive_session(current_user.user_id, session_id)
    return ApiResponse.ok(message="会话已归档")


@router.post("/sessions/{session_id}/restore")
async def restore_session(
    session_id: int,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = AssistantService(db)
    await service.restore_session(current_user.user_id, session_id)
    return ApiResponse.ok(message="会话已恢复")


@router.post("/sessions/{session_id}/summarize")
async def summarize_session(
    session_id: int,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = AssistantService(db)
    summary = await service.refresh_summary(current_user.user_id, session_id)
    return ApiResponse.ok(data={"summaryText": summary})


@router.post("/sessions")
async def create_session(
    body: dict = None,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    mode = (body or {}).get("mode", "CHAT")
    if mode == "ADMIN" and current_user.system_role != "ADMIN":
        from app.common.exception.exceptions import ForbiddenException
        raise ForbiddenException("无权创建管理会话")
    service = AssistantService(db)
    result = await service.create_session(current_user.user_id, mode=mode)
    return ApiResponse.ok(data=result)


@router.get("/sessions/{session_id}")
async def get_session(
    session_id: int,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = AssistantService(db)
    result = await service.get_session(current_user.user_id, session_id)
    return result  # Frontend expects direct object


@router.patch("/sessions/{session_id}")
async def update_session(
    session_id: int,
    body: dict,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = AssistantService(db)
    result = await service.update_session(current_user.user_id, session_id, body.get("title", ""))
    return ApiResponse.ok(data=result)


@router.delete("/sessions/{session_id}")
async def delete_session(
    session_id: int,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = AssistantService(db)
    await service.delete_session(current_user.user_id, session_id)
    return ApiResponse.ok(message="已删除")


@router.get("/sessions/{session_id}/messages")
async def list_messages(
    session_id: int,
    before_id: int | None = Query(default=None, alias="beforeId"),
    limit: int = Query(default=30, ge=1, le=100),
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = AssistantService(db)
    messages = await service.list_messages(session_id, before_id=before_id, limit=limit)
    return ApiResponse.ok(data=messages)


@router.get("/sessions/{session_id}/context")
async def get_context(
    session_id: int,
    recent_limit: int = Query(default=12, alias="recentLimit"),
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = AssistantService(db)
    ctx = await service.get_context(session_id, recent_limit)
    return ctx  # Frontend expects direct object


@router.post("/chat")
async def chat(
    request: ChatRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = AssistantService(db)
    if request.group_id is not None:
        await require_group_access(db, current_user.user_id, current_user.system_role, request.group_id)
    result = await service.chat(
        current_user.user_id, request.session_id or 0, request.message,
        request.tool_mode, request.group_id,
        current_user.system_role, current_user.user_code,
    )
    return ApiResponse.ok(data=result)


@router.post("/chat/stream")
async def chat_stream(
    request: ChatRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if request.group_id is not None:
        await require_group_access(db, current_user.user_id, current_user.system_role, request.group_id)
    if request.tool_mode == "ADMIN" and current_user.system_role != "ADMIN":
        from app.common.exception.exceptions import ForbiddenException
        raise ForbiddenException("无权使用管理助手")
    service = AssistantService(db)

    async def event_generator():
        async for ev in service.chat_stream(
            current_user.user_id, request.session_id or 0, request.message,
            request.tool_mode, request.group_id,
            current_user.system_role, current_user.user_code,
            resume=request.resume,
        ):
            event_name = ev["event"]
            if event_name == "delta":
                # 前端解析约定 data 为 {"delta": "..."} 对象
                yield f"event: delta\ndata: {json.dumps({'delta': ev['data']}, ensure_ascii=False)}\n\n"
            else:
                yield f"event: {event_name}\ndata: {json.dumps(ev['data'], ensure_ascii=False)}\n\n"
        yield 'event: done\ndata: {"event":"done","reply":"","citations":[]}\n\n'

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
    )
