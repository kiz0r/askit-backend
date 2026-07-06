import asyncio
from datetime import datetime, timezone

from fastapi import (
    APIRouter,
    Depends,
    Request,
    Response,
    WebSocket,
    WebSocketDisconnect,
)
from pydantic import TypeAdapter
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user, get_optional_current_user
from app.auth.services.jwt_service import jwt_service
from app.core.limiter import limiter
from app.core.logging import get_logger
from app.core.security import create_ws_token, verify_ws_token
from app.database import get_async_db
from app.models.game import GameSessionStatus
from app.models.user import User
from app.settings import ENV_SETTINGS, is_dev
from app.user.services.user_service import user_service
from app.user.types import UserId

from .connection_manager import connection_manager
from .exceptions import AlreadyAnsweredError, QuestionNotActiveError, RoomNotFoundError
from .schemas import (
    AnswerClientMessage,
    ClientMessage,
    CreateRoomRequest,
    JoinRoomRequest,
    NextQuestionMessage,
    PlayerInfo,
    RoomResponse,
    StartGameMessage,
    WSGameFinished,
    WSGameStarting,
    WSHostAnswerUpdate,
    WSMessageType,
    WSPlayerAnswered,
    WSPlayerJoined,
    WSPlayerLeft,
    WSQuestionEnded,
)
from .services import game_service

logger = get_logger(__name__)

client_message_adapter: TypeAdapter[ClientMessage] = TypeAdapter(ClientMessage)

router = APIRouter(tags=["Game"])
ws_router = APIRouter(tags=["WebSocket"])


@router.post("/room", response_model=RoomResponse)
@limiter.limit("10/minute")
async def create_room(
    request: Request,
    data: CreateRoomRequest,
    db: AsyncSession = Depends(get_async_db),
    user: User = Depends(get_current_user),
) -> RoomResponse:
    return await game_service.create_room(db, user, data)


@router.get("/room/{room_code}", response_model=RoomResponse)
async def get_room(
    room_code: str,
    db: AsyncSession = Depends(get_async_db),
) -> RoomResponse:
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
@limiter.limit("20/minute")
async def join_room(
    request: Request,
    response: Response,
    room_code: str,
    data: JoinRoomRequest,
    db: AsyncSession = Depends(get_async_db),
    user: User | None = Depends(get_optional_current_user),
) -> PlayerInfo:
    session, player = await game_service.join_room(db, room_code, data.nickname, user)
    ws_token = await create_ws_token(str(player.player_id))
    response.set_cookie(
        key="ws_token",
        value=ws_token,
        httponly=True,
        samesite="lax",
        secure=not is_dev(),
        max_age=4 * 3600,
    )
    return PlayerInfo(
        player_id=str(player.player_id),
        nickname=player.nickname,
        score=player.score,
        is_connected=True,
    )


@ws_router.websocket("/game/{room_code}")
async def websocket_player_endpoint(
    websocket: WebSocket,
    room_code: str,
    db: AsyncSession = Depends(get_async_db),
) -> None:
    ws_token = websocket.cookies.get("ws_token")
    if not ws_token:
        await websocket.close(code=4001, reason="Not authenticated")
        return

    player_id = await verify_ws_token(ws_token)
    if player_id is None:
        await websocket.close(code=4001, reason="Invalid or expired token")
        return

    session = await game_service.get_room(db, room_code)
    if session is None:
        await websocket.close(code=4004, reason="Room not found")
        return

    player = next(
        (p for p in session.players if str(p.player_id) == player_id),
        None,
    )
    if player is None:
        await websocket.close(code=4004, reason="Player not found")
        return

    await connection_manager.connect(websocket, room_code, player_id)

    player.is_connected = True
    await db.commit()

    room_state = await game_service.build_room_state(db, room_code)
    if room_state:
        await connection_manager.send_to_player(
            player_id,
            {
                "type": WSMessageType.ROOM_STATE.value,
                "payload": room_state.model_dump(by_alias=True),
            },
        )

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
            data = await websocket.receive_json()
            await handle_player_message(db, room_code, player_id, data)

    except WebSocketDisconnect:
        logger.info("player_disconnect", player_id=player_id, room_code=room_code)
    except Exception as e:
        logger.error("player_ws_error", error=str(e), player_id=player_id)
    finally:
        await connection_manager.disconnect(websocket, room_code, player_id)

        try:
            player.is_connected = False
            await db.commit()
        except Exception:
            pass

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


