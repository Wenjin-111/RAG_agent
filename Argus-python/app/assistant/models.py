from datetime import datetime
from typing import Optional

from sqlalchemy import String, BigInteger, DateTime, ForeignKey, Text, Integer, Index, JSON, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AssistantSession(Base):
    __tablename__ = "assistant_sessions"

    __table_args__ = (
        Index("idx_sessions_user_status", "user_id", "status"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False, default="新会话")
    mode: Mapped[str] = mapped_column(String(32), nullable=False, default="CHAT")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="ACTIVE")
    last_message_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())


class AssistantMessage(Base):
    __tablename__ = "assistant_messages"

    __table_args__ = (
        Index("idx_messages_session_created", "session_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("assistant_sessions.id"), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    tool_mode: Mapped[str] = mapped_column(String(32), nullable=False)
    group_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    structured_payload: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())


class AssistantSessionContext(Base):
    __tablename__ = "assistant_session_contexts"

    session_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("assistant_sessions.id"), primary_key=True)
    session_memory: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    compact_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    session_memory_base_message_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    session_memory_range_end_message_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    compact_summary_base_message_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    compact_summary_range_end_message_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    summary_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_message_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    context_version: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())
