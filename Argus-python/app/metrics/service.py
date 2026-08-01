from datetime import timedelta
from decimal import Decimal

from sqlalchemy import select, func, case, distinct
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

        # daily trend (last 30 days, zero-filled so the chart line is continuous)
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
        )
        trend_map = {str(r.date): r for r in trend_result}
        daily_trend = []
        for i in range(30):
            day = (utcnow() - timedelta(days=29 - i)).date()
            row = trend_map.get(str(day))
            daily_trend.append({
                "date": str(day),
                "requests": row.calls if row else 0,
                "tokens": (row.tokens or 0) if row else 0,
                "cost": float(row.cost or Decimal("0")) if row else 0.0,
            })

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

    async def top_users(self, limit: int = 10, since=None) -> list:
        stmt = (
            select(
                LlmUsageRecord.user_id,
                User.display_name,
                func.count().label("calls"),
                func.sum(LlmUsageRecord.total_tokens).label("tokens"),
                func.sum(LlmUsageRecord.cost_amount).label("cost"),
            )
            .join(User, LlmUsageRecord.user_id == User.id)
        )
        if since is not None:
            stmt = stmt.where(LlmUsageRecord.created_at >= since)
        stmt = stmt.group_by(LlmUsageRecord.user_id, User.display_name).order_by(
            func.sum(LlmUsageRecord.total_tokens).desc()
        ).limit(limit)
        result = await self.session.execute(stmt)
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

    async def top_groups(self, limit: int = 10, since=None) -> list:
        stmt = (
            select(
                LlmUsageRecord.group_id,
                Group.group_name,
                func.count().label("calls"),
                func.sum(LlmUsageRecord.total_tokens).label("tokens"),
                func.sum(LlmUsageRecord.cost_amount).label("cost"),
            )
            .join(Group, LlmUsageRecord.group_id == Group.id)
            .where(LlmUsageRecord.group_id.isnot(None))
        )
        if since is not None:
            stmt = stmt.where(LlmUsageRecord.created_at >= since)
        stmt = stmt.group_by(LlmUsageRecord.group_id, Group.group_name).order_by(
            func.sum(LlmUsageRecord.total_tokens).desc()
        ).limit(limit)
        result = await self.session.execute(stmt)
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

    async def insights(self) -> dict:
        """Platform insights: document trend/formats, DAU, evidence quality."""
        from app.document.models import Document
        from app.qa.models import QaSession, QaMessage

        since = utcnow() - timedelta(days=29)
        days_ago = [(utcnow() - timedelta(days=29 - i)).date() for i in range(30)]

        # 1. Document upload trend (30d, zero-filled)
        upload_result = await self.session.execute(
            select(func.date(Document.uploaded_at).label("date"), func.count().label("cnt"))
            .where(
                Document.deleted == False,
                Document.uploaded_at.isnot(None),
                Document.uploaded_at >= since,
            )
            .group_by(func.date(Document.uploaded_at))
        )
        upload_map = {str(r.date): r.cnt for r in upload_result}
        upload_trend = [
            {"date": str(day), "count": upload_map.get(str(day), 0)} for day in days_ago
        ]

        # 2. Document format distribution
        fmt_result = await self.session.execute(
            select(Document.file_ext, func.count().label("cnt"))
            .where(Document.deleted == False)
            .group_by(Document.file_ext)
            .order_by(func.count().desc())
        )
        formats = [
            {"ext": (r.file_ext or "unknown").upper() or "unknown", "count": r.cnt}
            for r in fmt_result
        ]

        # 3. Daily active users (QA askers, 30d, zero-filled)
        dau_result = await self.session.execute(
            select(
                func.date(QaSession.created_at).label("date"),
                func.count(distinct(QaSession.user_id)).label("dau"),
            )
            .where(QaSession.created_at >= since)
            .group_by(func.date(QaSession.created_at))
        )
        dau_map = {str(r.date): r.dau for r in dau_result}
        active_trend = [
            {"date": str(day), "users": dau_map.get(str(day), 0)} for day in days_ago
        ]

        # 4. Evidence-level distribution of assistant answers
        ev_result = await self.session.execute(
            select(QaMessage.evidence_level, func.count().label("cnt"))
            .where(QaMessage.role == "ASSISTANT")
            .group_by(QaMessage.evidence_level)
        )
        evidence = {}
        for level, cnt in ev_result:
            key = level or "UNKNOWN"
            evidence[key] = evidence.get(key, 0) + cnt
        # Legacy rows (pre evidence_level): NO_EVIDENCE reason → NONE
        legacy_none = (await self.session.execute(
            select(func.count()).select_from(QaMessage).where(
                QaMessage.role == "ASSISTANT",
                QaMessage.evidence_level.is_(None),
                QaMessage.reason_code == "NO_EVIDENCE",
            )
        )).scalar() or 0
        if legacy_none:
            evidence["NONE"] = evidence.get("NONE", 0) + legacy_none
            evidence["UNKNOWN"] = evidence.get("UNKNOWN", 0) - legacy_none
            if evidence["UNKNOWN"] <= 0:
                evidence.pop("UNKNOWN", None)
        ordered = ["SUFFICIENT", "PARTIAL", "WEAK", "NONE", "UNKNOWN"]
        evidence_dist = [
            {"level": lv, "count": evidence.get(lv, 0)} for lv in ordered
        ]

        # Totals
        total_qa = (await self.session.execute(
            select(func.count()).select_from(QaSession)
        )).scalar() or 0
        refused_qa = (await self.session.execute(
            select(func.count()).select_from(QaMessage).where(
                QaMessage.role == "ASSISTANT",
                QaMessage.reason_code == "NO_EVIDENCE",
            )
        )).scalar() or 0

        return {
            "uploadTrend": upload_trend,
            "formats": formats,
            "activeTrend": active_trend,
            "evidenceDistribution": evidence_dist,
            "totalQa": total_qa,
            "refusedQa": refused_qa,
        }