@ws_router.websocket("/game/{room_code}/host")
async def websocket_host_endpoint(
    websocket: WebSocket,
    room_code: str,
    db: AsyncSession = Depends(get_async_db),
) -> None:
    origin = websocket.headers.get("origin")
    if origin and origin not in ENV_SETTINGS.cors_origins_list:
        await websocket.close(code=4003, reason="Origin not allowed")
        return

    token = websocket.cookies.get("access_token")
    if not token:
        await websocket.close(code=4001, reason="Not authenticated")
        return

    try:
        payload = jwt_service.verify_access_token(token)
        sub = payload.get("sub")
        if not sub:
            await websocket.close(code=4001, reason="Invalid token")
            return
        host_user = await user_service.get_user_by_id(db, UserId(sub))
    except Exception:
        await websocket.close(code=4001, reason="Invalid token")
        return

    if not host_user or not host_user.is_active:
        await websocket.close(code=4001, reason="User not found")
        return

    session = await game_service.get_room(db, room_code)
    if session is None:
        await websocket.close(code=4004, reason="Room not found")
        return

    if session.host_id != host_user.id:
        await websocket.close(code=4003, reason="Not the host of this room")
        return

    await connection_manager.connect_host(websocket, room_code)

    room_state = await game_service.build_room_state(db, room_code)
    if room_state:
        await connection_manager.send_to_host(
            room_code,
            {
                "type": WSMessageType.ROOM_STATE.value,
                "payload": room_state.model_dump(by_alias=True),
            },
        )

    try:
        while True:
            data = await websocket.receive_json()
            await handle_host_message(db, room_code, host_user, data)

    except WebSocketDisconnect:
        logger.info("host_disconnect", room_code=room_code)
    except Exception as e:
        logger.error("host_ws_error", error=str(e), room_code=room_code)
    finally:
        await connection_manager.disconnect_host(websocket, room_code)


async def handle_player_message(
    db: AsyncSession,
    room_code: str,
    player_id: str,
    data: dict[str, object],
) -> None:
    try:
        message = client_message_adapter.validate_python(data)

        if isinstance(message, AnswerClientMessage):
            await handle_answer(db, room_code, player_id, message)
        else:
            logger.warning("unknown_player_message_type", type=data.get("type"))

    except Exception as e:
        logger.error("player_message_handler_error", error=str(e))
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


async def handle_host_message(
    db: AsyncSession,
    room_code: str,
    host_user: User,
    data: dict[str, object],
) -> None:
    try:
        message = client_message_adapter.validate_python(data)

        if isinstance(message, StartGameMessage):
            await handle_start_game(db, room_code, host_user)
        elif isinstance(message, NextQuestionMessage):
            await handle_next_question(db, room_code)
        else:
            logger.warning("unknown_host_message_type", type=data.get("type"))

    except Exception as e:
        logger.error("host_message_handler_error", error=str(e))
        await connection_manager.send_to_host(
            room_code,
            {
                "type": WSMessageType.ERROR.value,
                "payload": {
                    "code": "HANDLER_ERROR",
                    "message": "An unexpected error occurred",
                },
            },
        )


async def handle_start_game(db: AsyncSession, room_code: str, host_user: User) -> None:
    questions = await game_service.start_game(db, room_code, host_user)

    total_questions = len(questions)
    for ms in (3000, 2000, 1000):
        await connection_manager.broadcast_to_room(
            room_code,
            {
                "type": WSMessageType.GAME_STARTING.value,
                "payload": WSGameStarting(
                    countdown_ms=ms,
                    total_questions=total_questions,
                ).model_dump(by_alias=True),
            },
        )
        await asyncio.sleep(1)

    await send_question(db, room_code, 1, total_questions)


async def handle_next_question(db: AsyncSession, room_code: str) -> None:
    session = await game_service.get_room(db, room_code)
    if session is None:
        return

    if session.status == GameSessionStatus.question:
        question = await game_service.get_current_question(db, room_code)
        if question is None:
            return
        session.status = GameSessionStatus.revealing
        await db.commit()
        correct_ids = [str(a.answer_id) for a in question.answers if a.is_correct]
        distribution = await game_service.compute_answer_distribution(
            db, session.session_id, question
        )
        leaderboard = await game_service.get_leaderboard(db, room_code)
        await connection_manager.broadcast_to_room(
            room_code,
            {
                "type": WSMessageType.QUESTION_ENDED.value,
                "payload": WSQuestionEnded(
                    question_id=str(question.question_id),
                    correct_answer_ids=correct_ids,
                    answer_distribution=distribution,
                    leaderboard=leaderboard,
                ).model_dump(by_alias=True),
            },
        )
        return

    if session.status != GameSessionStatus.revealing:
        return
    question_count = len(session.quiz.questions)
    next_index = session.current_question_index + 1
    if next_index > question_count:
        await end_game(db, room_code)
        return
    await send_question(db, room_code, next_index, question_count)


