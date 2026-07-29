from httpx import AsyncClient

USER = {"username": "quizuser", "email": "quiz@example.com", "password": "TestPass123!"}
USER2 = {
    "username": "quizuser2",
    "email": "quiz2@example.com",
    "password": "TestPass123!",
}

_QUIZ = {
    "title": "Test Quiz",
    "settings": {"defaultTimePerQuestion": 30000, "maxParticipants": 10},
    "questions": [],
}

_QUIZ_WITH_QUESTION = {
    "title": "Test Quiz",
    "settings": {"defaultTimePerQuestion": 30000, "maxParticipants": 10},
    "questions": [
        {
            "text": "What is 2+2?",
            "timeLimit": 30000,
            "answers": [
                {"text": "3", "isCorrect": False},
                {"text": "4", "isCorrect": True},
            ],
        }
    ],
}


async def _create_quiz(client: AsyncClient, with_question: bool = False) -> str:
    await client.post("/api/v1/auth/register", json=USER)
    body = _QUIZ_WITH_QUESTION if with_question else _QUIZ
    resp = await client.post("/api/v1/quiz", json=body)
    assert resp.status_code == 200
    quiz_id: str = resp.json()["quizId"]
    return quiz_id


async def test_create_quiz(client: AsyncClient) -> None:
    quiz_id = await _create_quiz(client)
    assert quiz_id


async def test_list_quizzes_returns_only_own(client: AsyncClient) -> None:
    await _create_quiz(client)

    # Second user creates their own quiz
    client.cookies.clear()
    await client.post("/api/v1/auth/register", json=USER2)
    await client.post("/api/v1/quiz", json=_QUIZ)

    resp = await client.get("/api/v1/quiz")
    assert resp.status_code == 200
    assert len(resp.json()["items"]) == 1


async def test_get_own_quiz(client: AsyncClient) -> None:
    quiz_id = await _create_quiz(client)
    resp = await client.get(f"/api/v1/quiz/{quiz_id}")
    assert resp.status_code == 200
    assert resp.json()["quizId"] == quiz_id


async def test_get_foreign_quiz_denied(client: AsyncClient) -> None:
    quiz_id = await _create_quiz(client)

    client.cookies.clear()
    await client.post("/api/v1/auth/register", json=USER2)
    resp = await client.get(f"/api/v1/quiz/{quiz_id}")
    assert resp.status_code in (403, 404)


async def test_update_quiz(client: AsyncClient) -> None:
    quiz_id = await _create_quiz(client)
    resp = await client.patch(f"/api/v1/quiz/{quiz_id}", json={"title": "Updated"})
    assert resp.status_code == 200
    assert resp.json()["title"] == "Updated"


async def test_update_foreign_quiz_denied(client: AsyncClient) -> None:
    quiz_id = await _create_quiz(client)

    client.cookies.clear()
    await client.post("/api/v1/auth/register", json=USER2)
    resp = await client.patch(f"/api/v1/quiz/{quiz_id}", json={"title": "Hacked"})
    assert resp.status_code in (403, 404)


async def test_delete_quiz(client: AsyncClient) -> None:
    quiz_id = await _create_quiz(client)
    resp = await client.delete(f"/api/v1/quiz/{quiz_id}")
    assert resp.status_code == 204


async def test_publish_empty_quiz_fails(client: AsyncClient) -> None:
    quiz_id = await _create_quiz(client, with_question=False)
    resp = await client.patch(
        f"/api/v1/quiz/{quiz_id}/status", json={"status": "published"}
    )
    assert resp.status_code == 422


async def test_publish_and_unpublish(client: AsyncClient) -> None:
    quiz_id = await _create_quiz(client, with_question=True)

    pub = await client.patch(
        f"/api/v1/quiz/{quiz_id}/status", json={"status": "published"}
    )
    assert pub.status_code == 200
    assert pub.json()["status"] == "published"

    unpub = await client.patch(
        f"/api/v1/quiz/{quiz_id}/status", json={"status": "draft"}
    )
    assert unpub.status_code == 200
    assert unpub.json()["status"] == "draft"


async def test_cannot_edit_published_quiz(client: AsyncClient) -> None:
    quiz_id = await _create_quiz(client, with_question=True)
    await client.patch(f"/api/v1/quiz/{quiz_id}/status", json={"status": "published"})
    resp = await client.patch(f"/api/v1/quiz/{quiz_id}", json={"title": "New Title"})
    assert resp.status_code == 409


async def test_favorite_add_and_remove(client: AsyncClient) -> None:
    quiz_id = await _create_quiz(client)

    add = await client.post(f"/api/v1/quiz/{quiz_id}/favorite/toggle")
    assert add.status_code == 200
    assert add.json()["isFavorited"] is True

    listed = await client.get("/api/v1/quiz/favorites/list")
    assert [q["quizId"] for q in listed.json()["items"]] == [quiz_id]

    remove = await client.post(f"/api/v1/quiz/{quiz_id}/favorite/toggle")
    assert remove.status_code == 200
    assert remove.json()["isFavorited"] is False


async def test_public_visibility_is_refused_until_discovery_exists(
    client: AsyncClient,
) -> None:
    """Nothing serves a public quiz to anyone but its owner, so the API must not
    accept the value and pretend the quiz was shared."""
    await client.post("/api/v1/auth/register", json=USER)

    body: dict[str, object] = dict(_QUIZ_WITH_QUESTION)
    body["settings"] = {
        "defaultTimePerQuestion": 30000,
        "maxParticipants": 10,
        "visibility": "public",
    }

    refused = await client.post("/api/v1/quiz", json=body)
    assert refused.status_code == 422
    assert refused.json()["errorCode"] == "INVALID_QUIZ_DATA"

    # The default path still works and stays private.
    created = await client.post("/api/v1/quiz", json=_QUIZ_WITH_QUESTION)
    assert created.status_code == 200
    assert created.json()["settings"]["visibility"] == "private"
