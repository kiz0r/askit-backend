"""Reproductions for the findings raised in the supervisor's code review.

These tests assert the CURRENT (vulnerable) behaviour, so they pass today and
document exactly what an attacker can do. Once the findings are fixed they must
be inverted into regression tests.
"""

from httpx import AsyncClient

VICTIM = {
    "username": "victim",
    "email": "victim@example.com",
    "password": "TestPass123!",
}
ATTACKER = {
    "username": "attacker",
    "email": "attacker@example.com",
    "password": "TestPass123!",
}

QUIZ = {
    "title": "Private Exam",
    "settings": {"defaultTimePerQuestion": 30000, "maxParticipants": 10},
    "questions": [
        {
            "text": "Capital of France?",
            "timeLimit": 30000,
            "answers": [
                {"text": "Berlin", "isCorrect": False},
                {"text": "Paris", "isCorrect": True},
            ],
        }
    ],
}


async def test_foreign_quiz_cannot_be_read_through_favorites(
    client: AsyncClient,
) -> None:
    """A quiz id leaked by the public room endpoint must not unlock the quiz.

    The room endpoint is unauthenticated by design, so any participant learns the
    quiz id of the game they are in. Favoriting must not turn that id into a read
    path, because list_favorites returns the full quiz including which answers
    are correct.
    """
    # Victim creates a private quiz, publishes it and opens a room.
    await client.post("/api/v1/auth/register", json=VICTIM)
    quiz_id = (await client.post("/api/v1/quiz", json=QUIZ)).json()["quizId"]
    await client.patch(f"/api/v1/quiz/{quiz_id}/status", json={"status": "published"})
    room_code = (
        await client.post("/api/v1/game/room", json={"quizId": quiz_id})
    ).json()["roomCode"]
    client.cookies.clear()

    # The room endpoint needs no authentication and does leak the quiz id.
    room = await client.get(f"/api/v1/game/room/{room_code}")
    assert room.status_code == 200
    leaked_quiz_id = room.json()["quizId"]
    assert leaked_quiz_id == quiz_id

    # Another account can neither read the quiz nor favorite it.
    await client.post("/api/v1/auth/register", json=ATTACKER)
    assert (await client.get(f"/api/v1/quiz/{leaked_quiz_id}")).status_code == 404

    toggled = await client.post(f"/api/v1/quiz/{leaked_quiz_id}/favorite/toggle")
    assert toggled.status_code == 404, "favoriting a foreign quiz must be refused"

    # And the favorites list stays empty, so no correct answers are exposed.
    favorites = (await client.get("/api/v1/quiz/favorites/list")).json()
    assert favorites["items"] == []


async def test_owner_can_still_favorite_own_quiz(client: AsyncClient) -> None:
    """The ownership check must not break the legitimate path."""
    await client.post("/api/v1/auth/register", json=VICTIM)
    quiz_id = (await client.post("/api/v1/quiz", json=QUIZ)).json()["quizId"]

    toggled = await client.post(f"/api/v1/quiz/{quiz_id}/favorite/toggle")
    assert toggled.status_code == 200
    assert toggled.json()["isFavorited"] is True

    favorites = (await client.get("/api/v1/quiz/favorites/list")).json()
    assert [q["quizId"] for q in favorites["items"]] == [quiz_id]

    untoggled = await client.post(f"/api/v1/quiz/{quiz_id}/favorite/toggle")
    assert untoggled.json()["isFavorited"] is False


async def test_m3_player_room_state_carries_host_only_fields(
    client: AsyncClient,
) -> None:
    """M3: the room_state payload built for a player includes host-only data."""
    from app.game.services import game_service
    from app.game.schemas import WSRoomState

    # The single builder is used for both endpoints and takes no audience flag,
    # so whatever it produces for the host is what the player receives verbatim
    # (game/router.py sends room_state.model_dump() with no filtering).
    assert "for_host" not in game_service.build_room_state.__code__.co_varnames
    assert "host_answer_details" in WSRoomState.model_fields
    assert "question_ended" in WSRoomState.model_fields
