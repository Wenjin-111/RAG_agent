import logging
from typing import List

import httpx
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.time_utils import utcnow
from app.models_config.models import ModelConfig

logger = logging.getLogger(__name__)


class ModelConfigService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_models(self, user_id: int, model_type: str) -> List[dict]:
        result = await self.session.execute(
            select(ModelConfig)
            .where(ModelConfig.user_id == user_id, ModelConfig.model_type == model_type)
            .order_by(ModelConfig.created_at.desc())
        )
        return [
            {
                "id": m.id, "model_type": m.model_type, "display_name": m.display_name,
                "base_url": m.base_url, "api_key": m.api_key, "model_name": m.model_name,
                "is_active": m.is_active, "created_at": m.created_at.isoformat() if m.created_at else None,
            }
            for m in result.scalars()
        ]

    async def add_model(self, user_id: int, model_type: str, display_name: str,
                        base_url: str, api_key: str, model_name: str) -> dict:
        model = ModelConfig(
            user_id=user_id, model_type=model_type, display_name=display_name,
            base_url=base_url, api_key=api_key, model_name=model_name,
            is_active=False,
        )
        self.session.add(model)
        await self.session.flush()
        return {
            "id": model.id, "model_type": model.model_type, "display_name": model.display_name,
            "base_url": model.base_url, "api_key": model.api_key, "model_name": model.model_name,
            "is_active": model.is_active,
        }

    async def activate_model(self, user_id: int, model_id: int) -> dict:
        # Deactivate all models of the same type
        model = await self._get_model(user_id, model_id)
        if not model:
            from app.common.exception.exceptions import BusinessException
            raise BusinessException("模型配置不存在")

        await self.session.execute(
            update(ModelConfig)
            .where(ModelConfig.user_id == user_id, ModelConfig.model_type == model.model_type)
            .values(is_active=False)
        )

        model.is_active = True
        model.updated_at = utcnow()
        await self.session.flush()

        return {
            "id": model.id, "model_type": model.model_type, "display_name": model.display_name,
            "base_url": model.base_url, "api_key": model.api_key, "model_name": model.model_name,
            "is_active": True,
        }

    async def delete_model(self, user_id: int, model_id: int):
        model = await self._get_model(user_id, model_id)
        if not model:
            from app.common.exception.exceptions import BusinessException
            raise BusinessException("模型配置不存在")
        await self.session.delete(model)
        await self.session.flush()

    async def get_active_model(self, user_id: int, model_type: str) -> dict | None:
        result = await self.session.execute(
            select(ModelConfig)
            .where(ModelConfig.user_id == user_id, ModelConfig.model_type == model_type, ModelConfig.is_active == True)
        )
        m = result.scalar_one_or_none()
        if not m:
            return None
        return {
            "base_url": m.base_url, "api_key": m.api_key, "model_name": m.model_name,
        }

    async def _get_model(self, user_id: int, model_id: int) -> ModelConfig | None:
        result = await self.session.execute(
            select(ModelConfig)
            .where(ModelConfig.id == model_id, ModelConfig.user_id == user_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def test_connection(base_url: str, api_key: str, model_name: str, model_type: str) -> dict:
        if model_type == "mineru":
            return await ModelConfigService._test_mineru(base_url, api_key, model_name)
        url = base_url.rstrip("/")
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                if model_type == "chat":
                    resp = await client.post(
                        f"{url}/chat/completions",
                        json={"model": model_name, "messages": [{"role": "user", "content": "hi"}], "max_tokens": 5},
                        headers={"Authorization": f"Bearer {api_key}"},
                    )
                else:
                    resp = await client.post(
                        f"{url}/embeddings",
                        json={"model": model_name, "input": "test"},
                        headers={"Authorization": f"Bearer {api_key}"},
                    )
                if resp.status_code < 500:
                    return {"ok": True, "status": resp.status_code, "message": "连接成功"}
                return {"ok": False, "status": resp.status_code, "message": f"API 返回 {resp.status_code}"}
        except Exception as e:
            return {"ok": False, "status": 0, "message": str(e)[:200]}

    @staticmethod
    async def _test_mineru(base_url: str, api_key: str, model_name: str) -> dict:
        """验证 MinerU token：申请一次上传链接（不消耗解析额度）"""
        url = (base_url or "https://mineru.net").rstrip("/") + "/api/v4/file-urls/batch"
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    url,
                    json={"files": [{"name": "connection-test.pdf"}],
                          "model_version": model_name or "vlm"},
                    headers={"Content-Type": "application/json",
                             "Authorization": f"Bearer {api_key}"},
                )
            data = resp.json()
            if data.get("code") == 0:
                return {"ok": True, "status": resp.status_code, "message": "连接成功"}
            return {"ok": False, "status": resp.status_code, "message": data.get("msg", "连接失败")}
        except Exception as e:
            return {"ok": False, "status": 0, "message": str(e)[:200]}
