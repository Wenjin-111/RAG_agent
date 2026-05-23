import pytest


@pytest.mark.asyncio
async def test_register(client):
    resp = await client.post("/api/auth/register", json={
        "username": "newuser",
        "email": "new@example.com",
        "displayName": "New User",
        "password": "NewUser@123456",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True


@pytest.mark.asyncio
async def test_login(client):
    resp = await client.post("/api/auth/login", json={
        "loginId": "testuser",
        "password": "Test@12345678",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert "accessToken" in data["data"]


@pytest.mark.asyncio
async def test_me_unauthorized(client):
    resp = await client.get("/api/auth/me")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_me_authorized(client, auth_headers):
    resp = await client.get("/api/auth/me", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["data"]["displayName"] == "Test User"
