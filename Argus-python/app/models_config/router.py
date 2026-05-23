from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user, require_admin
from app.common.response import ApiResponse
from app.common.security.context import AuthenticatedUser
from app.dependencies import get_db
from app.models_config.service import ModelConfigService

router = APIRouter()


@router.get("/model-configs")
async def list_models(
    model_type: str = Query(..., alias="modelType"),
    _admin: AuthenticatedUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    service = ModelConfigService(db)
    models = await service.list_models(_admin.user_id, model_type)
    return ApiResponse.ok(data=models)


@router.post("/model-configs")
async def add_model(
    body: dict,
    _admin: AuthenticatedUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    service = ModelConfigService(db)
    result = await service.add_model(
        _admin.user_id,
        model_type=body.get("model_type", body.get("modelType", "chat")),
        display_name=body.get("display_name", body.get("displayName", "")),
        base_url=body.get("base_url", body.get("baseUrl", "")),
        api_key=body.get("api_key", body.get("apiKey", "")),
        model_name=body.get("model_name", body.get("modelName", "")),
    )
    return ApiResponse.ok(data=result)


@router.patch("/model-configs/{model_id}/activate")
async def activate_model(
    model_id: int,
    _admin: AuthenticatedUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    service = ModelConfigService(db)
    result = await service.activate_model(_admin.user_id, model_id)
    return ApiResponse.ok(data=result)


@router.delete("/model-configs/{model_id}")
async def delete_model(
    model_id: int,
    _admin: AuthenticatedUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    service = ModelConfigService(db)
    await service.delete_model(_admin.user_id, model_id)
    return ApiResponse.ok(message="已删除")


@router.post("/model-configs/test")
async def test_connection(
    body: dict,
    _admin: AuthenticatedUser = Depends(require_admin),
):
    result = await ModelConfigService.test_connection(
        base_url=body.get("base_url", body.get("baseUrl", "")),
        api_key=body.get("api_key", body.get("apiKey", "")),
        model_name=body.get("model_name", body.get("modelName", "")),
        model_type=body.get("model_type", body.get("modelType", "chat")),
    )
    return ApiResponse.ok(data=result)
