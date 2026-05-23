from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user, require_admin
from app.auth.schemas import ChangePasswordRequest
from app.common.response import ApiResponse
from app.common.security.context import AuthenticatedUser
from app.dependencies import get_db
from app.user.schemas import UpdateUserStatusRequest
from app.user.service import AccountService, AdminUserService

router = APIRouter()


# ---- Account routes ----

@router.post("/account/change-password")
async def change_password(
    request: ChangePasswordRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = AccountService(db)
    await service.change_password(current_user.user_id, request)
    return ApiResponse.ok(message="密码修改成功")


# ---- Admin user management routes ----

@router.get("/admin/users")
async def list_users(
    _admin: AuthenticatedUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    service = AdminUserService(db)
    users = await service.list_users()
    return ApiResponse.ok(data=users)


@router.get("/admin/users/{user_id}")
async def get_user(
    user_id: int,
    _admin: AuthenticatedUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    service = AdminUserService(db)
    user = await service.get_user(user_id)
    return ApiResponse.ok(data=user)


@router.patch("/admin/users/{user_id}/status")
async def update_user_status(
    user_id: int,
    request: UpdateUserStatusRequest,
    _admin: AuthenticatedUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    service = AdminUserService(db)
    await service.update_user_status(user_id, request.status)
    return ApiResponse.ok(message="用户状态更新成功")


@router.put("/admin/users/{user_id}/reset-password")
async def reset_password(
    user_id: int,
    _admin: AuthenticatedUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    service = AdminUserService(db)
    await service.reset_password(user_id, "Admin@123456")
    return ApiResponse.ok(message="密码重置成功")
