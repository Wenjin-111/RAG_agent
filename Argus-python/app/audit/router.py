from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import AuditService
from app.auth.dependencies import require_admin
from app.common.response import ApiResponse
from app.common.security.context import AuthenticatedUser
from app.dependencies import get_db

router = APIRouter()


@router.get("/audit-logs")
async def list_audit_logs(
    action: str = Query(default=""),
    user_id: int | None = Query(default=None, alias="userId"),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    _admin: AuthenticatedUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    service = AuditService(db)
    result = await service.list_logs(
        action=action or None,
        user_id=user_id,
        page=page,
        limit=limit,
    )
    return ApiResponse.ok(data=result)
