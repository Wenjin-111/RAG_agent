from pydantic import BaseModel, Field


class UpdateUserStatusRequest(BaseModel):
    status: str = Field(..., description="ACTIVE or DISABLED")


class AdminUserItemResponse(BaseModel):
    id: int
    user_code: str
    username: str
    email: str
    display_name: str
    system_role: str
    status: str
    must_change_password: bool
    last_login_at: str | None = None
    created_at: str | None = None
