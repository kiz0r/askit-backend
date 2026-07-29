"""Regression tests for access-control boundaries between users and roles.

Each test here corresponds to a defect that was reachable at some point: reading
another user's quiz through the favorites list, and receiving host-only game
state as a player.
"""

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.game.services import game_service
from app.user.services.user_service import user_service

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


async def test_room_state_withholds_the_answer_feed_from_players(
    client: AsyncClient, db: AsyncSession
) -> None:
    """A reconnecting player must not receive the host's per-player answer feed.

    The feed carries each player's selected answer ids together with is_correct,
    so while a question is still running it reveals the correct answer to anyone
    who reads the frame.
    """
    await client.post("/api/v1/auth/register", json=VICTIM)
    quiz_id = (await client.post("/api/v1/quiz", json=QUIZ)).json()["quizId"]
    await client.patch(f"/api/v1/quiz/{quiz_id}/status", json={"status": "published"})
    room_code = (
        await client.post("/api/v1/game/room", json={"quizId": quiz_id})
    ).json()["roomCode"]

    host_user = await user_service.get_user_by_email(db, VICTIM["email"])
    assert host_user is not None

    # Join as a guest: the host may not occupy a player slot in their own game.
    client.cookies.clear()
    joined = await client.post(
        f"/api/v1/game/room/{room_code}/join", json={"nickname": "p1"}
    )
    assert joined.status_code == 200

    await game_service.start_game(db, room_code, host_user.id)
    await game_service.advance_to_question(db, room_code, 1)

    question = await game_service.get_current_question(db, room_code)
    assert question is not None
    correct_id = next(str(a.answer_id) for a in question.answers if a.is_correct)
    session = await game_service.get_room(db, room_code)
    assert session is not None
    player = session.players[0]
    await game_service.submit_answer(
        db, room_code, str(player.player_id), str(question.question_id), [correct_id]
    )

    for_player = await game_service.build_room_state(db, room_code)
    assert for_player is not None
    assert for_player.host_answer_details == [], "player must not see the answer feed"

    for_host = await game_service.build_room_state(db, room_code, for_host=True)
    assert for_host is not None
    assert len(for_host.host_answer_details) == 1, "host still gets the feed"
    assert for_host.host_answer_details[0].is_correct is True


REFRESH_USER = {
    "username": "rotator",
    "email": "rotator@example.com",
    "password": "TestPass123!",
}


async def test_refresh_rotates_and_burns_the_presented_token(
    client: AsyncClient,
) -> None:
    """A refresh token is single use: replaying it must be refused."""
    await client.post("/api/v1/auth/register", json=REFRESH_USER)
    spent_token = client.cookies["refresh_token"]

    first = await client.post("/api/v1/auth/refresh")
    assert first.status_code == 200
    assert client.cookies["refresh_token"] != spent_token, "token must rotate"

    # Replaying the spent token is rejected even though it has not expired.
    client.cookies.set("refresh_token", spent_token)
    replayed = await client.post("/api/v1/auth/refresh")
    assert replayed.status_code == 401
    assert replayed.json()["errorCode"] == "TOKEN_REVOKED"


async def test_password_change_invalidates_tokens_of_other_sessions(
    client: AsyncClient,
) -> None:
    """Changing the password must drop sessions opened under the old one."""
    await client.post("/api/v1/auth/register", json=REFRESH_USER)
    stale_access = client.cookies["access_token"]
    stale_refresh = client.cookies["refresh_token"]

    changed = await client.post(
        "/api/v1/user/password",
        json={
            "currentPassword": REFRESH_USER["password"],
            "nextPassword": "BrandNewPass456!",
        },
    )
    assert changed.status_code == 200

    # The session that made the change keeps working on its re-issued cookies.
    assert (await client.get("/api/v1/user/profile")).status_code == 200
    assert client.cookies["access_token"] != stale_access

    # Another session holding the old cookies does not.
    client.cookies.set("access_token", stale_access)
    stale = await client.get("/api/v1/user/profile")
    assert stale.status_code == 401
    assert stale.json()["errorCode"] == "TOKEN_REVOKED"

    client.cookies.set("refresh_token", stale_refresh)
    assert (await client.post("/api/v1/auth/refresh")).status_code == 401


async def test_deactivation_invalidates_the_refresh_token(
    client: AsyncClient,
) -> None:
    """A deactivated account cannot mint new access tokens."""
    await client.post("/api/v1/auth/register", json=REFRESH_USER)
    refresh_token = client.cookies["refresh_token"]

    assert (await client.post("/api/v1/user/deactivate")).status_code == 200

    client.cookies.set("refresh_token", refresh_token)
    refused = await client.post("/api/v1/auth/refresh")
    assert refused.status_code == 401
    assert refused.json()["errorCode"] == "TOKEN_REVOKED"
