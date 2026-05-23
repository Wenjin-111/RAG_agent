import json
from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from app.auth.dependencies import get_current_user
from app.common.response import ApiResponse
from app.common.security.context import AuthenticatedUser
from app.qa.service import QaService
from pydantic import BaseModel, Field

router = APIRouter()
qa_service = QaService()


class AskRequest(BaseModel):
    group_id: int = Field(..., alias="groupId")
    question: str = Field(..., min_length=1, max_length=5000)

    model_config = {"populate_by_name": True}


@router.post("/ask")
async def ask(
    request: AskRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    result = await qa_service.ask(current_user.user_id, request.group_id, request.question)
    # Frontend expects direct AskQuestionResponse, not ApiResponse-wrapped
    return result


@router.post("/stream-ask")
async def stream_ask(
    request: AskRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    async def event_generator():
        async for event in qa_service.ask_stream(
            current_user.user_id, request.group_id, request.question
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
