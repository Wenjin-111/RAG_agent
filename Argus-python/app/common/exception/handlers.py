from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.common.exception.exceptions import (
    AppException,
    BusinessException,
    AuthenticationException,
    ForbiddenException,
)


async def business_exception_handler(request: Request, exc: BusinessException) -> JSONResponse:
    return JSONResponse(status_code=400, content={"success": False, "data": None, "message": exc.message})


async def authentication_exception_handler(request: Request, exc: AuthenticationException) -> JSONResponse:
    return JSONResponse(status_code=401, content={"success": False, "data": None, "message": exc.message})


async def forbidden_exception_handler(request: Request, exc: ForbiddenException) -> JSONResponse:
    return JSONResponse(status_code=403, content={"success": False, "data": None, "message": exc.message})


async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    return JSONResponse(status_code=400, content={"success": False, "data": None, "message": exc.message})


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    first_error = exc.errors()[0] if exc.errors() else {"msg": "Validation error"}
    return JSONResponse(status_code=422, content={"success": False, "data": None, "message": first_error["msg"]})


async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(status_code=500, content={"success": False, "data": None, "message": "Internal server error"})
