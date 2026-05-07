from httpx import AsyncClient

USER = {
    "username": "testuser",
    "email": "test@example.com",
    "password": "TestPass123!",
}


async def test_register_success(client: AsyncClient) -> None:
    resp = await client.post("/api/v1/auth/register", json=USER)
    assert resp.status_code == 200
    data = resp.json()
    assert data["username"] == USER["username"]
    assert data["email"] == USER["email"]
    assert "access_token" in resp.cookies
    assert "refresh_token" in resp.cookies


async def test_register_duplicate_email(client: AsyncClient) -> None:
    await client.post("/api/v1/auth/register", json=USER)
    resp = await client.post(
        "/api/v1/auth/register", json={**USER, "username": "other"}
    )
    assert resp.status_code == 409
    assert resp.json()["errorCode"] == "USER_ALREADY_EXISTS"


async def test_register_duplicate_username(client: AsyncClient) -> None:
    await client.post("/api/v1/auth/register", json=USER)
    resp = await client.post(
        "/api/v1/auth/register", json={**USER, "email": "other@example.com"}
    )
    assert resp.status_code == 409
    assert resp.json()["errorCode"] == "USERNAME_ALREADY_EXISTS"


async def test_register_weak_password(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/auth/register", json={**USER, "password": "short"}
    )
    assert resp.status_code == 422


async def test_login_success(client: AsyncClient) -> None:
    await client.post("/api/v1/auth/register", json=USER)
    client.cookies.clear()
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": USER["email"], "password": USER["password"]},
    )
    assert resp.status_code == 200
    assert "access_token" in resp.cookies


async def test_login_wrong_password(client: AsyncClient) -> None:
    await client.post("/api/v1/auth/register", json=USER)
    client.cookies.clear()
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": USER["email"], "password": "WrongPass1!"},
    )
    assert resp.status_code == 401
    assert resp.json()["errorCode"] == "INVALID_CREDENTIALS"


async def test_login_nonexistent_user(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "nobody@example.com", "password": "TestPass123!"},
    )
    assert resp.status_code == 401


async def test_refresh_success(client: AsyncClient) -> None:
    await client.post("/api/v1/auth/register", json=USER)
    resp = await client.post("/api/v1/auth/refresh")
    assert resp.status_code == 200


async def test_refresh_without_cookie(client: AsyncClient) -> None:
    resp = await client.post("/api/v1/auth/refresh")
    assert resp.status_code == 401
    assert resp.json()["errorCode"] == "REFRESH_TOKEN_MISSING"


async def test_logout(client: AsyncClient) -> None:
    await client.post("/api/v1/auth/register", json=USER)
    resp = await client.post("/api/v1/auth/logout")
    assert resp.status_code == 200
