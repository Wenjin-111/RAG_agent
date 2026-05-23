class AppException(Exception):
    """Base application exception."""
    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class BusinessException(AppException):
    """400 - Business logic error (e.g. duplicate username, invalid state)."""
    pass


class AuthenticationException(AppException):
    """401 - Authentication required or token invalid."""
    pass


class ForbiddenException(AppException):
    """403 - Authenticated but insufficient permissions."""
    pass
