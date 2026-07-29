import json
import random
from collections.abc import Awaitable
from datetime import datetime, timezone
from typing import Literal, cast
from uuid import UUID

from attrs import frozen
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.logging import get_logger
from app.core.utils import utcnow
from app.models.game import (
    GamePlayer,
    GamePlayerAnswer,
    GameSession,
    GameSessionStatus,
    generate_room_code,
)
from app.models.quiz import Quiz, QuizQuestion
from app.models.user import User
from app.redis import get_redis_client
from app.user.schemas import GameHistoryItem, GameHistoryOut

from .exceptions import (
    AlreadyAnsweredError,
    GameAlreadyStartedError,
    HostCannotJoinError,
    NicknameAlreadyTakenError,
    NotHostError,
    QuestionNotActiveError,
    RoomFullError,
    RoomNotFoundError,
)
from .schemas import (
    CreateRoomRequest,
    PlayerInfo,
    RoomResponse,
    WSAnswerOption,
    WSAnswerResult,
    WSGameFinished,
    WSHostAnswerUpdate,
    WSLeaderboardEntry,
    WSQuestion,
    WSQuestionEnded,
    WSRoomState,
)

logger = get_logger(__name__)


# Redis key prefixes
QUESTION_START_KEY = "game:question_start:{room_code}"
PLAYER_ANSWERED_KEY = "game:answered:{room_code}:{question_index}"
PREV_RANKING_KEY = "game:prev_ranking:{room_code}"

# How many times to retry room creation when the generated code is taken.
_ROOM_CODE_ATTEMPTS = 5

# Scoring constants
MAX_POINTS_PER_QUESTION = 1000
MIN_POINTS_PER_QUESTION = 100


def calculate_score(time_taken_ms: int, time_limit_ms: int, is_correct: bool) -> int:
    if not is_correct:
        return 0

    time_factor = max(0.0, 1.0 - (time_taken_ms / time_limit_ms))
    speed_bonus = int((MAX_POINTS_PER_QUESTION - MIN_POINTS_PER_QUESTION) * time_factor)

    return MIN_POINTS_PER_QUESTION + speed_bonus


