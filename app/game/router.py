import asyncio
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user, get_optional_current_user
from app.core.logging import get_logger
from app.database import get_async_db
from app.models.game import GameSessionStatus
from app.models.user import User

from .connection_manager import connection_manager
from .exceptions import RoomNotFoundError
from .schemas import (
    CreateRoomRequest,
    JoinRoomRequest,
    PlayerInfo,
    RoomResponse,
    WSAnswerSubmit,
    WSGameFinished,
    WSGameStarting,
    WSMessageType,
    WSPlayerJoined,
    WSPlayerLeft,
    WSQuestionEnded,
)
from .services import game_service

logger = get_logger(__name__)

router = APIRouter(tags=["Game"])
ws_router = APIRouter(tags=["WebSocket"])


# =============================================================================
# REST Endpoints
# =============================================================================


@router.post("/room", response_model=RoomResponse)
async def create_room(
    data: CreateRoomRequest,
    db: AsyncSession = Depends(get_async_db),
    user: User = Depends(get_current_user),
) -> RoomResponse:
    """Create a new game room for a quiz."""
    return await game_service.create_room(db, user, data)


@router.get("/room/{room_code}", response_model=RoomResponse)
async def get_room(
    room_code: str,
    db: AsyncSession = Depends(get_async_db),
) -> RoomResponse:
    """Get game room details."""
    session = await game_service.get_room(db, room_code)
    if session is None:
        raise RoomNotFoundError()

    return RoomResponse(
        session_id=str(session.session_id),
        room_code=session.room_code,
        quiz_id=str(session.quiz_id),
        status=session.status,
        player_count=len(session.players),
        created_at=session.created_at,
    )


@router.post("/room/{room_code}/join", response_model=PlayerInfo)
async def join_room(
    room_code: str,
    data: JoinRoomRequest,
    db: AsyncSession = Depends(get_async_db),
    user: User | None = Depends(get_optional_current_user),
) -> PlayerInfo:
    """
    Join a game room (REST endpoint for initial join).

    After this, connect via WebSocket for real-time updates.
    """
    session, player = await game_service.join_room(
        db,
        room_code,
        data.nickname,
        user,
    )

    return PlayerInfo(
        player_id=str(player.player_id),
        nickname=player.nickname,
        score=player.score,
        is_connected=True,
    )


# =============================================================================
# WebSocket Endpoint
# =============================================================================


@ws_router.websocket("/game/{room_code}")
async def websocket_endpoint(
    websocket: WebSocket,
    room_code: str,
    player_id: str = Query(...),
    db: AsyncSession = Depends(get_async_db),
) -> None:
    """
    WebSocket endpoint for real-time game communication.

    Query params:
    - player_id: The player's ID (from join_room response)

    Message format (both directions):
    {
        "type": "message_type",
        "payload": { ... }
    }
    """
    # Verify room exists
    session = await game_service.get_room(db, room_code)
    if session is None:
        await websocket.close(code=4004, reason="Room not found")
        return

    # Verify player belongs to room
    player = next(
        (p for p in session.players if str(p.player_id) == player_id),
        None,
    )
    if player is None:
        await websocket.close(code=4004, reason="Player not found")
        return

    # Connect
    await connection_manager.connect(websocket, room_code, player_id)

    # Update player connection status
    player.is_connected = True
    await db.commit()

    # Send current room state
    room_state = await game_service.build_room_state(db, room_code)
    if room_state:
        await connection_manager.send_to_player(
            player_id,
            {
                "type": WSMessageType.ROOM_STATE.value,
                "payload": room_state.model_dump(by_alias=True),
            },
        )

    # Notify others that player joined
    await connection_manager.broadcast_to_room(
        room_code,
        {
            "type": WSMessageType.PLAYER_JOINED.value,
            "payload": WSPlayerJoined(
                player=PlayerInfo(
                    player_id=str(player.player_id),
                    nickname=player.nickname,
                    score=player.score,
                    is_connected=True,
                )
            ).model_dump(by_alias=True),
        },
        exclude_player_id=player_id,
    )

    try:
        while True:
            # Receive message from client
            data = await websocket.receive_json()
            await handle_websocket_message(
                db,
                room_code,
                player_id,
                data,
                session.host_id == player.user_id if player.user_id else False,
            )

    except WebSocketDisconnect:
        logger.info("websocket_disconnect", player_id=player_id, room_code=room_code)
    except Exception as e:
        logger.error("websocket_error", error=str(e), player_id=player_id)
    finally:
        # Clean up
        await connection_manager.disconnect(websocket, room_code, player_id)

        # Update player connection status
        try:
            player.is_connected = False
            await db.commit()
        except Exception:
            pass

        # Notify others that player left
        await connection_manager.broadcast_to_room(
            room_code,
            {
                "type": WSMessageType.PLAYER_LEFT.value,
                "payload": WSPlayerLeft(
                    player_id=player_id,
                    nickname=player.nickname,
                ).model_dump(by_alias=True),
            },
        )


