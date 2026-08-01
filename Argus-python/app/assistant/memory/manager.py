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

    async def maintain_before_response(self, session_id: int, user_id: int) -> None:
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
            await self._update_summary(session_id, ctx, user_id)

    async def _update_summary(self, session_id: int, ctx: AssistantSessionContext,
                              user_id: int = 1) -> None:
        # Load recent messages (covers ~15 exchanges)
        result = await self.session.execute(
            select(AssistantMessage)
            .where(AssistantMessage.session_id == session_id)
            .order_by(AssistantMessage.id.desc())
            .limit(30)
        )
        recent = list(result.scalars())
        if not recent:
            return

        summary = await self._generate_summary(user_id, recent)
        if summary:
            ctx.summary_text = summary
            ctx.compact_summary = summary
        else:
            # Fallback: concatenate recent messages when the LLM call fails
            summary_parts = []
            for msg in reversed(recent):
                prefix = {"USER": "用户", "ASSISTANT": "助手", "TOOL": "工具"}
                summary_parts.append(f"[{prefix.get(msg.role, msg.role)}] {msg.content[:200]}")
            ctx.compact_summary = "\n".join(summary_parts)

        ctx.source_message_id = recent[0].id
        ctx.context_version += 1
        ctx.updated_at = utcnow()
        await self.session.flush()

    async def _generate_summary(self, user_id: int, messages: list) -> str:
        """Generate a semantic summary of the recent conversation via LLM."""
        try:
            from app.models_config.resolver import get_chat_config
            from langchain_core.messages import HumanMessage
            from langchain_openai import ChatOpenAI

            chat_cfg = await get_chat_config(user_id)
            model = ChatOpenAI(
                model=chat_cfg["model_name"],
                openai_api_key=chat_cfg["api_key"],
                openai_api_base=chat_cfg["base_url"],
                temperature=0.2,
                max_tokens=300,
            )
            prefix = {"USER": "用户", "ASSISTANT": "助手", "TOOL": "工具"}
            transcript = "\n".join(
                f"[{prefix.get(m.role, m.role)}] {m.content[:300]}" for m in reversed(messages)
            )
            prompt = (
                "请将以下对话压缩为 3-6 条要点式摘要（中文，每条一句话，"
                "覆盖用户的核心意图、已答复的关键信息以及待办/悬而未决的问题）：\n\n"
                f"{transcript}\n\n摘要："
            )
            resp = await model.ainvoke([HumanMessage(content=prompt)])
            return (resp.content or "").strip()[:2000]
        except Exception as e:
            logger.warning("LLM summary failed, using concatenation fallback: %s", e)
            return ""

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
            "updated_at": ctx.updated_at,
            "recent_messages": [
                {"role": m.role, "content": m.content}
                for m in messages
            ],
        }
