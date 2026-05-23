from datetime import timedelta
from decimal import Decimal

from sqlalchemy import select, func, case, literal_column
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.time_utils import utcnow
from app.metrics.models import LlmUsageRecord
from app.auth.models import User
from app.group.models import Group
from app.document.models import Document
from app.ingestion.models import DocumentChunk


class LlmUsageStatisticsService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def overview(self) -> dict:
        total_users = await self._count(User)
        total_groups = await self._count(Group)
        total_documents = await self._count(Document, Document.deleted == False)
        total_chunks = await self._count(DocumentChunk)

        today_start = utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

        today = await self.session.execute(
            select(
                func.count().label("calls"),
                func.sum(LlmUsageRecord.total_tokens).label("tokens"),
                func.sum(LlmUsageRecord.cost_amount).label("cost"),
                func.sum(
                    case((LlmUsageRecord.success == True, 1), else_=0)
                ).label("success_count"),
            ).where(LlmUsageRecord.created_at >= today_start)
        )
        t = today.one()

        today_calls = t.calls or 0
        today_success = t.success_count or 0
        today_success_rate = (today_success / today_calls * 100) if today_calls > 0 else 100.0

        # daily trend (last 30 days)
        since = utcnow() - timedelta(days=30)
        trend_result = await self.session.execute(
            select(
                func.date(LlmUsageRecord.created_at).label("date"),
                func.count().label("calls"),
                func.sum(LlmUsageRecord.total_tokens).label("tokens"),
                func.sum(LlmUsageRecord.cost_amount).label("cost"),
            )
            .where(LlmUsageRecord.created_at >= since)
            .group_by(func.date(LlmUsageRecord.created_at))
            .order_by(func.date(LlmUsageRecord.created_at))
        )
        daily_trend = [
            {
                "date": str(r.date),
                "requests": r.calls,
                "tokens": r.tokens or 0,
                "cost": float(r.cost or Decimal("0")),
            }
            for r in trend_result
        ]

        return {
            "today_requests": today_calls,
            "today_tokens": t.tokens or 0,
            "today_cost": float(t.cost or Decimal("0")),
            "today_success_rate": round(today_success_rate, 1),
            "total_users": total_users,
            "total_groups": total_groups,
            "total_documents": total_documents,
            "total_chunks": total_chunks,
            "total_calls": t.calls or 0,
            "daily_trend": daily_trend,
        }

    async def daily_trend(self, days: int = 30) -> list:
        since = utcnow() - timedelta(days=days)
        result = await self.session.execute(
            select(
                func.date(LlmUsageRecord.created_at).label("date"),
                func.count().label("calls"),
                func.sum(LlmUsageRecord.total_tokens).label("tokens"),
            )
            .where(LlmUsageRecord.created_at >= since)
            .group_by(func.date(LlmUsageRecord.created_at))
            .order_by(func.date(LlmUsageRecord.created_at))
        )
        return [
            {"date": str(r.date), "requests": r.calls, "tokens": r.tokens or 0}
            for r in result
        ]

    async def top_users(self, limit: int = 10) -> list:
        result = await self.session.execute(
            select(
                LlmUsageRecord.user_id,
                User.display_name,
                func.count().label("calls"),
                func.sum(LlmUsageRecord.total_tokens).label("tokens"),
                func.sum(LlmUsageRecord.cost_amount).label("cost"),
            )
            .join(User, LlmUsageRecord.user_id == User.id)
            .group_by(LlmUsageRecord.user_id, User.display_name)
            .order_by(func.sum(LlmUsageRecord.total_tokens).desc())
            .limit(limit)
        )
        return [
            {
                "id": r.user_id,
                "name": r.display_name,
                "total_requests": r.calls,
                "total_tokens": r.tokens or 0,
                "total_cost": float(r.cost or Decimal("0")),
            }
            for r in result
        ]

    async def top_groups(self, limit: int = 10) -> list:
        result = await self.session.execute(
            select(
                LlmUsageRecord.group_id,
                Group.group_name,
                func.count().label("calls"),
                func.sum(LlmUsageRecord.total_tokens).label("tokens"),
                func.sum(LlmUsageRecord.cost_amount).label("cost"),
            )
            .join(Group, LlmUsageRecord.group_id == Group.id)
            .where(LlmUsageRecord.group_id.isnot(None))
            .group_by(LlmUsageRecord.group_id, Group.group_name)
            .order_by(func.sum(LlmUsageRecord.total_tokens).desc())
            .limit(limit)
        )
        return [
            {
                "id": r.group_id,
                "name": r.group_name,
                "total_requests": r.calls,
                "total_tokens": r.tokens or 0,
                "total_cost": float(r.cost or Decimal("0")),
            }
            for r in result
        ]

    async def _count(self, model, *filters) -> int:
        stmt = select(func.count()).select_from(model)
        if filters:
            stmt = stmt.where(*filters)
        result = await self.session.execute(stmt)
        return result.scalar() or 0
