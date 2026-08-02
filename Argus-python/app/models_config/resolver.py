from app.config import settings
from app.models_config.service import ModelConfigService


async def get_chat_config(user_id: int) -> dict:
    """Get chat model config for the user, falling back to .env defaults."""
    # Only admin users can have custom configs
    try:
        from app.dependencies import async_session_factory
        async with async_session_factory() as session:
            service = ModelConfigService(session)
            active = await service.get_active_model(user_id, "chat")
            await session.commit()
            if active:
                return active
    except Exception:
        pass

    return {
        "base_url": settings.chat.base_url,
        "api_key": settings.chat.api_key,
        "model_name": settings.chat.model_name,
    }


async def get_embedding_config(user_id: int) -> dict:
    """Get embedding model config for the user, falling back to .env defaults."""
    try:
        from app.dependencies import async_session_factory
        async with async_session_factory() as session:
            service = ModelConfigService(session)
            active = await service.get_active_model(user_id, "embedding")
            await session.commit()
            if active:
                return active
    except Exception:
        pass

    return {
        "base_url": settings.embedding.base_url,
        "api_key": settings.embedding.api_key,
        "model_name": settings.embedding.model_name,
    }


async def get_mineru_config(user_id: int) -> dict:
    """Get MinerU document-parsing config, falling back to .env defaults.

    model_configs 表中 model_type="mineru"：base_url=mineru.net, api_key=token,
    model_name=vlm|pipeline。管理员在系统设置 → 添加模型 中维护。
    """
    try:
        from app.dependencies import async_session_factory
        async with async_session_factory() as session:
            service = ModelConfigService(session)
            active = await service.get_active_model(user_id, "mineru")
            await session.commit()
            if active:
                return active
    except Exception:
        pass

    return {
        "base_url": settings.mineru.base_url,
        "api_key": settings.mineru.token,
        "model_name": settings.mineru.model,
    }