async def handle_websocket_message(
    db: AsyncSession,
    room_code: str,
    player_id: str,
    data: dict[str, object],
    is_host: bool,
) -> None:
    """Handle incoming WebSocket messages."""
    try:
        message_type = data.get("type")
        raw_payload = data.get("payload", {})
        payload: dict[str, object] = (
            raw_payload if isinstance(raw_payload, dict) else {}
        )

        if message_type == WSMessageType.START_GAME.value:
            await handle_start_game(db, room_code, player_id, is_host)

        elif message_type == WSMessageType.NEXT_QUESTION.value:
            await handle_next_question(db, room_code, player_id, is_host)

        elif message_type == WSMessageType.ANSWER.value:
            await handle_answer(db, room_code, player_id, payload)

        else:
            logger.warning("unknown_message_type", type=message_type)

    except Exception as e:
        logger.error("message_handler_error", error=str(e))
        await connection_manager.send_to_player(
            player_id,
            {
                "type": WSMessageType.ERROR.value,
                "payload": {
                    "code": "HANDLER_ERROR",
                    "message": "An unexpected error occurred",
                },
            },
        )


async def handle_start_game(
    db: AsyncSession,
    room_code: str,
    player_id: str,
    is_host: bool,
) -> None:
    """Handle game start request from host."""
    if not is_host:
        await connection_manager.send_to_player(
            player_id,
            {
                "type": WSMessageType.ERROR.value,
                "payload": {
                    "code": "NOT_HOST",
                    "message": "Only the host can start the game",
                },
            },
        )
        return

    session = await game_service.get_room(db, room_code)
    if session is None:
        return

    user_result = await db.execute(select(User).where(User.id == session.host_id))
    host_user = user_result.scalars().first()
    if host_user is None:
        return

    questions = await game_service.start_game(db, room_code, host_user)

    # Broadcast game starting message
    await connection_manager.broadcast_to_room(
        room_code,
        {
            "type": WSMessageType.GAME_STARTING.value,
            "payload": WSGameStarting(
                countdown_seconds=3,
                total_questions=len(questions),
            ).model_dump(by_alias=True),
        },
    )

    # Wait for countdown
    await asyncio.sleep(3)

    # Start first question
    await send_question(db, room_code, 1, len(questions))


async def handle_next_question(
    db: AsyncSession,
    room_code: str,
    player_id: str,
    is_host: bool,
) -> None:
    """Handle next question request from host."""
    if not is_host:
        await connection_manager.send_to_player(
            player_id,
            {
                "type": WSMessageType.ERROR.value,
                "payload": {
                    "code": "NOT_HOST",
                    "message": "Only the host can advance questions",
                },
            },
        )
        return

    session = await game_service.get_room(db, room_code)
    if session is None:
        return

    question_count = len(session.quiz.questions)
    next_index = session.current_question_index + 1

    if next_index > question_count:
        # Game finished
        await end_game(db, room_code)
    else:
        # Send leaderboard first
        leaderboard = await game_service.get_leaderboard(db, room_code)
        await connection_manager.broadcast_to_room(
            room_code,
            {
                "type": WSMessageType.LEADERBOARD.value,
                "payload": {
                    "entries": [e.model_dump(by_alias=True) for e in leaderboard],
                    "questionIndex": session.current_question_index,
                },
            },
        )

        # Wait a bit for leaderboard display
        await asyncio.sleep(5)

        # Send next question
        await send_question(db, room_code, next_index, question_count)


