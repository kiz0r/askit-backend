from httpx import AsyncClient

USER = {
    "username": "profileuser",
    "email": "profile@example.com",
    "password": "TestPass123!",
}


async def test_get_profile(client: AsyncClient) -> None:
    await client.post("/api/v1/auth/register", json=USER)
    resp = await client.get("/api/v1/user/profile")
    assert resp.status_code == 200
    assert resp.json()["username"] == USER["username"]
    assert resp.json()["email"] == USER["email"]


async def test_get_profile_unauthenticated(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/user/profile")
    assert resp.status_code == 401


async def test_update_username(client: AsyncClient) -> None:
    await client.post("/api/v1/auth/register", json=USER)
    resp = await client.patch("/api/v1/user/profile", json={"username": "newname"})
    assert resp.status_code == 200
    assert resp.json()["username"] == "newname"


async def test_update_email(client: AsyncClient) -> None:
    await client.post("/api/v1/auth/register", json=USER)
    resp = await client.patch("/api/v1/user/profile", json={"email": "new@example.com"})
    assert resp.status_code == 200
    assert resp.json()["email"] == "new@example.com"


async def test_update_username_conflict(client: AsyncClient) -> None:
    await client.post("/api/v1/auth/register", json=USER)
    saved = dict(client.cookies)
    await client.post(
        "/api/v1/auth/register",
        json={
            "username": "taken",
            "email": "taken@example.com",
            "password": "TestPass123!",
        },
    )
    # Restore first user's session (second register replaced cookies)
    client.cookies.clear()
    client.cookies.update(saved)
    resp = await client.patch("/api/v1/user/profile", json={"username": "taken"})
    assert resp.status_code == 409


async def test_change_password_success(client: AsyncClient) -> None:
    await client.post("/api/v1/auth/register", json=USER)
    resp = await client.post(
        "/api/v1/user/password",
        json={"currentPassword": USER["password"], "newPassword": "NewPass456!"},
    )
    assert resp.status_code == 200

    # Old password no longer works
    client.cookies.clear()
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": USER["email"], "password": USER["password"]},
    )
    assert login.status_code == 401

    # New password works
    login2 = await client.post(
        "/api/v1/auth/login",
        json={"email": USER["email"], "password": "NewPass456!"},
    )
    assert login2.status_code == 200


async def test_change_password_wrong_current(client: AsyncClient) -> None:
    await client.post("/api/v1/auth/register", json=USER)
    resp = await client.post(
        "/api/v1/user/password",
        json={"currentPassword": "WrongPass1!", "newPassword": "NewPass456!"},
    )
    assert resp.status_code == 401
    assert resp.json()["errorCode"] == "INVALID_CREDENTIALS"


async def test_game_history_empty(client: AsyncClient) -> None:
    await client.post("/api/v1/auth/register", json=USER)
    resp = await client.get("/api/v1/user/game-history")
    assert resp.status_code == 200
    assert resp.json()["items"] == []
    assert resp.json()["total"] == 0
