import logging
from datetime import datetime

from app.common.time_utils import utcnow
from typing import Optional

from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.assistant.models import AssistantSessionContext, AssistantMessage

logger = logging.getLogger(__name__)

TOKEN_ESTIMATE_DIVISOR = 4


class AssistantShortTermMemoryManager:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_or_create_context(self, session_id: int) -> AssistantSessionContext:
        result = await self.session.execute(
            select(AssistantSessionContext).where(AssistantSessionContext.session_id == session_id)
        )
        ctx = result.scalar_one_or_none()
        if ctx is None:
            ctx = AssistantSessionContext(session_id=session_id)
            self.session.add(ctx)
            await self.session.flush()
        return ctx

    async def maintain_before_response(self, session_id: int) -> None:
        ctx = await self.get_or_create_context(session_id)
        # Count total messages
        result = await self.session.execute(
            select(func.count()).select_from(AssistantMessage).where(
                AssistantMessage.session_id == session_id
            )
        )
        msg_count = result.scalar() or 0

        # Estimate total tokens
        result = await self.session.execute(
            select(func.sum(func.length(AssistantMessage.content))).where(
                AssistantMessage.session_id == session_id
            )
        )
        total_chars = result.scalar() or 0
        estimated_tokens = total_chars // TOKEN_ESTIMATE_DIVISOR

        # Trigger compact summary if needed
        if msg_count > 20 or estimated_tokens > 8000:
            await self._update_summary(session_id, ctx)

    async def _update_summary(self, session_id: int, ctx: AssistantSessionContext) -> None:
        # Load recent messages summary
        result = await self.session.execute(
            select(AssistantMessage)
            .where(AssistantMessage.session_id == session_id)
            .order_by(AssistantMessage.id.desc())
            .limit(10)
        )
        recent = list(result.scalars())
        if not recent:
            return

        summary_parts = []
        for msg in reversed(recent):
            prefix = {"USER": "用户", "ASSISTANT": "助手", "TOOL": "工具"}
            summary_parts.append(f"[{prefix.get(msg.role, msg.role)}] {msg.content[:200]}")

        ctx.compact_summary = "\n".join(summary_parts)
        ctx.source_message_id = recent[0].id
        ctx.context_version += 1
        ctx.updated_at = utcnow()
        await self.session.flush()

    async def load_context(self, session_id: int) -> dict:
        ctx = await self.get_or_create_context(session_id)

        result = await self.session.execute(
            select(AssistantMessage)
            .where(AssistantMessage.session_id == session_id)
            .order_by(AssistantMessage.created_at)
            .limit(20)
        )
        messages = list(result.scalars())

        return {
            "compact_summary": ctx.compact_summary,
            "session_memory": ctx.session_memory,
            "summary_text": ctx.summary_text,
            "recent_messages": [
                {"role": m.role, "content": m.content}
                for m in messages
            ],
        }
