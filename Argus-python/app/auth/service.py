import logging
import re
from datetime import datetime
from app.common.time_utils import utcnow

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import User, UserRefreshToken
from app.auth.schemas import RegisterRequest
from app.auth.security import (
    hash_password,
    verify_password,
    issue_access_token,
    find_user_by_login_id,
    RefreshTokenService,
)
from app.auth.enums import SystemRole, UserStatus
from app.common.exception.exceptions import BusinessException

logger = logging.getLogger(__name__)

INVALID_CREDENTIALS = "账号或密码错误"
USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")
RESERVED_USERNAMES = {"admin", "root", "null", "undefined", "system"}
TOKEN_SEPARATOR = "."


class AuthService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self._refresh = RefreshTokenService(session)

    async def login(self, login_id: str, password: str) -> dict:
        login_id = login_id.strip()
        if not login_id or len(login_id) > 128:
            raise BusinessException(INVALID_CREDENTIALS)
        if not password or len(password) > 256:
            raise BusinessException(INVALID_CREDENTIALS)
        if len(password.encode("utf-8")) > 72:
            raise BusinessException("密码长度超过安全上限，请控制在 72 字节以内")

        user = await find_user_by_login_id(self.session, login_id)
        if user is None:
            raise BusinessException(INVALID_CREDENTIALS)
        if user.status == UserStatus.DISABLED.value:
            raise BusinessException("账号已被禁用")
        if not user.password_hash or not verify_password(password, user.password_hash):
            raise BusinessException(INVALID_CREDENTIALS)

        await self._refresh.revoke_active_tokens(user.id)
        refresh_token = await self._refresh.issue_token(user.id)

        await self.session.execute(
            update(User).where(User.id == user.id).values(last_login_at=utcnow())
        )

        logger.info("用户登录成功: userId=%s, username=%s", user.id, user.username)
        return self._build_token_result(user, refresh_token)

    async def register(self, request: RegisterRequest) -> None:
        username = request.username.strip()
        email = request.email.strip()
        display_name = request.display_name.strip()

        if not username or len(username) > 64:
            raise BusinessException("用户名不能为空")
        if not USERNAME_PATTERN.match(username):
            raise BusinessException("用户名不合法")
        if username.lower() in RESERVED_USERNAMES:
            raise BusinessException("用户名不合法")
        if not email or len(email) > 128:
            raise BusinessException("邮箱不能为空")
        if not display_name or len(display_name) > 128:
            raise BusinessException("显示名称不能为空")
        if len(request.password) > 256:
            raise BusinessException("密码长度非法")

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
            password_hash=hash_password(request.password),
            system_role=SystemRole.USER.value,
            status=UserStatus.ACTIVE.value,
            must_change_password=False,
        )
        self.session.add(user)
        await self.session.flush()
        logger.info("用户注册成功: username=%s, email=%s", user.username, user.email)

    async def refresh(self, refresh_token: str | None) -> dict:
        if not refresh_token:
            raise BusinessException("refresh token 不存在或已失效")

        active_token = await self._refresh.find_active_token(refresh_token)
        if active_token is None:
            raise BusinessException("refresh token 不存在或已失效")

        result = await self.session.execute(select(User).where(User.id == active_token.user_id))
        user = result.scalar_one_or_none()
        if user is None:
            raise BusinessException("用户不存在")
        if user.status == UserStatus.DISABLED.value:
            raise BusinessException("账号已被禁用")

        if not await self._refresh.revoke_token_by_id(active_token.id):
            await self._refresh.revoke_active_tokens(user.id)
            logger.warning("refresh token 重放攻击: userId=%s", user.id)
            raise BusinessException("refresh token 已被使用，请重新登录")

        new_refresh_token = await self._refresh.issue_token(user.id)
        logger.info("令牌刷新成功: userId=%s", user.id)
        return self._build_token_result(user, new_refresh_token)

    async def logout(self, refresh_token: str | None) -> None:
        if not refresh_token or TOKEN_SEPARATOR not in refresh_token:
            return
        token_id = refresh_token.split(TOKEN_SEPARATOR, 1)[0]
        now = utcnow()
        result = await self.session.execute(
            update(UserRefreshToken)
            .where(UserRefreshToken.token_id == token_id, UserRefreshToken.revoked_at.is_(None))
            .values(revoked_at=now)
        )
        if result.rowcount > 0:
            logger.info("用户登出成功")

    @staticmethod
    def _build_token_result(user: User, refresh_token: str) -> dict:
        return {
            "access_token": issue_access_token(user),
            "refresh_token": refresh_token,
            "must_change_password": user.must_change_password,
            "current_user": {
                "user_id": user.id,
                "user_code": user.user_code,
                "display_name": user.display_name,
                "system_role": user.system_role,
                "must_change_password": user.must_change_password,
            },
        }