@frozen
class GameService:
    """Service for game session management."""

    async def create_room(
        self,
        db: AsyncSession,
        user: User,
        data: CreateRoomRequest,
    ) -> RoomResponse:
        """Create a new game room for a quiz."""
        # Verify quiz exists and user owns it
        result = await db.execute(
            select(Quiz)
            .where(Quiz.quiz_id == data.quiz_id)
            .options(selectinload(Quiz.questions))
        )
        quiz = result.scalars().first()

        if quiz is None:
            from app.quiz.exceptions import QuizNotFoundError

            raise QuizNotFoundError()

        if quiz.creator_id != user.id:
            from app.quiz.exceptions import QuizAccessDeniedError

            raise QuizAccessDeniedError()

        from app.quiz.exceptions import QuizNotPlayableError
        from app.quiz.schemas import QuizStatus

        if quiz.status != QuizStatus.published:
            raise QuizNotPlayableError()

        # Room codes are six characters from a 31-symbol alphabet and are never
        # released, so the space only shrinks as sessions accumulate. A collision
        # is very unlikely but not impossible, and the unique index turns one
        # into a failed request. Retry with a fresh code instead of checking
        # first, which would leave a window between the check and the insert.
        # Read these before the loop: a rollback expires every object in the
        # session, so touching quiz or user again inside it would trigger a lazy
        # reload.
        quiz_id = quiz.quiz_id
        host_id = user.id

        for remaining in range(_ROOM_CODE_ATTEMPTS - 1, -1, -1):
            session = GameSession(
                room_code=generate_room_code(),
                quiz_id=quiz_id,
                host_id=host_id,
                randomize_questions=data.randomize_questions,
                randomize_answers=data.randomize_answers,
                show_immediate_feedback=data.show_immediate_feedback,
                public_results=data.public_results,
            )
            db.add(session)
            try:
                await db.commit()
                break
            except IntegrityError:
                await db.rollback()
                if remaining == 0:
                    raise
                logger.warning("room_code_collision", attempts_left=remaining)

        await db.refresh(session)

        logger.info(
            "room_created",
            room_code=session.room_code,
            quiz_id=str(quiz_id),
            host_id=str(host_id),
        )

        return RoomResponse(
            session_id=str(session.session_id),
            room_code=session.room_code,
            quiz_id=str(session.quiz_id),
            status=session.status,
            player_count=0,
            created_at=session.created_at,
        )

    async def get_room(
        self,
        db: AsyncSession,
        room_code: str,
    ) -> GameSession | None:
        """Get a game session by room code."""
        result = await db.execute(
            select(GameSession)
            .where(GameSession.room_code == room_code.upper())
            .options(
                selectinload(GameSession.players),
                selectinload(GameSession.quiz)
                .selectinload(Quiz.questions)
                .selectinload(QuizQuestion.answers),
            )
            .execution_options(populate_existing=True)
        )
        session: GameSession | None = result.scalars().first()
        return session

    async def join_room(
        self,
        db: AsyncSession,
        room_code: str,
        nickname: str,
        user: User | None = None,
    ) -> tuple[GameSession, GamePlayer]:
        """Add a player to a game room."""
        session = await self.get_room(db, room_code)

        if session is None:
            raise RoomNotFoundError()

        if session.status != GameSessionStatus.waiting:
            raise GameAlreadyStartedError()

        if user is not None and session.host_id == user.id:
            raise HostCannotJoinError()

        # Check max participants
        quiz = session.quiz
        if quiz.max_participants and len(session.players) >= quiz.max_participants:
            raise RoomFullError()

        # Check nickname uniqueness in room
        for player in session.players:
            if player.nickname.lower() == nickname.lower():
                raise NicknameAlreadyTakenError()

        # Create player
        player = GamePlayer(
            session_id=session.session_id,
            nickname=nickname,
            user_id=user.id if user else None,
        )
        db.add(player)
        await db.commit()
        await db.refresh(player)

        logger.info(
            "player_joined",
            room_code=room_code,
            player_id=str(player.player_id),
            nickname=nickname,
        )

        return session, player

    async def start_game(
        self,
        db: AsyncSession,
        room_code: str,
        host_id: UUID,
    ) -> list[QuizQuestion]:
        """Start the game. Returns questions in play order.

        Takes the host's id rather than the loaded ``User``: the WebSocket
        handler that calls this opens a fresh session per message, and an ORM
        instance must not be carried across that boundary.
        """
        session = await self.get_room(db, room_code)

        if session is None:
            raise RoomNotFoundError()

        if session.host_id != host_id:
            raise NotHostError()

        if session.status != GameSessionStatus.waiting:
            raise GameAlreadyStartedError()

        # Get questions
        questions = list(session.quiz.questions)

        # Randomize if configured
        if session.randomize_questions:
            random.shuffle(questions)
        else:
            questions.sort(key=lambda q: q.position)

        # Update session status
        session.status = GameSessionStatus.starting
        session.started_at = utcnow()
        await db.commit()

        # Store question order in Redis
        redis_client = get_redis_client()
        question_ids = [str(q.question_id) for q in questions]
        await redis_client.set(
            f"game:questions:{room_code}",
            json.dumps(question_ids),
            ex=3600,  # 1 hour expiry
        )

        logger.info(
            "game_started",
            room_code=room_code,
            question_count=len(questions),
        )

        return questions

    async def get_current_question(
        self,
        db: AsyncSession,
        room_code: str,
    ) -> QuizQuestion | None:
        """Get the current question for a game."""
        session = await self.get_room(db, room_code)
        if session is None or session.current_question_index == 0:
            return None

        redis_client = get_redis_client()
        question_ids_json = await redis_client.get(f"game:questions:{room_code}")
        if not question_ids_json:
            return None

        question_ids = json.loads(question_ids_json)
        if session.current_question_index > len(question_ids):
            return None

        question_id = question_ids[session.current_question_index - 1]

        result = await db.execute(
            select(QuizQuestion)
            .where(QuizQuestion.question_id == UUID(question_id))
            .options(selectinload(QuizQuestion.answers))
        )
        question: QuizQuestion | None = result.scalars().first()
        return question

    async def advance_to_question(
        self,
        db: AsyncSession,
        room_code: str,
        question_index: int,
    ) -> QuizQuestion | None:
        """Move to a specific question index."""
        session = await self.get_room(db, room_code)
        if session is None:
            raise RoomNotFoundError()

        redis_client = get_redis_client()
        question_ids_json = await redis_client.get(f"game:questions:{room_code}")
        if not question_ids_json:
            return None

        question_ids = json.loads(question_ids_json)

        if question_index > len(question_ids):
            # Game finished
            session.status = GameSessionStatus.finished
            session.ended_at = utcnow()
            await db.commit()
            return None

        # Update game state
        session.status = GameSessionStatus.question
        session.current_question_index = question_index
        await db.commit()

        # Store question start time in Redis
        await redis_client.set(
            QUESTION_START_KEY.format(room_code=room_code),
            datetime.now(timezone.utc).isoformat(),
            ex=600,  # 10 min expiry
        )

        question_id = question_ids[question_index - 1]
        result = await db.execute(
            select(QuizQuestion)
            .where(QuizQuestion.question_id == UUID(question_id))
            .options(selectinload(QuizQuestion.answers))
        )
        question: QuizQuestion | None = result.scalars().first()
        return question

    async def submit_answer(
        self,
        db: AsyncSession,
        room_code: str,
        player_id: str,
        question_id: str,
        answer_ids: list[str],
    ) -> WSAnswerResult:
        """Process a player's answer submission."""
        session = await self.get_room(db, room_code)
        if session is None:
            raise RoomNotFoundError()

        if session.status != GameSessionStatus.question:
            raise QuestionNotActiveError()

        # Check if player already answered
        redis_client = get_redis_client()
        answered_key = PLAYER_ANSWERED_KEY.format(
            room_code=room_code,
            question_index=session.current_question_index,
        )
        if await cast(Awaitable[int], redis_client.sismember(answered_key, player_id)):
            raise AlreadyAnsweredError()

        # Validate the client-supplied question_id against the current active
        # question. A player must not be able to answer a different question,
        # and a malformed id must not reach UUID() and surface as a 500.
        try:
            submitted_question_id = UUID(question_id)
        except ValueError:
            raise QuestionNotActiveError()

        question = await self.get_current_question(db, room_code)
        if question is None or question.question_id != submitted_question_id:
            raise QuestionNotActiveError()

        # Calculate time taken
        question_start = await redis_client.get(
            QUESTION_START_KEY.format(room_code=room_code)
        )
        if question_start:
            start_time = datetime.fromisoformat(question_start)
            time_taken_ms = int(
                (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
            )
        else:
            time_taken_ms = question.time_limit

        # Check correctness
        correct_answer_ids = {
            str(a.answer_id) for a in question.answers if a.is_correct
        }
        submitted_ids = set(answer_ids)
        is_correct = submitted_ids == correct_answer_ids

        # Calculate score
        points = calculate_score(time_taken_ms, question.time_limit, is_correct)

        # Update player score and record the answer atomically. The unique
        # constraint on (player_id, question_id) is the authoritative guard
        # against duplicate answers: the Redis SISMEMBER check above is only
        # a fast-path optimization and can be bypassed if Redis loses its
        # state (e.g. a restart mid-session), so both changes are committed
        # together and a duplicate is rejected here regardless.
        player_result = await db.execute(
            select(GamePlayer).where(GamePlayer.player_id == UUID(player_id))
        )
        player = player_result.scalars().first()
        if player:
            player.score += points

        answer_record = GamePlayerAnswer(
            player_id=UUID(player_id),
            question_id=UUID(question_id),
            selected_answer_ids=json.dumps(answer_ids),
            is_correct=is_correct,
            time_taken_ms=time_taken_ms,
            points_earned=points,
        )
        db.add(answer_record)
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
            raise AlreadyAnsweredError()

        # Mark as answered in Redis so subsequent submissions can be
        # rejected without a database round trip.
        await cast(Awaitable[int], redis_client.sadd(answered_key, player_id))
        await redis_client.expire(answered_key, 600)

        logger.info(
            "answer_submitted",
            room_code=room_code,
            player_id=player_id,
            is_correct=is_correct,
            points=points,
        )

        return WSAnswerResult(
            is_correct=is_correct,
            correct_answer_ids=list(correct_answer_ids),
            points_earned=points,
            time_taken_ms=time_taken_ms,
        )

    async def get_leaderboard(
        self,
        db: AsyncSession,
        room_code: str,
    ) -> list[WSLeaderboardEntry]:
        session = await self.get_room(db, room_code)
        if session is None:
            return []

        players = sorted(session.players, key=lambda p: p.score, reverse=True)

        redis_client = get_redis_client()
        prev_ranking_json = await redis_client.get(
            PREV_RANKING_KEY.format(room_code=room_code)
        )
        prev_ranking: dict[str, int] = (
            json.loads(prev_ranking_json) if prev_ranking_json else {}
        )

        entries = []
        new_ranking: dict[str, int] = {}
        for rank, player in enumerate(players, 1):
            pid = str(player.player_id)
            prev_rank = prev_ranking.get(pid, rank)
            new_ranking[pid] = rank
            entries.append(
                WSLeaderboardEntry(
                    rank=rank,
                    player_id=pid,
                    nickname=player.nickname,
                    score=player.score,
                    change=prev_rank - rank,
                )
            )

        await redis_client.set(
            PREV_RANKING_KEY.format(room_code=room_code),
            json.dumps(new_ranking),
            ex=3600,
        )

        return entries

    async def compute_answer_distribution(
        self,
        db: AsyncSession,
        session_id: UUID,
        question: QuizQuestion,
    ) -> dict[str, int]:
        result = await db.execute(
            select(GamePlayerAnswer.selected_answer_ids)
            .join(GamePlayer, GamePlayerAnswer.player_id == GamePlayer.player_id)
            .where(
                GamePlayer.session_id == session_id,
                GamePlayerAnswer.question_id == question.question_id,
            )
        )
        rows = result.scalars().all()

        counts: dict[str, int] = {str(a.answer_id): 0 for a in question.answers}
        for row in rows:
            for aid in json.loads(row):
                if aid in counts:
                    counts[aid] += 1

        return counts

    async def clear_ranking_state(self, room_code: str) -> None:
        redis_client = get_redis_client()
        await redis_client.delete(PREV_RANKING_KEY.format(room_code=room_code))

    async def get_game_history(
        self,
        db: AsyncSession,
        user: User,
        limit: int = 20,
        offset: int = 0,
        role: Literal["host", "player"] | None = None,
    ) -> GameHistoryOut:
        finished = GameSessionStatus.finished

        items: list[GameHistoryItem] = []

        if role != "player":
            host_result = await db.execute(
                select(GameSession)
                .options(
                    selectinload(GameSession.quiz),
                    selectinload(GameSession.players),
                )
                .where(
                    GameSession.host_id == user.id,
                    GameSession.status == finished,
                )
            )
            host_sessions = host_result.scalars().all()

            for session in host_sessions:
                items.append(
                    GameHistoryItem(
                        session_id=str(session.session_id),
                        room_code=str(session.room_code),
                        quiz_id=str(session.quiz_id),
                        quiz_title=str(session.quiz.title),
                        role="host",
                        score=None,
                        rank=None,
                        total_players=len(session.players),
                        started_at=session.started_at,
                        ended_at=session.ended_at,
                        status=str(session.status.value),
                    )
                )

        player_entries: list[GamePlayer] = []
        if role != "host":
            player_result = await db.execute(
                select(GamePlayer)
                .options(
                    selectinload(GamePlayer.session).selectinload(GameSession.quiz),
                    selectinload(GamePlayer.session).selectinload(GameSession.players),
                )
                .join(GameSession, GamePlayer.session_id == GameSession.session_id)
                .where(
                    GamePlayer.user_id == user.id,
                    GameSession.status == finished,
                )
            )
            player_entries = list(player_result.scalars().all())

        for player in player_entries:
            session = player.session
            sorted_players = sorted(
                session.players, key=lambda p: p.score, reverse=True
            )
            rank = next(
                (
                    i + 1
                    for i, p in enumerate(sorted_players)
                    if p.player_id == player.player_id
                ),
                None,
            )
            items.append(
                GameHistoryItem(
                    session_id=str(session.session_id),
                    room_code=str(session.room_code),
                    quiz_id=str(session.quiz_id),
                    quiz_title=str(session.quiz.title),
                    role="player",
                    score=player.score,
                    rank=rank,
                    total_players=len(session.players),
                    started_at=session.started_at,
                    ended_at=session.ended_at,
                    status=str(session.status.value),
                )
            )

        items.sort(
            key=lambda x: (x.started_at or datetime.min, x.session_id, x.role),
            reverse=True,
        )
        total = len(items)
        return GameHistoryOut(items=items[offset : offset + limit], total=total)

    async def build_room_state(
        self,
        db: AsyncSession,
        room_code: str,
        *,
        for_host: bool = False,
    ) -> WSRoomState | None:
        """Build full room state for sync.

        ``for_host`` gates the fields that only the host may see. The per-player
        answer feed reveals which players have answered and, through their
        selected answer ids, what the correct answer is while the question is
        still running, so it must never reach a player's connection. It defaults
        to off so a new call site leaks nothing by omission.
        """
        session = await self.get_room(db, room_code)
        if session is None:
            return None

        players = [
            PlayerInfo(
                player_id=str(p.player_id),
                nickname=p.nickname,
                score=p.score,
                is_connected=p.is_connected,
            )
            for p in session.players
        ]

        question_count = len(session.quiz.questions)

        current_question: WSQuestion | None = None
        host_answer_details: list[WSHostAnswerUpdate] = []
        question_ended: WSQuestionEnded | None = None
        if session.status in (GameSessionStatus.question, GameSessionStatus.revealing):
            question = await self.get_current_question(db, room_code)
            if question is not None:
                current_question = await self.build_question_message(
                    question,
                    session.current_question_index,
                    question_count,
                    room_code=room_code,
                    randomize_answers=session.randomize_answers,
                )
                if for_host:
                    host_answer_details = await self.build_host_answer_details(
                        db, session, question
                    )

                if session.status == GameSessionStatus.revealing:
                    question_ended = WSQuestionEnded(
                        question_id=str(question.question_id),
                        correct_answer_ids=[
                            str(a.answer_id) for a in question.answers if a.is_correct
                        ],
                        answer_distribution=await self.compute_answer_distribution(
                            db, session.session_id, question
                        ),
                        leaderboard=await self.get_leaderboard(db, room_code),
                    )

        return WSRoomState(
            session_id=str(session.session_id),
            room_code=session.room_code,
            status=session.status,
            host_id=str(session.host_id),
            players=players,
            quiz_title=session.quiz.title,
            total_questions=question_count,
            current_question_index=session.current_question_index,
            current_question=current_question,
            host_answer_details=host_answer_details,
            question_ended=question_ended,
        )

    async def build_host_answer_details(
        self,
        db: AsyncSession,
        session: GameSession,
        question: QuizQuestion,
    ) -> list[WSHostAnswerUpdate]:
        """Rebuild the host's per-player answer feed for the current question.

        Used on host reconnection so the answered-count and answer breakdown
        survive a page reload mid-question.
        """
        result = await db.execute(
            select(GamePlayerAnswer, GamePlayer)
            .join(GamePlayer, GamePlayerAnswer.player_id == GamePlayer.player_id)
            .where(
                GamePlayer.session_id == session.session_id,
                GamePlayerAnswer.question_id == question.question_id,
            )
        )

        details: list[WSHostAnswerUpdate] = []
        for answer, player in result.all():
            details.append(
                WSHostAnswerUpdate(
                    player_id=str(player.player_id),
                    nickname=player.nickname,
                    is_correct=answer.is_correct,
                    answer_ids=json.loads(answer.selected_answer_ids),
                    time_taken_ms=answer.time_taken_ms,
                    total_score=player.score,
                )
            )

        return details

    async def build_game_finished(
        self,
        db: AsyncSession,
        room_code: str,
    ) -> WSGameFinished | None:
        """Build the final results payload for a finished game."""
        session = await self.get_room(db, room_code)
        if session is None:
            return None

        leaderboard = await self.get_leaderboard(db, room_code)

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

        return WSGameFinished(
            final_leaderboard=leaderboard,
            total_questions=len(session.quiz.questions),
            duration_ms=duration_ms,
            public_results=session.public_results,
        )

    async def build_question_message(
        self,
        question: QuizQuestion,
        question_index: int,
        total_questions: int,
        room_code: str,
        randomize_answers: bool = False,
    ) -> WSQuestion:
        """Build question message for players."""
        answers = list(question.answers)
        if randomize_answers:
            # Seeded from the question id so the order is stable for the whole
            # question: a client that reconnects mid-question is rebuilt the
            # same message it first received, rather than seeing the options
            # (and their letters and colours) jump to a new order.
            random.Random(str(question.question_id)).shuffle(answers)

        redis_client = get_redis_client()
        question_start = await redis_client.get(
            QUESTION_START_KEY.format(room_code=room_code)
        )
        started_at = (
            question_start if question_start else datetime.now(timezone.utc).isoformat()
        )

        return WSQuestion(
            question_index=question_index,
            total_questions=total_questions,
            question_id=str(question.question_id),
            text=question.text,
            answers=[
                WSAnswerOption(
                    answer_id=str(a.answer_id),
                    text=a.text,
                )
                for a in answers
            ],
            time_limit_ms=question.time_limit,
            started_at=started_at,
            allow_multiple_answers=question.allow_multiple_answers,
        )


# Singleton instance
game_service = GameService()