async def handle_answer(
    db: AsyncSession,
    room_code: str,
    player_id: str,
    message: AnswerClientMessage,
) -> None:
    try:
        result = await game_service.submit_answer(
            db,
            room_code,
            player_id,
            message.payload.question_id,
            message.payload.answer_ids,
        )

        session = await game_service.get_room(db, room_code)

        await connection_manager.broadcast_to_room(
            room_code,
            {
                "type": WSMessageType.PLAYER_ANSWERED.value,
                "payload": WSPlayerAnswered(player_id=player_id).model_dump(
                    by_alias=True
                ),
            },
        )

        if session and session.show_immediate_feedback:
            await connection_manager.send_to_player(
                player_id,
                {
                    "type": WSMessageType.ANSWER_RESULT.value,
                    "payload": result.model_dump(by_alias=True),
                },
            )

        if session:
            player = next(
                (p for p in session.players if str(p.player_id) == player_id), None
            )
            if player:
                await connection_manager.send_to_host(
                    room_code,
                    {
                        "type": WSMessageType.HOST_ANSWER_UPDATE.value,
                        "payload": WSHostAnswerUpdate(
                            player_id=player_id,
                            nickname=player.nickname,
                            is_correct=result.is_correct,
                            answer_ids=message.payload.answer_ids,
                            time_taken_ms=result.time_taken_ms,
                            total_score=player.score,
                        ).model_dump(by_alias=True),
                    },
                )

    except (AlreadyAnsweredError, QuestionNotActiveError) as e:
        logger.warning("answer_ignored", reason=type(e).__name__, player_id=player_id)
        await connection_manager.send_to_player(
            player_id,
            {
                "type": WSMessageType.ERROR.value,
                "payload": {
                    "code": e.error_code,
                    "message": e.message,
                },
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
    question = await game_service.advance_to_question(db, room_code, question_index)

    if question is None:
        await end_game(db, room_code)
        return

    session = await game_service.get_room(db, room_code)

    question_msg = await game_service.build_question_message(
        question,
        question_index,
        total_questions,
        room_code=room_code,
        randomize_answers=session.randomize_answers if session else False,
    )

    await connection_manager.broadcast_to_room(
        room_code,
        {
            "type": WSMessageType.QUESTION.value,
            "payload": question_msg.model_dump(by_alias=True),
        },
    )

    asyncio.create_task(
        question_timeout(db, room_code, question_index, question.time_limit)
    )


async def question_timeout(
    db: AsyncSession,
    room_code: str,
    question_index: int,
    time_limit_ms: int,
) -> None:
    await asyncio.sleep(time_limit_ms / 1000)

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

        leaderboard = await game_service.get_leaderboard(db, room_code)
        await connection_manager.broadcast_to_room(
            room_code,
            {
                "type": WSMessageType.QUESTION_ENDED.value,
                "payload": WSQuestionEnded(
                    question_id=str(question.question_id),
                    correct_answer_ids=correct_ids,
                    answer_distribution=distribution,
                    leaderboard=leaderboard,
                ).model_dump(by_alias=True),
            },
        )


async def end_game(db: AsyncSession, room_code: str) -> None:
    session = await game_service.get_room(db, room_code)
    if session is None:
        return

    session.status = GameSessionStatus.finished
    await db.commit()

    leaderboard = await game_service.get_leaderboard(db, room_code)

    duration_ms = 0
    if session.started_at and session.ended_at:
        duration_ms = int(
            (session.ended_at - session.started_at).total_seconds() * 1000
        )
    elif session.started_at:
        duration_ms = int(
            (
                datetime.now(timezone.utc).replace(tzinfo=None) - session.started_at
            ).total_seconds()
            * 1000
        )

    question_count = len(session.quiz.questions)

    await connection_manager.broadcast_to_room(
        room_code,
        {
            "type": WSMessageType.GAME_FINISHED.value,
            "payload": WSGameFinished(
                final_leaderboard=leaderboard,
                total_questions=question_count,
                duration_ms=duration_ms,
            ).model_dump(by_alias=True),
        },
    )

    await game_service.clear_ranking_state(room_code)

    logger.info(
        "game_finished",
        room_code=room_code,
        duration_ms=duration_ms,
        player_count=len(leaderboard),
    )
