from typing import Optional
from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    session_id: Optional[int] = Field(default=None, alias="sessionId")
    message: str = Field(..., min_length=1)
    tool_mode: str = Field(default="CHAT", alias="toolMode")
    group_id: Optional[int] = Field(default=None, alias="groupId")
    # human-in-the-loop 恢复值：写工具被 interrupt 暂停后，用户确认时传入
    resume: Optional[str] = Field(default=None)

    model_config = {"populate_by_name": True}


class SessionResponse(BaseModel):
    id: int
    title: str
    status: str
    last_message_at: Optional[str] = None
    created_at: Optional[str] = None


class MessageResponse(BaseModel):
    id: int
    role: str
    content: str
    tool_mode: str
    created_at: Optional[str] = None
