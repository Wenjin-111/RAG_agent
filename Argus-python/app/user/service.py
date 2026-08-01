import logging
from datetime import datetime

from app.common.time_utils import utcnow
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

from app.auth.models import User
from app.auth.security import hash_password, verify_password
from app.auth.schemas import ChangePasswordRequest
from app.auth.enums import SystemRole, UserStatus
from app.common.exception.exceptions import BusinessException


class AccountService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def change_password(self, user_id: int, request: ChangePasswordRequest) -> None:
        result = await self.session.execute(select(User).where(User.id == user_id))
        user = result.scalar_one()
        if not user.password_hash or not verify_password(request.current_password, user.password_hash):
            raise BusinessException("当前密码错误")
        if request.current_password == request.new_password:
            raise BusinessException("新密码不能与当前密码相同")

        user.password_hash = hash_password(request.new_password)
        user.must_change_password = False
        await self.session.flush()


class AdminUserService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_users(self) -> list[dict]:
        result = await self.session.execute(
            select(User).order_by(User.created_at.desc())
        )
        return [
            {
                "user_id": u.id,
                "user_code": u.user_code,
                "username": u.username,
                "email": u.email,
                "display_name": u.display_name,
                "system_role": u.system_role,
                "status": u.status,
                "must_change_password": u.must_change_password,
                "last_login_at": u.last_login_at.isoformat() + "Z" if u.last_login_at else None,
                "created_at": u.created_at.isoformat() + "Z" if u.created_at else None,
            }
            for u in result.scalars()
        ]

    async def get_user(self, user_id: int) -> dict:
        result = await self.session.execute(select(User).where(User.id == user_id))
        u = result.scalar_one_or_none()
        if u is None:
            raise BusinessException("用户不存在")
        return {
            "user_id": u.id,
            "user_code": u.user_code,
            "username": u.username,
            "email": u.email,
            "display_name": u.display_name,
            "system_role": u.system_role,
            "status": u.status,
            "must_change_password": u.must_change_password,
            "last_login_at": u.last_login_at.isoformat() if u.last_login_at else None,
            "created_at": u.created_at.isoformat() if u.created_at else None,
        }

    async def update_user_status(self, user_id: int, status: str) -> None:
        if status not in {UserStatus.ACTIVE.value, UserStatus.DISABLED.value}:
            raise BusinessException("无效的用户状态")
        result = await self.session.execute(
            update(User).where(User.id == user_id).values(status=status, updated_at=utcnow())
        )
        if result.rowcount == 0:
            raise BusinessException("用户不存在")

    async def reset_password(self, user_id: int, new_password: str) -> None:
        result = await self.session.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if user is None:
            raise BusinessException("用户不存在")
        user.password_hash = hash_password(new_password)
        user.must_change_password = True
        await self.session.flush()

    async def create_user(self, username: str, email: str, display_name: str) -> dict:
        """Create a user with the default password; must change on first login."""
        username = username.strip()
        email = email.strip()
        display_name = display_name.strip()
        if not username or not email or not display_name:
            raise BusinessException("用户名、邮箱、显示名称均不能为空")

        result = await self.session.execute(select(User).where(User.username == username))
        if result.scalar_one_or_none():
            raise BusinessException("用户名已存在")
        result = await self.session.execute(select(User).where(User.email == email))
        if result.scalar_one_or_none():
            raise BusinessException("邮箱已存在")

        user = User(
            user_code=username,
            username=username,
            email=email,
            display_name=display_name,
            password_hash=hash_password("Admin@123456"),
            system_role=SystemRole.USER.value,
            status=UserStatus.ACTIVE.value,
            must_change_password=True,
        )
        self.session.add(user)
        await self.session.flush()
        logger.info("Admin created user: %s (%s)", username, email)
        return {
            "user_id": user.id,
            "username": user.username,
            "email": user.email,
            "display_name": user.display_name,
        }
