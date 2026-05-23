from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    login_id: str = Field(..., min_length=1, max_length=128, alias="loginId", description="用户名或邮箱")
    password: str = Field(..., min_length=1, max_length=256)

    model_config = {"populate_by_name": True}


class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=64)
    email: str = Field(..., min_length=1, max_length=128)
    display_name: str = Field(..., min_length=1, max_length=128, alias="displayName")
    password: str = Field(..., min_length=8, max_length=256)

    model_config = {"populate_by_name": True}


class CurrentUserProfile(BaseModel):
    user_id: int = Field(alias="userId")
    user_code: str = Field(alias="userCode")
    display_name: str = Field(alias="displayName")
    system_role: str = Field(alias="systemRole")
    must_change_password: bool = Field(alias="mustChangePassword")

    model_config = {"populate_by_name": True}


class AuthTokensResponse(BaseModel):
    access_token: str = Field(alias="accessToken")
    refresh_token: str = Field(alias="refreshToken")
    must_change_password: bool = Field(alias="mustChangePassword")
    current_user: CurrentUserProfile = Field(alias="currentUser")

    model_config = {"populate_by_name": True}


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(..., alias="currentPassword")
    new_password: str = Field(..., min_length=8, max_length=256, alias="newPassword")

    model_config = {"populate_by_name": True}
