import logging
from datetime import datetime

from app.common.time_utils import utcnow
from typing import AsyncIterator, Optional, List

from sqlalchemy import select, update, delete, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.assistant.models import AssistantSession, AssistantMessage, AssistantSessionContext
from app.assistant.memory.manager import AssistantShortTermMemoryManager
from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI

from app.assistant.agent import facade

logger = logging.getLogger(__name__)


def _fmt(dt) -> Optional[str]:
    return dt.isoformat() + "Z" if dt else None


class AssistantService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.memory = AssistantShortTermMemoryManager(session)

    # ---- Sessions ----

    async def list_sessions(self, user_id: int) -> List[dict]:
        result = await self.session.execute(
            select(AssistantSession)
            .where(AssistantSession.user_id == user_id, AssistantSession.status == "ACTIVE")
            .order_by(AssistantSession.last_message_at.desc().nullslast(), AssistantSession.created_at.desc())
        )
        return [
            {"session_id": s.id, "title": s.title, "status": s.status,
             "last_message_at": _fmt(s.last_message_at), "created_at": _fmt(s.created_at)}
            for s in result.scalars()
        ]

    async def create_session(self, user_id: int, title: str = "新会话") -> dict:
        session_entity = AssistantSession(
            user_id=user_id,
            title=title,
            status="ACTIVE",
        )
        self.session.add(session_entity)
        await self.session.flush()
        return {"session_id": session_entity.id, "title": session_entity.title, "status": session_entity.status}

    async def update_session(self, user_id: int, session_id: int, title: str) -> dict:
        await self.session.execute(
            update(AssistantSession)
            .where(AssistantSession.id == session_id, AssistantSession.user_id == user_id)
            .values(title=title, updated_at=utcnow())
        )
        await self.session.flush()
        return {"session_id": session_id, "title": title}

    async def delete_session(self, user_id: int, session_id: int) -> None:
        # Verify session exists and belongs to user
        result = await self.session.execute(
            select(AssistantSession)
            .where(AssistantSession.id == session_id, AssistantSession.user_id == user_id)
        )
        if result.scalar_one_or_none() is None:
            from app.common.exception.exceptions import BusinessException
            raise BusinessException("会话不存在")

        # Delete messages
        msg_result = await self.session.execute(
            delete(AssistantMessage).where(AssistantMessage.session_id == session_id)
        )
        # Delete context
        ctx_result = await self.session.execute(
            delete(AssistantSessionContext).where(AssistantSessionContext.session_id == session_id)
        )
        # Soft-delete session
        await self.session.execute(
            update(AssistantSession)
            .where(AssistantSession.id == session_id)
            .values(status="DELETED", updated_at=utcnow())
        )
        await self.session.flush()
        logger.info("Session %s deleted: %d messages, context cleaned", session_id, msg_result.rowcount)

    async def get_session(self, user_id: int, session_id: int) -> dict:
        result = await self.session.execute(
            select(AssistantSession)
            .where(AssistantSession.id == session_id, AssistantSession.user_id == user_id)
        )
        s = result.scalar_one_or_none()
        if s is None:
            return {}
        return {
            "session_id": s.id, "title": s.title, "status": s.status,
            "last_message_at": _fmt(s.last_message_at), "created_at": _fmt(s.created_at),
        }

    async def get_context(self, session_id: int, recent_limit: int = 12) -> dict:
        ctx = await self.memory.load_context(session_id)
        result = await self.session.execute(
            select(AssistantMessage)
            .where(AssistantMessage.session_id == session_id)
            .order_by(AssistantMessage.created_at.desc(), AssistantMessage.id.desc())
            .limit(recent_limit)
        )
        recent = []
        for m in reversed(list(result.scalars())):
            recent.append({"message_id": m.id, "role": m.role, "content": m.content,
                          "tool_mode": m.tool_mode, "group_id": m.group_id, "created_at": _fmt(m.created_at)})
        return {
            "summaryText": ctx.get("compact_summary") or ctx.get("summary_text") or "",
            "recentMessages": recent,
        }

    # ---- Messages ----

    async def list_messages(self, session_id: int, limit: int = 50) -> List[dict]:
        result = await self.session.execute(
            select(AssistantMessage)
            .where(AssistantMessage.session_id == session_id)
            .order_by(AssistantMessage.created_at, AssistantMessage.id)
            .limit(limit)
        )
        return [
            {"message_id": m.id, "role": m.role, "content": m.content,
             "tool_mode": m.tool_mode, "created_at": _fmt(m.created_at)}
            for m in result.scalars()
        ]

    # ---- Chat ----

    async def chat(self, user_id: int, session_id: int, message: str,
                   tool_mode: str = "CHAT", group_id: Optional[int] = None) -> dict:
        session_id = await self._ensure_session(user_id, session_id)

        # Save user message
        self.session.add(AssistantMessage(
            session_id=session_id, role="USER", tool_mode=tool_mode,
            group_id=group_id, content=message,
        ))
        await self.session.flush()

        # Memory maintenance
        await self.memory.maintain_before_response(session_id)

        # Load context and build instruction
        ctx = await self.memory.load_context(session_id)
        instruction = self._build_instruction(ctx, tool_mode)

        # Call agent
        thread_id = f"session_{session_id}"
        result = await facade.chat_sync(instruction, message, tool_mode, group_id, thread_id, user_id)

        # Save assistant message
        self.session.add(AssistantMessage(
            session_id=session_id, role="ASSISTANT", tool_mode=tool_mode,
            content=result["reply"],
            structured_payload={"citations": result.get("citations", [])},
        ))

        # Update session
        await self.session.execute(
            update(AssistantSession)
            .where(AssistantSession.id == session_id)
            .values(last_message_at=utcnow(),
                    updated_at=utcnow())
        )
        await self.session.flush()

        # Auto-title (fire-and-forget, non-critical)
        import asyncio
        asyncio.create_task(self._auto_title(session_id, message, result.get("reply", "")))

        return {
            "session_id": session_id,
            "reply": result["reply"],
            "citations": result.get("citations", []),
            "thinking": result.get("thinking", ""),
        }

    async def chat_stream(self, user_id: int, session_id: int, message: str,
                          tool_mode: str = "CHAT", group_id: Optional[int] = None) -> AsyncIterator[str]:
        session_id = await self._ensure_session(user_id, session_id)

        # Save user message
        self.session.add(AssistantMessage(
            session_id=session_id, role="USER", tool_mode=tool_mode,
            group_id=group_id, content=message,
        ))
        await self.session.flush()

        await self.memory.maintain_before_response(session_id)
        ctx = await self.memory.load_context(session_id)
        instruction = self._build_instruction(ctx, tool_mode)

        thread_id = f"session_{session_id}"
        full_reply = ""

        async for delta in facade.chat_stream(instruction, message, tool_mode, group_id, thread_id, user_id):
            full_reply += delta
            yield delta

        # Save assistant message
        self.session.add(AssistantMessage(
            session_id=session_id, role="ASSISTANT", tool_mode=tool_mode,
            content=full_reply,
        ))

        await self.session.execute(
            update(AssistantSession)
            .where(AssistantSession.id == session_id)
            .values(last_message_at=utcnow(),
                    updated_at=utcnow())
        )
        await self.session.flush()

        # Auto-title (fire-and-forget, non-critical, with its own session)
        import asyncio as _asyncio
        _asyncio.create_task(self._auto_title_async(session_id, message, full_reply))

    async def _ensure_session(self, user_id: int, session_id: Optional[int]) -> int:
        if session_id:
            return session_id
        result = await self.create_session(user_id)
        return result["session_id"]

    def _build_instruction(self, ctx: dict, tool_mode: str) -> str:
        parts = ["你是一个智能AI助手。"]
        if tool_mode == "KB_SEARCH":
            parts.append("你可以使用 knowledge_base_search 工具搜索知识库文档。"
                         "每次对话只能调用一次搜索工具。获取证据后直接给出最终回答。")

        # Include recent conversation history so the assistant has short-term memory
        recent = ctx.get("recent_messages", [])
        if recent:
            history = ["\n最近对话记录："]
            for m in recent[-10:]:  # last 10 messages
                role = "用户" if m["role"] == "USER" else "助手"
                history.append(f"[{role}] {m['content'][:300]}")
            parts.append("\n".join(history))

        if ctx.get("compact_summary"):
            parts.append(f"\n历史对话摘要：\n{ctx['compact_summary']}")
        if ctx.get("session_memory"):
            parts.append(f"\n会话记忆：\n{ctx['session_memory']}")

        parts.append("\n请用中文回答，保持简洁专业。")
        return "\n".join(parts)

    async def _auto_title(self, session_id: int, user_msg: str, assistant_reply: str):
        """Launch auto-title in background with its own DB session."""
        import asyncio as _asyncio
        _asyncio.create_task(self._auto_title_async(session_id, user_msg, assistant_reply))

    async def _auto_title_async(self, session_id: int, user_msg: str, assistant_reply: str):
        try:
            from app.dependencies import async_session_factory
            from app.models_config.resolver import get_chat_config
            async with async_session_factory() as db:
                result = await db.execute(
                    select(AssistantSession.title).where(AssistantSession.id == session_id)
                )
                current_title = result.scalar_one_or_none()
                if not current_title or current_title == "新会话":
                    chat_cfg = await get_chat_config(1)
                    model = ChatOpenAI(
                        model=chat_cfg["model_name"], openai_api_key=chat_cfg["api_key"],
                        openai_api_base=chat_cfg["base_url"], temperature=0.3, max_tokens=16,
                    )
                    prompt = f"根据对话生成2-6字标题，直接输出：\n用户：{user_msg[:100]}\n助手：{assistant_reply[:200]}\n标题："
                    resp = await model.ainvoke([HumanMessage(content=prompt)])
                    title = resp.content.strip()[:12]
                    if title:
                        await db.execute(
                            update(AssistantSession).where(AssistantSession.id == session_id).values(title=title)
                        )
                        await db.commit()
                        logger.info("Auto-titled session %s → %s", session_id, title)
        except Exception as e:
            logger.debug("Auto-title failed (non-critical): %s", e)
