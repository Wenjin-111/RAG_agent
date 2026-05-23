from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_admin
from app.common.response import ApiResponse
from app.common.security.context import AuthenticatedUser
from app.dependencies import get_db
from app.metrics.service import LlmUsageStatisticsService

router = APIRouter()


@router.get("/overview")
async def overview(
    _admin: AuthenticatedUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    service = LlmUsageStatisticsService(db)
    result = await service.overview()
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
    _admin: AuthenticatedUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    service = LlmUsageStatisticsService(db)
    result = await service.top_users(limit)
    return ApiResponse.ok(data=result)


@router.get("/rankings/groups")
async def top_groups(
    limit: int = 10,
    _admin: AuthenticatedUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    service = LlmUsageStatisticsService(db)
    result = await service.top_groups(limit)
    return ApiResponse.ok(data=result)
