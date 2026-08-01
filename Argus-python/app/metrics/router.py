from datetime import timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_admin
from app.common.response import ApiResponse
from app.common.security.context import AuthenticatedUser
from app.common.time_utils import utcnow
from app.dependencies import get_db
from app.metrics.service import LlmUsageStatisticsService

router = APIRouter()

PERIOD_DAYS = {"TODAY": 0, "LAST_7_DAYS": 7, "LAST_14_DAYS": 14, "LAST_30_DAYS": 30}


def _period_since(period: str):
    """Return the datetime threshold for a given period string, or None for all-time."""
    days = PERIOD_DAYS.get(period)
    if days is None:
        return None
    if days == 0:
        return utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    return utcnow() - timedelta(days=days)


@router.get("/overview")
async def overview(
    _admin: AuthenticatedUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    service = LlmUsageStatisticsService(db)
    result = await service.overview()
    return ApiResponse.ok(data=result)


@router.get("/insights")
async def insights(
    _admin: AuthenticatedUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    service = LlmUsageStatisticsService(db)
    result = await service.insights()
    return ApiResponse.ok(data=result)


@router.get("/trend")
async def trend(
    days: int = 30,
    _admin: AuthenticatedUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    service = LlmUsageStatisticsService(db)
    result = await service.daily_trend(days)
    return ApiResponse.ok(data=result)


@router.get("/rankings/users")
async def top_users(
    limit: int = 10,
    period: str = Query(default="LAST_7_DAYS"),
    _admin: AuthenticatedUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    service = LlmUsageStatisticsService(db)
    result = await service.top_users(limit, since=_period_since(period))
    return ApiResponse.ok(data=result)


@router.get("/rankings/groups")
async def top_groups(
    limit: int = 10,
    period: str = Query(default="LAST_7_DAYS"),
    _admin: AuthenticatedUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    service = LlmUsageStatisticsService(db)
    result = await service.top_groups(limit, since=_period_since(period))
    return ApiResponse.ok(data=result)
