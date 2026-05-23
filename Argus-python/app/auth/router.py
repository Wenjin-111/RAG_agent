from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.schemas import LoginRequest, RegisterRequest, AuthTokensResponse, CurrentUserProfile
from app.auth.service import AuthService
from app.auth.dependencies import get_current_user
from app.common.response import ApiResponse
from app.common.security.context import AuthenticatedUser, UserContext
from app.config import settings
from app.dependencies import get_db

router = APIRouter()


@router.post("/login")
async def login(request: LoginRequest, response: Response, db: AsyncSession = Depends(get_db)):
    service = AuthService(db)
    result = await service.login(request.login_id, request.password)
    _set_refresh_cookie(response, result["refresh_token"])
    return ApiResponse.ok(
        data=AuthTokensResponse(
            accessToken=result["access_token"],
            refreshToken=result["refresh_token"],
            mustChangePassword=result["must_change_password"],
            currentUser=CurrentUserProfile(**result["current_user"]),
        )
    )


@router.post("/register")
async def register(request: RegisterRequest, db: AsyncSession = Depends(get_db)):
    service = AuthService(db)
    await service.register(request)
    return ApiResponse.ok(message="注册成功")


@router.post("/refresh")
async def refresh(request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    refresh_token = request.cookies.get(settings.auth.refresh_cookie_name)
    service = AuthService(db)
    result = await service.refresh(refresh_token)
    _set_refresh_cookie(response, result["refresh_token"])
    return ApiResponse.ok(
        data=AuthTokensResponse(
            accessToken=result["access_token"],
            refreshToken=result["refresh_token"],
            mustChangePassword=result["must_change_password"],
            currentUser=CurrentUserProfile(**result["current_user"]),
        )
    )


@router.post("/logout")
async def logout(request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    refresh_token = request.cookies.get(settings.auth.refresh_cookie_name)
    service = AuthService(db)
    await service.logout(refresh_token)
    _clear_refresh_cookie(response)
    return ApiResponse.ok(message="已登出")


@router.get("/me")
async def me(current_user: AuthenticatedUser = Depends(get_current_user)):
    return ApiResponse.ok(
        data=CurrentUserProfile(
            user_id=current_user.user_id,
            user_code=current_user.user_code,
            display_name=current_user.display_name,
            system_role=current_user.system_role,
            must_change_password=current_user.must_change_password,
        )
    )


def _set_refresh_cookie(response: Response, token: str):
    response.set_cookie(
        key=settings.auth.refresh_cookie_name,
        value=token,
        httponly=True,
        max_age=settings.auth.refresh_token_expire_days * 86400,
        path="/api",
        secure=settings.auth.refresh_cookie_secure,
        samesite="lax",
    )


def _clear_refresh_cookie(response: Response):
    response.delete_cookie(
        key=settings.auth.refresh_cookie_name,
        path="/api",
        secure=settings.auth.refresh_cookie_secure,
    )
