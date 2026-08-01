from datetime import datetime
from typing import Optional

from sqlalchemy import String, BigInteger, DateTime, ForeignKey, Text, Integer, Index, JSON, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class QaSession(Base):
    __tablename__ = "qa_sessions"

    __table_args__ = (
        Index("idx_qa_session_user_created", "user_id", "created_at"),
        Index("idx_qa_session_group_created", "group_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)
    group_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("groups.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())


class QaMessage(Base):
    __tablename__ = "qa_messages"

    __table_args__ = (
        Index("idx_qa_message_session", "session_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("qa_sessions.id"), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    thinking: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    citations: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    reason_code: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    reason_message: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    evidence_level: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
