"""
Database initialization script for Argus-Python.
Run once before first start:
    python init_db.py
"""
import asyncio
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("init_db")


async def main():
    from app.config import settings
    from app.dependencies import engine
    from app.database import Base
    from sqlalchemy import text

    # Import all models
    import app.auth.models           # noqa: F401
    import app.group.models          # noqa: F401
    import app.document.models       # noqa: F401
    import app.ingestion.models      # noqa: F401
    import app.assistant.models      # noqa: F401
    import app.metrics.models        # noqa: F401
    import app.models_config.models  # noqa: F401

    logger.info("Connecting to: %s", settings.database_url)

    async with engine.begin() as conn:
        # Enable pgvector
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        logger.info("pgvector extension enabled")

        # Create all tables
        await conn.run_sync(Base.metadata.create_all)
        logger.info("All tables created")

    # Seed admin
    if settings.dev_admin.enabled:
        from sqlalchemy import select
        from app.dependencies import async_session_factory
        from app.auth.models import User
        from app.auth.security import hash_password
        from app.auth.enums import SystemRole, UserStatus

        async with async_session_factory() as session:
            result = await session.execute(
                select(User).where(User.system_role == SystemRole.ADMIN.value)
            )
            if result.scalar_one_or_none() is None:
                admin = User(
                    user_code=settings.dev_admin.username,
                    username=settings.dev_admin.username,
                    email=settings.dev_admin.email,
                    display_name=settings.dev_admin.display_name,
                    password_hash=hash_password(settings.dev_admin.password),
                    system_role=SystemRole.ADMIN.value,
                    status=UserStatus.ACTIVE.value,
                )
                session.add(admin)
                await session.commit()
                logger.info("Admin seeded: %s / %s", settings.dev_admin.email, settings.dev_admin.password)
            else:
                logger.info("Admin already exists, skipped")

    await engine.dispose()
    logger.info("Database initialization complete!")


if __name__ == "__main__":
    import sys
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
