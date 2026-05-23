from contextvars import ContextVar
from typing import Optional
from pydantic import BaseModel


class AuthenticatedUser(BaseModel):
    user_id: int
    user_code: str
    display_name: str
    system_role: str
    must_change_password: bool = False


_user_context: ContextVar[Optional[AuthenticatedUser]] = ContextVar("current_user", default=None)


class UserContext:
    @staticmethod
    def get() -> Optional[AuthenticatedUser]:
        return _user_context.get()

    @staticmethod
    def set(user: AuthenticatedUser) -> None:
        _user_context.set(user)

    @staticmethod
    def clear() -> None:
        _user_context.set(None)
