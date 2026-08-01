from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.models import AuditLog


async def log_audit(session: AsyncSession, user, action: str,
                    target_type: Optional[str] = None, target_id: Optional[str] = None,
                    detail: Optional[dict] = None) -> None:
    """Convenience helper for router handlers: records the current user's action."""
    await AuditService(session).log(
        user_id=user.user_id,
        username=getattr(user, "user_code", "") or "",
        action=action,
        target_type=target_type,
        target_id=target_id,
        detail=detail,
    )


def _fmt(dt) -> Optional[str]:
    return dt.isoformat() + "Z" if dt else None


class AuditService:
    """Sensitive-operation audit trail (non-critical: failures are swallowed)."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def log(self, user_id: int, username: str, action: str,
                  target_type: Optional[str] = None, target_id: Optional[str] = None,
                  detail: Optional[dict] = None) -> None:
        try:
            self.session.add(AuditLog(
                user_id=user_id,
                username=username or "",
                action=action,
                target_type=target_type,
                target_id=str(target_id) if target_id is not None else None,
                detail=detail,
            ))
            await self.session.flush()
        except Exception:
            pass  # audit must never break the main operation

    async def list_logs(self, action: Optional[str] = None, user_id: Optional[int] = None,
                        page: int = 1, limit: int = 20) -> dict:
        filters = []
        if action:
            filters.append(AuditLog.action == action)
        if user_id:
            filters.append(AuditLog.user_id == user_id)

        count_result = await self.session.execute(
            select(func.count()).select_from(AuditLog).where(*filters)
        )
        total = count_result.scalar() or 0

        result = await self.session.execute(
            select(AuditLog)
            .where(*filters)
            .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
            .offset((page - 1) * limit)
            .limit(limit)
        )
        items = [
            {
                "id": log.id,
                "userId": log.user_id,
                "username": log.username,
                "action": log.action,
                "targetType": log.target_type,
                "targetId": log.target_id,
                "detail": log.detail or {},
                "createdAt": _fmt(log.created_at),
            }
            for log in result.scalars()
        ]
        return {"items": items, "total": total, "page": page, "limit": limit}
