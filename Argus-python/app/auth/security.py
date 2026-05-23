import hashlib
import secrets
import uuid
from base64 import urlsafe_b64encode
from datetime import datetime, timedelta

from app.common.time_utils import utcnow
from typing import Optional

import jwt
from passlib.hash import bcrypt
from sqlalchemy import select, update, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import User, UserRefreshToken
from app.auth.schemas import CurrentUserProfile
from app.config import settings

JWT_ALGORITHM = "HS256"
TOKEN_SEPARATOR = "."
SECRET_BYTES = 24


def hash_password(plain_password: str) -> str:
    return bcrypt.hash(plain_password)


def verify_password(plain_password: str, hashed: str) -> bool:
    return bcrypt.verify(plain_password, hashed)


def generate_user_code() -> str:
    return uuid.uuid4().hex[:12]


def issue_access_token(user: User) -> str:
    now = utcnow()
    payload = {
        "iss": settings.auth.issuer,
        "sub": user.user_code,
        "uid": user.id,
        "displayName": user.display_name,
        "systemRole": user.system_role,
        "mustChangePassword": user.must_change_password,
        "iat": now,
        "exp": now + timedelta(minutes=settings.auth.access_token_expire_minutes),
    }
    return jwt.encode(payload, settings.auth.jwt_secret, algorithm=JWT_ALGORITHM)


def parse_access_token(token: str) -> dict:
    return jwt.decode(token, settings.auth.jwt_secret, algorithms=[JWT_ALGORITHM],
                      options={"require": ["exp", "iss", "sub", "uid", "displayName", "systemRole"]})


def to_current_user(user: User) -> CurrentUserProfile:
    return CurrentUserProfile(
        user_id=user.id,
        user_code=user.user_code,
        display_name=user.display_name,
        system_role=user.system_role,
        must_change_password=user.must_change_password,
    )


class RefreshTokenService:
    def __init__(self, session: AsyncSession):
        self.session = session

    @staticmethod
    def generate_token() -> tuple[str, str]:
        token_id = uuid.uuid4().hex
        secret_bytes = secrets.token_bytes(SECRET_BYTES)
        secret = urlsafe_b64encode(secret_bytes).decode("ascii").rstrip("=")
        return token_id, f"{token_id}{TOKEN_SEPARATOR}{secret}"

    async def issue_token(self, user_id: int) -> str:
        token_id, raw_token = self.generate_token()
        token_hash = hash_password(raw_token)
        expires_at = datetime.utcnow() + timedelta(days=settings.auth.refresh_token_expire_days)

        entity = UserRefreshToken(
            user_id=user_id,
            token_id=token_id,
            token_hash=token_hash,
            expires_at=expires_at,
        )
        self.session.add(entity)
        await self.session.flush()
        return raw_token

    async def find_active_token(self, refresh_token: str) -> Optional[UserRefreshToken]:
        if not refresh_token or TOKEN_SEPARATOR not in refresh_token:
            return None
        token_id = refresh_token.split(TOKEN_SEPARATOR, 1)[0]

        result = await self.session.execute(
            select(UserRefreshToken).where(UserRefreshToken.token_id == token_id)
        )
        entity = result.scalar_one_or_none()
        if entity is None:
            return None
        if not verify_password(refresh_token, entity.token_hash):
            return None
        if entity.revoked_at is not None:
            return None
        if entity.expires_at < datetime.utcnow():
            return None
        return entity

    async def revoke_active_tokens(self, user_id: int) -> None:
        now = datetime.utcnow()
        await self.session.execute(
            update(UserRefreshToken)
            .where(
                UserRefreshToken.user_id == user_id,
                UserRefreshToken.revoked_at.is_(None),
                UserRefreshToken.expires_at > now,
            )
            .values(revoked_at=now)
        )

    async def revoke_token_by_id(self, token_id: int) -> bool:
        now = datetime.utcnow()
        result = await self.session.execute(
            update(UserRefreshToken)
            .where(UserRefreshToken.id == token_id, UserRefreshToken.revoked_at.is_(None))
            .values(revoked_at=now)
        )
        return result.rowcount > 0


async def find_user_by_login_id(session: AsyncSession, login_id: str) -> Optional[User]:
    result = await session.execute(
        select(User).where(
            or_(User.username == login_id, User.email == login_id)
        ).with_for_update()
    )
    rows = result.scalars().all()
    if len(rows) == 0:
        return None
    if len(rows) > 1:
        user_ids = {r.id for r in rows}
        if len(user_ids) > 1:
            return None  # ambiguous match
    return rows[0]
