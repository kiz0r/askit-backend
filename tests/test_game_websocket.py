"""End-to-end coverage of the WebSocket game loop, host and player together.

The handlers open a short session per message instead of holding one for the
lifetime of the connection, so a whole game has to be driven through real
sockets to prove that nothing depends on state carried across those sessions.

Starlette's TestClient cannot serve this: it creates a fresh event loop per
``websocket_connect``, while the ConnectionManager is a single process-wide
object, so two concurrent clients end up in different loops and sends between
them hang. A real uvicorn server is started instead, so both sockets live in one
loop exactly as they do in production.
"""

import asyncio
import contextlib
import socket
from collections.abc import AsyncGenerator
from typing import Any

import pytest
import uvicorn
import websockets
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import app

HOST = {"username": "wshost", "email": "wshost@example.com", "password": "TestPass123!"}

QUIZ = {
    "title": "WS Quiz",
    "settings": {"defaultTimePerQuestion": 30000, "maxParticipants": 10},
    "questions": [
        {
            "text": "2 + 2?",
            "timeLimit": 300000,
            "answers": [
                {"text": "3", "isCorrect": False},
                {"text": "4", "isCorrect": True},
            ],
        }
    ],
}


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port: int = s.getsockname()[1]
        return port


@pytest.fixture
async def live_server(db: AsyncSession) -> AsyncGenerator[int, None]:
    """Serve the app on a real port, in this test's event loop.

    ``db`` is requested so the dependency override and the patched session
    factory are installed before the server starts. Lifespan is off: the whole
    suite shares one event loop, so the pools the fixtures already built are the
    right ones, and running the app's shutdown hook here would close the Redis
    pool out from under every later test.
    """
    port = _free_port()
    config = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=port,
        log_level="warning",
        access_log=False,
        lifespan="off",
    )
    server = uvicorn.Server(config)
    task = asyncio.create_task(server.serve())

    for _ in range(200):
        if server.started:
            break
        await asyncio.sleep(0.05)
    else:  # pragma: no cover - only on a broken environment
        raise RuntimeError("uvicorn did not start")

    try:
        yield port
    finally:
        server.should_exit = True
        with contextlib.suppress(asyncio.TimeoutError):
            await asyncio.wait_for(task, timeout=10)


async def _next(ws: Any, wanted: str, limit: int = 25) -> dict[str, Any]:
    """Read frames until one of type ``wanted`` arrives."""
    import json

    for _ in range(limit):
        frame = json.loads(await asyncio.wait_for(ws.recv(), timeout=15))
        if frame["type"] == wanted:
            return dict(frame)
    raise AssertionError(f"no {wanted!r} frame within {limit} frames")


async def test_full_game_over_websockets(client: AsyncClient, live_server: int) -> None:
    base = f"http://127.0.0.1:{live_server}"
    ws_base = f"ws://127.0.0.1:{live_server}"

    async with AsyncClient(base_url=base) as http:
        await http.post("/api/v1/auth/register", json=HOST)
        quiz_id = (await http.post("/api/v1/quiz", json=QUIZ)).json()["quizId"]
        await http.patch(f"/api/v1/quiz/{quiz_id}/status", json={"status": "published"})
        room_code = (
            await http.post("/api/v1/game/room", json={"quizId": quiz_id})
        ).json()["roomCode"]
        host_cookie = f"access_token={http.cookies['access_token']}"

    async with AsyncClient(base_url=base) as http:
        join = await http.post(
            f"/api/v1/game/room/{room_code}/join", json={"nickname": "p1"}
        )
        assert join.status_code == 200
        player_id = join.json()["playerId"]
        player_cookie = f"ws_token={http.cookies['ws_token']}"

    async with websockets.connect(
        f"{ws_base}/ws/game/{room_code}/host",
        additional_headers={"Cookie": host_cookie},
    ) as host_ws:
        assert (await _next(host_ws, "room_state"))["payload"]["roomCode"] == room_code

        async with websockets.connect(
            f"{ws_base}/ws/game/{room_code}",
            additional_headers={"Cookie": player_cookie},
        ) as player_ws:
            state = await _next(player_ws, "room_state")
            assert state["payload"]["status"] == "waiting"
            # The host-only answer feed must never be on a player's wire.
            assert state["payload"]["hostAnswerDetails"] == []

            # start_game spans two sessions either side of a three-second
            # countdown, which is the case the refactor most needed to survive.
            await host_ws.send('{"type": "start_game"}')
            question = await _next(player_ws, "question")
            question_id = question["payload"]["questionId"]
            answers = question["payload"]["answers"]
            assert all("isCorrect" not in a for a in answers), (
                "correctness must never be sent with the question"
            )

            correct_id = next(a["answerId"] for a in answers if a["text"] == "4")
            await player_ws.send(
                '{"type": "answer", "payload": {"questionId": "%s", '
                '"answerIds": ["%s"]}}' % (question_id, correct_id)
            )

            result = await _next(player_ws, "answer_result")
            assert result["payload"]["isCorrect"] is True
            assert result["payload"]["pointsEarned"] > 0

            update = await _next(host_ws, "host_answer_update")
            assert update["payload"]["playerId"] == player_id
            assert update["payload"]["isCorrect"] is True

            # Force-end the question, then advance past the last one.
            await host_ws.send('{"type": "next_question"}')
            ended = await _next(player_ws, "question_ended")
            assert ended["payload"]["correctAnswerIds"] == [correct_id]

            await host_ws.send('{"type": "next_question"}')
            finished = await _next(player_ws, "game_finished")
            leaderboard = finished["payload"]["finalLeaderboard"]
            assert [e["playerId"] for e in leaderboard] == [player_id]
            assert leaderboard[0]["score"] > 0


async def test_player_socket_rejects_a_foreign_origin(
    client: AsyncClient, live_server: int
) -> None:
    """The player socket must refuse a handshake from an origin we do not serve.

    A WebSocket handshake is not covered by CORS, so this check, and not the
    CORS configuration, is what stops another site from opening a socket with
    the visitor's cookies attached.
    """
    base = f"http://127.0.0.1:{live_server}"
    ws_base = f"ws://127.0.0.1:{live_server}"

    async with AsyncClient(base_url=base) as http:
        await http.post(
            "/api/v1/auth/register",
            json={**HOST, "email": "origin@e.cz", "username": "originhost"},
        )
        quiz_id = (await http.post("/api/v1/quiz", json=QUIZ)).json()["quizId"]
        await http.patch(f"/api/v1/quiz/{quiz_id}/status", json={"status": "published"})
        room_code = (
            await http.post("/api/v1/game/room", json={"quizId": quiz_id})
        ).json()["roomCode"]

    async with AsyncClient(base_url=base) as http:
        await http.post(f"/api/v1/game/room/{room_code}/join", json={"nickname": "p1"})
        cookie = f"ws_token={http.cookies['ws_token']}"

    with pytest.raises(websockets.exceptions.InvalidStatus):
        async with websockets.connect(
            f"{ws_base}/ws/game/{room_code}",
            additional_headers={"Cookie": cookie, "Origin": "https://evil.example"},
        ):
            pass

    # The same handshake without the foreign origin still succeeds.
    async with websockets.connect(
        f"{ws_base}/ws/game/{room_code}",
        additional_headers={"Cookie": cookie},
    ) as ws:
        assert (await _next(ws, "room_state"))["payload"]["roomCode"] == room_code
