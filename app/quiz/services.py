from datetime import datetime
from typing import Callable, TypeVar
from uuid import UUID
from attrs import frozen
from sqlalchemy import delete, insert, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.models.game import GameSession, GameSessionStatus
from app.models.quiz import Quiz, QuizAnswer, QuizQuestion, Tag, quiz_favorites
from app.models.user import User
from .exceptions import (
    InvalidQuizDataError,
    QuizAccessDeniedError,
    QuizNotFoundError,
    QuizPublishedError,
)
from .schemas import (
    FavoriteActionResponse,
    QuizAnswerOut,
    QuizCreate,
    QuizOut,
    QuizQuestionOut,
    QuizSettingsOut,
    QuizStatsOut,
    QuizStatus,
    QuizUpdate,
    TopPlayerOut,
)
from app.core.utils import utcnow
from .types import AnswerId, QuestionId, QuizId

_IdT = TypeVar("_IdT", bound=str)


def _to_id(id_type: Callable[[str], _IdT], value: str | UUID) -> _IdT:
    return id_type(str(value) if isinstance(value, UUID) else value)


@frozen
class QuizService:
    def _from_quiz_id(self, quiz_id: QuizId) -> UUID:
        return UUID(quiz_id)

    async def _fetch_quiz(self, db: AsyncSession, uuid_val: UUID) -> Quiz | None:
        result: Quiz | None = await db.scalar(
            select(Quiz)
            .where(Quiz.quiz_id == uuid_val)
            .options(
                selectinload(Quiz.questions).selectinload(QuizQuestion.answers),
                selectinload(Quiz.tags),
            )
        )
        return result

    def quiz_to_response(self, quiz: Quiz, *, is_favorited: bool = False) -> QuizOut:
        questions_out: list[QuizQuestionOut] = []
        for question in quiz.questions:
            questions_out.append(
                QuizQuestionOut(
                    question_id=_to_id(QuestionId, question.question_id),
                    text=question.text,
                    position=question.position,
                    time_limit=question.time_limit,
                    answers=[
                        QuizAnswerOut(
                            answer_id=_to_id(AnswerId, answer.answer_id),
                            text=answer.text,
                            is_correct=answer.is_correct,
                        )
                        for answer in question.answers
                    ],
                )
            )

        estimated_time = sum(q.time_limit for q in quiz.questions)
        tags = [tag.name for tag in quiz.tags] if quiz.tags else []

        return QuizOut(
            quiz_id=_to_id(QuizId, quiz.quiz_id),
            creator_id=str(quiz.creator_id),
            title=quiz.title,
            description=quiz.description,
            tags=tags,
            status=quiz.status,
            settings=QuizSettingsOut(
                default_time_per_question=quiz.default_time_per_question,
                visibility=quiz.visibility,
                max_participants=quiz.max_participants,
            ),
            questions=questions_out,
            estimated_time=estimated_time,
            created_at=quiz.created_at,
            updated_at=quiz.updated_at,
            is_favorited=is_favorited,
        )

    async def _get_or_create_tags(
        self, db: AsyncSession, tag_names: list[str]
    ) -> list[Tag]:
        if not tag_names:
            return []

        tags = []
        for name in tag_names:
            result = await db.execute(select(Tag).where(Tag.name == name))
            tag = result.scalars().first()
            if tag is None:
                tag = Tag(name=name)
                db.add(tag)
            tags.append(tag)
        return tags

    async def create_quiz(
        self, db: AsyncSession, user: User, data: QuizCreate
    ) -> QuizOut:
        # Get or create tags
        tags = await self._get_or_create_tags(db, data.tags)

        quiz = Quiz(
            title=data.title,
            description=data.description,
            creator_id=user.id,
            default_time_per_question=data.settings.default_time_per_question,
            visibility=data.settings.visibility,
            max_participants=data.settings.max_participants,
            tags=tags,
        )

        for position, question_data in enumerate(data.questions, start=1):
            question = QuizQuestion(
                text=question_data.text,
                position=position,
                time_limit=question_data.time_limit,
            )
            answers_objs: list[QuizAnswer] = []
            correct_answers = []

            for answer_data in question_data.answers:
                answer = QuizAnswer(
                    text=answer_data.text,
                    is_correct=answer_data.is_correct,
                )
                answers_objs.append(answer)
                if answer_data.is_correct:
                    correct_answers.append(answer)

            if not correct_answers:
                raise InvalidQuizDataError(
                    f"Question {position} must have at least one correct answer."
                )

            question.answers = answers_objs
            quiz.questions.append(question)

        db.add(quiz)
        await db.commit()

        created = await self._fetch_quiz(db, quiz.quiz_id)
        if created is None:
            raise QuizNotFoundError()
        return self.quiz_to_response(created)

    async def get_quiz(
        self, db: AsyncSession, quiz_id: QuizId, owner: User | None = None
    ) -> QuizOut | None:
        try:
            uuid_val = self._from_quiz_id(quiz_id)
            result = await db.execute(
                select(Quiz)
                .where(Quiz.quiz_id == uuid_val)
                .options(
                    selectinload(Quiz.questions).selectinload(QuizQuestion.answers),
                    selectinload(Quiz.tags),
                )
            )
            quiz = result.scalars().first()
            if quiz is None:
                return None
            if owner is not None and quiz.creator_id != owner.id:
                return None

            is_fav = False
            if owner is not None:
                fav_result = await db.execute(
                    select(quiz_favorites).where(
                        quiz_favorites.c.user_id == owner.id,
                        quiz_favorites.c.quiz_id == uuid_val,
                    )
                )
                is_fav = fav_result.first() is not None

            return self.quiz_to_response(quiz, is_favorited=is_fav)
        except ValueError:
            return None

    async def update_quiz(
        self, db: AsyncSession, quiz_id: QuizId, user: User, data: QuizUpdate
    ) -> QuizOut:
        uuid_val = self._from_quiz_id(quiz_id)
        quiz = await self._fetch_quiz(db, uuid_val)

        if quiz is None:
            raise QuizNotFoundError()

        if quiz.creator_id != user.id:
            raise QuizAccessDeniedError()

        if quiz.status == QuizStatus.published:
            raise QuizPublishedError()

        # Update fields if provided
        if data.title is not None:
            quiz.title = data.title
        if data.description is not None:
            quiz.description = data.description
        if data.tags is not None:
            quiz.tags = await self._get_or_create_tags(db, data.tags)
        if data.settings is not None:
            quiz.default_time_per_question = data.settings.default_time_per_question
            quiz.visibility = data.settings.visibility
            quiz.max_participants = data.settings.max_participants

        # Update questions if provided
        if data.questions is not None:
            # Delete existing questions (cascades to answers)
            for question in quiz.questions:
                await db.delete(question)
            quiz.questions.clear()
            await db.flush()

            # Add new questions and answers
            for position, question_data in enumerate(data.questions, start=1):
                question = QuizQuestion(
                    text=question_data.text,
                    position=position,
                    time_limit=question_data.time_limit,
                )
                answers_objs: list[QuizAnswer] = []
                correct_answers = []

                for answer_data in question_data.answers:
                    answer = QuizAnswer(
                        text=answer_data.text,
                        is_correct=answer_data.is_correct,
                    )
                    answers_objs.append(answer)
                    if answer_data.is_correct:
                        correct_answers.append(answer)

                if not correct_answers:
                    raise InvalidQuizDataError(
                        f"Question {position} must have at least one correct answer."
                    )

                question.answers = answers_objs
                quiz.questions.append(question)

        # Explicitly update timestamp (onupdate doesn't trigger for related changes)
        quiz.updated_at = utcnow()

        await db.commit()

        updated = await self._fetch_quiz(db, uuid_val)
        if updated is None:
            raise QuizNotFoundError()
        return self.quiz_to_response(updated)

    async def _set_quiz_status(
        self,
        db: AsyncSession,
        quiz_id: QuizId,
        user: User,
        new_status: QuizStatus,
    ) -> QuizOut:
        uuid_val = self._from_quiz_id(quiz_id)
        quiz = await self._fetch_quiz(db, uuid_val)

        if quiz is None:
            raise QuizNotFoundError()
        if quiz.creator_id != user.id:
            raise QuizAccessDeniedError()

        if new_status == QuizStatus.published and not quiz.questions:
            raise InvalidQuizDataError("Cannot publish a quiz that has no questions.")

        quiz.status = new_status
        quiz.updated_at = utcnow()
        await db.commit()

        refreshed = await self._fetch_quiz(db, uuid_val)
        if refreshed is None:
            raise QuizNotFoundError()
        return self.quiz_to_response(refreshed)

    async def publish_quiz(
        self, db: AsyncSession, quiz_id: QuizId, user: User
    ) -> QuizOut:
        return await self._set_quiz_status(db, quiz_id, user, QuizStatus.published)

    async def unpublish_quiz(
        self, db: AsyncSession, quiz_id: QuizId, user: User
    ) -> QuizOut:
        return await self._set_quiz_status(db, quiz_id, user, QuizStatus.draft)

    async def delete_quiz(self, db: AsyncSession, quiz_id: QuizId, user: User) -> None:
        uuid_val = self._from_quiz_id(quiz_id)
        result = await db.execute(
            select(Quiz)
            .where(Quiz.quiz_id == uuid_val)
            .options(selectinload(Quiz.questions))
        )
        quiz = result.scalars().first()

        if quiz is None:
            raise QuizNotFoundError()

        if quiz.creator_id != user.id:
            raise QuizAccessDeniedError()

        await db.delete(quiz)
        await db.commit()

    async def list_quizzes(self, db: AsyncSession, user: User) -> list[QuizOut]:
        result = await db.execute(
            select(Quiz)
            .where(Quiz.creator_id == user.id)
            .options(
                selectinload(Quiz.questions).selectinload(QuizQuestion.answers),
                selectinload(Quiz.tags),
            )
        )
        quizzes = result.scalars().all()

        fav_result = await db.execute(
            select(quiz_favorites.c.quiz_id).where(quiz_favorites.c.user_id == user.id)
        )
        favorited_ids = {row.quiz_id for row in fav_result}

        return [
            self.quiz_to_response(quiz, is_favorited=quiz.quiz_id in favorited_ids)
            for quiz in quizzes
        ]

    async def toggle_favorite(
        self, db: AsyncSession, quiz_id: QuizId, user: User
    ) -> FavoriteActionResponse | None:
        """Toggle favorite state for a quiz. Returns None if quiz not found."""
        uuid_val = self._from_quiz_id(quiz_id)

        result = await db.execute(select(Quiz).where(Quiz.quiz_id == uuid_val))
        if result.scalars().first() is None:
            return None

        existing = await db.execute(
            select(quiz_favorites).where(
                quiz_favorites.c.user_id == user.id,
                quiz_favorites.c.quiz_id == uuid_val,
            )
        )
        is_favorited = existing.first() is not None

        if is_favorited:
            await db.execute(
                delete(quiz_favorites).where(
                    quiz_favorites.c.user_id == user.id,
                    quiz_favorites.c.quiz_id == uuid_val,
                )
            )
        else:
            await db.execute(
                insert(quiz_favorites).values(user_id=user.id, quiz_id=uuid_val)
            )

        await db.commit()
        return FavoriteActionResponse(
            quiz_id=str(uuid_val), is_favorited=not is_favorited
        )

    async def list_favorites(self, db: AsyncSession, user: User) -> list[QuizOut]:
        result = await db.execute(
            select(Quiz)
            .join(Quiz.favorited_by)
            .where(User.id == user.id)
            .options(
                selectinload(Quiz.questions).selectinload(QuizQuestion.answers),
                selectinload(Quiz.tags),
            )
        )
        quizzes = result.scalars().all()
        return [self.quiz_to_response(quiz) for quiz in quizzes]

    async def get_quiz_stats(
        self,
        db: AsyncSession,
        quiz_id: QuizId,
        user: User,
    ) -> QuizStatsOut:
        uuid_val = self._from_quiz_id(quiz_id)
        quiz = await self._fetch_quiz(db, uuid_val)
        if quiz is None:
            raise QuizNotFoundError()
        if quiz.creator_id != user.id:
            raise QuizAccessDeniedError()

        sessions_result = await db.execute(
            select(GameSession)
            .options(selectinload(GameSession.players))
            .where(
                GameSession.quiz_id == UUID(quiz_id),
                GameSession.status == GameSessionStatus.finished,
            )
        )
        sessions = sessions_result.scalars().all()

        if not sessions:
            return QuizStatsOut(
                quiz_id=quiz_id,
                times_played=0,
                total_players=0,
                average_score=0,
                average_duration_seconds=0,
                top_players=[],
            )

        all_players = [p for s in sessions for p in s.players]
        total_players = len(all_players)
        average_score = (
            sum(p.score for p in all_players) // total_players if total_players else 0
        )

        durations = [
            int((s.ended_at - s.started_at).total_seconds())
            for s in sessions
            if s.started_at and s.ended_at
        ]
        average_duration = sum(durations) // len(durations) if durations else 0

        top_players = [
            TopPlayerOut(
                nickname=str(p.nickname),
                score=p.score,
                played_at=s.started_at or datetime.min,
            )
            for s in sessions
            for p in s.players
        ]
        top_players.sort(key=lambda x: x.score, reverse=True)
        top_players = top_players[:10]

        return QuizStatsOut(
            quiz_id=quiz_id,
            times_played=len(sessions),
            total_players=total_players,
            average_score=average_score,
            average_duration_seconds=average_duration,
            top_players=top_players,
        )


# Singleton instance
quiz_service = QuizService()