async def handle_answer(
    db: AsyncSession,
    room_code: str,
    player_id: str,
    payload: dict[str, object],
) -> None:
    """Handle answer submission from player."""
    try:
        answer_data = WSAnswerSubmit.model_validate(payload)
        result = await game_service.submit_answer(
            db,
            room_code,
            player_id,
            answer_data.question_id,
            answer_data.answer_ids,
        )

        # Get session for feedback setting
        session = await game_service.get_room(db, room_code)

        # Send result to player (if immediate feedback enabled)
        if session and session.show_immediate_feedback:
            await connection_manager.send_to_player(
                player_id,
                {
                    "type": WSMessageType.ANSWER_RESULT.value,
                    "payload": result.model_dump(by_alias=True),
                },
            )

    except Exception as e:
        logger.error("answer_handler_error", error=str(e))
        await connection_manager.send_to_player(
            player_id,
            {
                "type": WSMessageType.ERROR.value,
                "payload": {
                    "code": "ANSWER_ERROR",
                    "message": "Failed to process answer",
                },
            },
        )


async def send_question(
    db: AsyncSession,
    room_code: str,
    question_index: int,
    total_questions: int,
) -> None:
    """Send a question to all players."""
    question = await game_service.advance_to_question(db, room_code, question_index)

    if question is None:
        await end_game(db, room_code)
        return

    # Get session for randomize_answers setting
    session = await game_service.get_room(db, room_code)

    question_msg = await game_service.build_question_message(
        question,
        question_index,
        total_questions,
        randomize_answers=session.randomize_answers if session else False,
    )

    await connection_manager.broadcast_to_room(
        room_code,
        {
            "type": WSMessageType.QUESTION.value,
            "payload": question_msg.model_dump(by_alias=True),
        },
    )

    # Schedule question timeout
    asyncio.create_task(
        question_timeout(db, room_code, question_index, question.time_limit)
    )


async def question_timeout(
    db: AsyncSession,
    room_code: str,
    question_index: int,
    time_limit_ms: int,
) -> None:
    """Handle question timeout."""
    await asyncio.sleep(time_limit_ms / 1000)

    # Check if still on this question
    session = await game_service.get_room(db, room_code)
    if session is None or session.current_question_index != question_index:
        return

    if session.status != GameSessionStatus.question:
        return

    session.status = GameSessionStatus.revealing
    await db.commit()

    question = await game_service.get_current_question(db, room_code)
    if question:
        correct_ids = [str(a.answer_id) for a in question.answers if a.is_correct]
        distribution = await game_service.compute_answer_distribution(
            db, session.session_id, question
        )

        await connection_manager.broadcast_to_room(
            room_code,
            {
                "type": WSMessageType.QUESTION_ENDED.value,
                "payload": WSQuestionEnded(
                    question_id=str(question.question_id),
                    correct_answer_ids=correct_ids,
                    answer_distribution=distribution,
                ).model_dump(by_alias=True),
            },
        )


async def end_game(db: AsyncSession, room_code: str) -> None:
    """End the game and send final results."""
    session = await game_service.get_room(db, room_code)
    if session is None:
        return

    session.status = GameSessionStatus.finished
    await db.commit()

    leaderboard = await game_service.get_leaderboard(db, room_code)

    duration = 0
    if session.started_at and session.ended_at:
        duration = int((session.ended_at - session.started_at).total_seconds())
    elif session.started_at:
        duration = int(
            (
                datetime.now(timezone.utc).replace(tzinfo=None) - session.started_at
            ).total_seconds()
        )

    question_count = len(session.quiz.questions)

    await connection_manager.broadcast_to_room(
        room_code,
        {
            "type": WSMessageType.GAME_FINISHED.value,
            "payload": WSGameFinished(
                final_leaderboard=leaderboard,
                total_questions=question_count,
                duration_seconds=duration,
            ).model_dump(by_alias=True),
        },
    )

    await game_service.clear_ranking_state(room_code)

    logger.info(
        "game_finished",
        room_code=room_code,
        duration_seconds=duration,
        player_count=len(leaderboard),
    )
