import json

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.game.services import game_service
from app.models.game import GamePlayer, GamePlayerAnswer, GameSession, GameSessionStatus
from app.models.quiz import QuizAnswer, QuizQuestion

USER = {"username": "gameuser", "email": "game@example.com", "password": "TestPass123!"}
USER2 = {
    "username": "gameuser2",
    "email": "game2@example.com",
    "password": "TestPass123!",
}

_QUIZ = {
    "title": "Game Quiz",
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


async def _published_quiz_and_room(client: AsyncClient) -> tuple[str, str]:
    await client.post("/api/v1/auth/register", json=USER)
    create = await client.post("/api/v1/quiz", json=_QUIZ)
    quiz_id = create.json()["quizId"]
    await client.patch(f"/api/v1/quiz/{quiz_id}/status", json={"status": "published"})
    room = await client.post("/api/v1/game/room", json={"quizId": quiz_id})
    return quiz_id, room.json()["roomCode"]


async def test_create_room(client: AsyncClient) -> None:
    quiz_id, room_code = await _published_quiz_and_room(client)
    assert len(room_code) == 6


async def test_create_room_foreign_quiz(client: AsyncClient) -> None:
    quiz_id, _ = await _published_quiz_and_room(client)

    client.cookies.clear()
    await client.post("/api/v1/auth/register", json=USER2)
    resp = await client.post("/api/v1/game/room", json={"quizId": quiz_id})
    assert resp.status_code == 403


async def test_create_room_unpublished_quiz(client: AsyncClient) -> None:
    await client.post("/api/v1/auth/register", json=USER)
    create = await client.post("/api/v1/quiz", json=_QUIZ)
    quiz_id = create.json()["quizId"]
    resp = await client.post("/api/v1/game/room", json={"quizId": quiz_id})
    assert resp.status_code == 409


async def test_get_room(client: AsyncClient) -> None:
    _, room_code = await _published_quiz_and_room(client)
    resp = await client.get(f"/api/v1/game/room/{room_code}")
    assert resp.status_code == 200
    assert resp.json()["roomCode"] == room_code


async def test_get_room_not_found(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/game/room/ZZZZZZ")
    assert resp.status_code == 404


async def test_join_room(client: AsyncClient) -> None:
    _, room_code = await _published_quiz_and_room(client)
    resp = await client.post(
        f"/api/v1/game/room/{room_code}/join", json={"nickname": "Alice"}
    )
    assert resp.status_code == 200
    assert resp.json()["nickname"] == "Alice"
    assert "playerId" in resp.json()


async def test_join_room_nickname_taken(client: AsyncClient) -> None:
    _, room_code = await _published_quiz_and_room(client)
    await client.post(f"/api/v1/game/room/{room_code}/join", json={"nickname": "Alice"})
    resp = await client.post(
        f"/api/v1/game/room/{room_code}/join", json={"nickname": "Alice"}
    )
    assert resp.status_code == 409
    assert resp.json()["errorCode"] == "NICKNAME_ALREADY_TAKEN"


async def test_join_started_room(client: AsyncClient, db: AsyncSession) -> None:
    _, room_code = await _published_quiz_and_room(client)

    result = await db.execute(
        select(GameSession).where(GameSession.room_code == room_code)
    )
    session = result.scalars().one()
    session.status = GameSessionStatus.question
    await db.commit()

    resp = await client.post(
        f"/api/v1/game/room/{room_code}/join", json={"nickname": "LatePlayer"}
    )
    assert resp.status_code == 409
    assert resp.json()["errorCode"] == "GAME_ALREADY_STARTED"


async def test_answer_distribution(db: AsyncSession) -> None:
    from app.models.quiz import Quiz
    from app.models.user import User
    from app.quiz.schemas import QuizStatus, QuizVisibility

    user = User(username="host", email="host@test.com", password_hash="x")
    db.add(user)
    await db.flush()

    quiz = Quiz(
        creator_id=user.id,
        title="Q",
        status=QuizStatus.published,
        visibility=QuizVisibility.private,
    )
    db.add(quiz)
    await db.flush()

    question = QuizQuestion(
        quiz_id=quiz.quiz_id, text="Q?", position=1, time_limit=30000
    )
    db.add(question)
    await db.flush()

    ans_a = QuizAnswer(question_id=question.question_id, text="A", is_correct=True)
    ans_b = QuizAnswer(question_id=question.question_id, text="B", is_correct=False)
    db.add_all([ans_a, ans_b])
    await db.flush()

    session = GameSession(
        quiz_id=quiz.quiz_id,
        host_id=user.id,
        status=GameSessionStatus.finished,
    )
    db.add(session)
    await db.flush()

    p1 = GamePlayer(session_id=session.session_id, nickname="P1")
    p2 = GamePlayer(session_id=session.session_id, nickname="P2")
    p3 = GamePlayer(session_id=session.session_id, nickname="P3")
    db.add_all([p1, p2, p3])
    await db.flush()

    # P1 → A, P2 → A, P3 → B
    db.add(
        GamePlayerAnswer(
            player_id=p1.player_id,
            question_id=question.question_id,
            selected_answer_ids=json.dumps([str(ans_a.answer_id)]),
            is_correct=True,
            time_taken_ms=3000,
            points_earned=700,
        )
    )
    db.add(
        GamePlayerAnswer(
            player_id=p2.player_id,
            question_id=question.question_id,
            selected_answer_ids=json.dumps([str(ans_a.answer_id)]),
            is_correct=True,
            time_taken_ms=5000,
            points_earned=500,
        )
    )
    db.add(
        GamePlayerAnswer(
            player_id=p3.player_id,
            question_id=question.question_id,
            selected_answer_ids=json.dumps([str(ans_b.answer_id)]),
            is_correct=False,
            time_taken_ms=8000,
            points_earned=0,
        )
    )
    await db.commit()

    result = await db.execute(
        select(QuizQuestion)
        .options(selectinload(QuizQuestion.answers))
        .where(QuizQuestion.question_id == question.question_id)
    )
    question_loaded = result.scalars().one()

    distribution = await game_service.compute_answer_distribution(
        db, session.session_id, question_loaded
    )

    assert distribution[str(ans_a.answer_id)] == 2
    assert distribution[str(ans_b.answer_id)] == 1


async def test_leaderboard_change_tracking(db: AsyncSession) -> None:
    from app.models.quiz import Quiz
    from app.models.user import User
    from app.quiz.schemas import QuizStatus, QuizVisibility

    user = User(username="host2", email="host2@test.com", password_hash="x")
    db.add(user)
    await db.flush()

    quiz = Quiz(
        creator_id=user.id,
        title="Q",
        status=QuizStatus.published,
        visibility=QuizVisibility.private,
    )
    db.add(quiz)
    await db.flush()

    session = GameSession(
        quiz_id=quiz.quiz_id,
        host_id=user.id,
        room_code="TSTRK",
        status=GameSessionStatus.revealing,
    )
    db.add(session)
    await db.flush()

    p1 = GamePlayer(session_id=session.session_id, nickname="Alice", score=1000)
    p2 = GamePlayer(session_id=session.session_id, nickname="Bob", score=500)
    db.add_all([p1, p2])
    await db.commit()

    # First leaderboard call — no previous ranking, change = 0 for all
    entries = await game_service.get_leaderboard(db, "TSTRK")
    assert entries[0].nickname == "Alice"
    assert entries[0].change == 0
    assert entries[1].nickname == "Bob"
    assert entries[1].change == 0

    # Swap scores — Bob now leads
    p1.score = 500
    p2.score = 1500
    await db.commit()

    entries2 = await game_service.get_leaderboard(db, "TSTRK")
    bob_entry = next(e for e in entries2 if e.nickname == "Bob")
    alice_entry = next(e for e in entries2 if e.nickname == "Alice")

    assert bob_entry.rank == 1
    assert bob_entry.change == 1  # был 2, стал 1 → +1
    assert alice_entry.rank == 2
    assert alice_entry.change == -1  # был 1, стал 2 → -1
