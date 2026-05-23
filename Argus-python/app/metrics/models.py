from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import String, BigInteger, DateTime, Integer, Boolean, Text, Numeric, Index, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class LlmUsageRecord(Base):
    __tablename__ = "llm_usage_records"

    __table_args__ = (
        Index("idx_llm_usage_user_created", "user_id", "created_at"),
        Index("idx_llm_usage_group_created", "group_id", "created_at"),
        Index("idx_llm_usage_module_created", "module", "created_at"),
        Index("idx_llm_usage_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    group_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    module: Mapped[str] = mapped_column(String(32), nullable=False)
    endpoint: Mapped[str] = mapped_column(String(64), nullable=False)
    session_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    prompt_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_estimated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    cost_amount: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=Decimal("0"))
    cost_currency: Mapped[str] = mapped_column(String(8), default="CNY")
    latency_ms: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    model_name: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
