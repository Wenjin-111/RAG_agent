from typing import Optional

from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.qa.models import QaSession, QaMessage
from app.auth.models import User
from app.group.models import Group


def _fmt(dt) -> Optional[str]:
    return dt.isoformat() + "Z" if dt else None


class QaHistoryService:
    """Admin QA history browsing (requires admin)."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_sessions(self, user_id: Optional[int] = None, group_id: Optional[int] = None,
                            page: int = 1, limit: int = 20) -> dict:
        filters = []
        if user_id:
            filters.append(QaSession.user_id == user_id)
        if group_id:
            filters.append(QaSession.group_id == group_id)

        count_result = await self.session.execute(
            select(func.count()).select_from(QaSession).where(*filters)
        )
        total = count_result.scalar() or 0

        result = await self.session.execute(
            select(QaSession, User.display_name, User.user_code, Group.group_name)
            .join(User, QaSession.user_id == User.id)
            .outerjoin(Group, QaSession.group_id == Group.id)
            .where(*filters)
            .order_by(QaSession.created_at.desc())
            .offset((page - 1) * limit)
            .limit(limit)
        )
        rows = result.all()

        # 每个会话的首条用户问题 + 末条回答摘要
        items = []
        for s, uname, ucode, gname in rows:
            msg_result = await self.session.execute(
                select(QaMessage.role, QaMessage.content, QaMessage.reason_code)
                .where(QaMessage.session_id == s.id)
                .order_by(QaMessage.id)
            )
            msgs = msg_result.all()
            question = next((m.content for m in msgs if m.role == "USER"), "")
            answer = next((m.content for m in reversed(msgs) if m.role == "ASSISTANT"), "")
            items.append({
                "sessionId": s.id,
                "userId": s.user_id,
                "userName": uname,
                "userCode": ucode,
                "groupId": s.group_id,
                "groupName": gname or "已解散群组",
                "title": s.title,
                # Full texts — the frontend truncates visually and shows the
                # complete content in the hover tooltip
                "question": question,
                "answerPreview": answer,
                "messageCount": len(msgs),
                "createdAt": _fmt(s.created_at),
            })

        return {"items": items, "total": total, "page": page, "limit": limit}

    async def get_session(self, session_id: int) -> Optional[dict]:
        result = await self.session.execute(
            select(QaSession, User.display_name, User.user_code, Group.group_name)
            .join(User, QaSession.user_id == User.id)
            .outerjoin(Group, QaSession.group_id == Group.id)
            .where(QaSession.id == session_id)
        )
        row = result.one_or_none()
        if row is None:
            return None
        s, uname, ucode, gname = row

        msg_result = await self.session.execute(
            select(QaMessage).where(QaMessage.session_id == session_id).order_by(QaMessage.id)
        )
        messages = [
            {
                "messageId": m.id,
                "role": m.role,
                "content": m.content,
                "thinking": m.thinking,
                "citations": m.citations or [],
                "reasonCode": m.reason_code,
                "reasonMessage": m.reason_message,
                "createdAt": _fmt(m.created_at),
            }
            for m in msg_result.scalars()
        ]
        return {
            "sessionId": s.id,
            "userId": s.user_id,
            "userName": uname,
            "userCode": ucode,
            "groupId": s.group_id,
            "groupName": gname or "已解散群组",
            "title": s.title,
            "messages": messages,
            "createdAt": _fmt(s.created_at),
        }
