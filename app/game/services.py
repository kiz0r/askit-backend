import json
import random
from collections.abc import Awaitable
from datetime import datetime, timezone
from typing import cast
from uuid import UUID

from attrs import frozen
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.logging import get_logger
from app.core.utils import utcnow
from app.models.game import GamePlayer, GamePlayerAnswer, GameSession, GameSessionStatus
from app.models.quiz import Quiz, QuizQuestion
from app.models.user import User
from app.redis import get_redis_client
from app.user.schemas import GameHistoryItem, GameHistoryOut

from .exceptions import (
    AlreadyAnsweredError,
    GameAlreadyStartedError,
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
    WSLeaderboardEntry,
    WSQuestion,
    WSRoomState,
)

logger = get_logger(__name__)


# Redis key prefixes
QUESTION_START_KEY = "game:question_start:{room_code}"
PLAYER_ANSWERED_KEY = "game:answered:{room_code}:{question_index}"
PREV_RANKING_KEY = "game:prev_ranking:{room_code}"

# Scoring constants
MAX_POINTS_PER_QUESTION = 1000
MIN_POINTS_PER_QUESTION = 100
SPEED_BONUS_FACTOR = 0.5  # Faster answers get more points


def calculate_score(time_taken_ms: int, time_limit_ms: int, is_correct: bool) -> int:
    if not is_correct:
        return 0

    # Calculate time factor (1.0 = instant, 0.0 = at time limit)
    time_factor = max(0, 1 - (time_taken_ms / time_limit_ms))

    # Base points + speed bonus
    base_points = MIN_POINTS_PER_QUESTION
    speed_bonus = int(
        (MAX_POINTS_PER_QUESTION - MIN_POINTS_PER_QUESTION)
        * time_factor
        * SPEED_BONUS_FACTOR
    )

    return base_points + speed_bonus


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
            .where(Quiz.quiz_id == UUID(data.quiz_id))
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

        # Create game session
        session = GameSession(
            quiz_id=quiz.quiz_id,
            host_id=user.id,
            randomize_questions=data.randomize_questions,
            randomize_answers=data.randomize_answers,
            show_immediate_feedback=data.show_immediate_feedback,
        )
        db.add(session)
        await db.commit()
        await db.refresh(session)

        logger.info(
            "room_created",
            room_code=session.room_code,
            quiz_id=str(quiz.quiz_id),
            host_id=str(user.id),
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
                selectinload(GameSession.quiz).selectinload(Quiz.questions),
            )
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
        user: User,
    ) -> list[QuizQuestion]:
        """Start the game. Returns questions in play order."""
        session = await self.get_room(db, room_code)

        if session is None:
            raise RoomNotFoundError()

        if session.host_id != user.id:
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

        # Get question
        result = await db.execute(
            select(QuizQuestion)
            .where(QuizQuestion.question_id == UUID(question_id))
            .options(selectinload(QuizQuestion.answers))
        )
        question = result.scalars().first()
        if question is None:
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

        # Update player score
        player_result = await db.execute(
            select(GamePlayer).where(GamePlayer.player_id == UUID(player_id))
        )
        player = player_result.scalars().first()
        if player:
            player.score += points
            await db.commit()

        # Record answer
        answer_record = GamePlayerAnswer(
            player_id=UUID(player_id),
            question_id=UUID(question_id),
            selected_answer_ids=json.dumps(answer_ids),
            is_correct=is_correct,
            time_taken_ms=time_taken_ms,
            points_earned=points,
        )
        db.add(answer_record)
        await db.commit()

        # Mark as answered in Redis
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
    ) -> GameHistoryOut:
        finished = GameSessionStatus.finished

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
        player_entries = player_result.scalars().all()

        items: list[GameHistoryItem] = []

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

        items.sort(key=lambda x: x.started_at or datetime.min, reverse=True)
        total = len(items)
        return GameHistoryOut(items=items[offset : offset + limit], total=total)

    async def build_room_state(
        self,
        db: AsyncSession,
        room_code: str,
    ) -> WSRoomState | None:
        """Build full room state for sync."""
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

        return WSRoomState(
            session_id=str(session.session_id),
            room_code=session.room_code,
            status=session.status,
            host_id=str(session.host_id),
            players=players,
            quiz_title=session.quiz.title,
            total_questions=question_count,
            current_question_index=session.current_question_index,
        )

    async def build_question_message(
        self,
        question: QuizQuestion,
        question_index: int,
        total_questions: int,
        randomize_answers: bool = False,
    ) -> WSQuestion:
        """Build question message for players."""
        answers = list(question.answers)
        if randomize_answers:
            random.shuffle(answers)

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
            started_at=datetime.now(timezone.utc).isoformat(),
        )


# Singleton instance
game_service = GameService()
