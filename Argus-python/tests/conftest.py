import asyncio
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.database import Base
from app.dependencies import get_db, async_session_factory


@pytest_asyncio.fixture
async def client():
    async with async_session_factory() as session:
        async def override_get_db():
            yield session
        app.dependency_overrides[get_db] = override_get_db

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac

        app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def auth_headers(client):
    # Register test user
    resp = await client.post("/api/auth/register", json={
        "username": "testuser",
        "email": "test@example.com",
        "displayName": "Test User",
        "password": "Test@12345678",
    })
    # Login
    resp = await client.post("/api/auth/login", json={
        "loginId": "testuser",
        "password": "Test@12345678",
    })
    data = resp.json()
    token = data["data"]["accessToken"]
    return {"Authorization": f"Bearer {token}"}
