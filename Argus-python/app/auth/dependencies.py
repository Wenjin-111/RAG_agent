from fastapi import Request, Depends
from app.auth.security import parse_access_token
from app.common.security.context import AuthenticatedUser, UserContext
from app.common.exception.exceptions import AuthenticationException, ForbiddenException
from app.config import settings

WHITELIST_PATHS = {
    "/api/auth/login",
    "/api/auth/register",
    "/api/auth/refresh",
    "/api/auth/logout",
}


async def get_current_user(request: Request) -> AuthenticatedUser:
    if request.url.path in WHITELIST_PATHS:
        raise AuthenticationException("Token 无效或已过期")

    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:].strip()
    else:
        token = auth_header.strip()

    if not token:
        raise AuthenticationException("Token 无效或已过期")

    try:
        claims = parse_access_token(token)
    except Exception:
        raise AuthenticationException("Token 无效或已过期")

    if claims.get("iss") != settings.auth.issuer:
        raise AuthenticationException("Token 无效或已过期")

    user = AuthenticatedUser(
        user_id=claims["uid"],
        user_code=claims["sub"],
        display_name=claims["displayName"],
        system_role=claims["systemRole"],
        must_change_password=claims.get("mustChangePassword", False),
    )
    UserContext.set(user)
    return user


async def require_admin(current_user: AuthenticatedUser = Depends(get_current_user)) -> AuthenticatedUser:
    if current_user.system_role != "ADMIN":
        raise ForbiddenException("需要管理员权限")
    return current_user
