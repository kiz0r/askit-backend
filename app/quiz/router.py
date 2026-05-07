"""Quiz router for CRUD operations and favorites."""

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.database import get_async_db
from app.models.user import User

from .exceptions import QuizAccessDeniedError, QuizNotFoundError
from .schemas import (
    FavoriteActionResponse,
    QuizCreate,
    QuizListOut,
    QuizOut,
    QuizStatsOut,
    QuizUpdate,
)
from .services import quiz_service
from .types import QuizId

router = APIRouter(tags=["Quiz"])


@router.post("", response_model=QuizOut, response_model_by_alias=True)
async def create_quiz(
    body: QuizCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
) -> QuizOut:
    quiz = await quiz_service.create_quiz(db, current_user, body)
    return quiz


@router.get("", response_model=QuizListOut, response_model_by_alias=True)
async def list_quizzes(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
) -> QuizListOut:
    quizzes = await quiz_service.list_quizzes(db, current_user)
    return QuizListOut(items=quizzes)


@router.get("/{quiz_id}", response_model=QuizOut, response_model_by_alias=True)
async def get_quiz(
    quiz_id: QuizId,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
) -> QuizOut:
    quiz = await quiz_service.get_quiz(db, quiz_id, owner=current_user)
    if quiz is None:
        raise QuizNotFoundError()

    return quiz


@router.patch("/{quiz_id}", response_model=QuizOut, response_model_by_alias=True)
async def update_quiz(
    quiz_id: QuizId,
    body: QuizUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
) -> QuizOut:
    quiz = await quiz_service.update_quiz(db, quiz_id, current_user, body)
    if quiz is None:
        # Distinguish between not found and access denied
        existing_quiz = await quiz_service.get_quiz(db, quiz_id)
        if existing_quiz is None:
            raise QuizNotFoundError()
        raise QuizAccessDeniedError()
    return quiz


@router.delete("/{quiz_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_quiz(
    quiz_id: QuizId,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
) -> Response:
    delete_result = await quiz_service.delete_quiz(db, quiz_id, current_user)
    if not delete_result:
        quiz = await quiz_service.get_quiz(db, quiz_id)
        if quiz is None:
            raise QuizNotFoundError()

        raise QuizAccessDeniedError()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# =============================================================================
# Publish / Unpublish
# =============================================================================


@router.post(
    "/{quiz_id}/publish",
    response_model=QuizOut,
    response_model_by_alias=True,
)
async def publish_quiz(
    quiz_id: QuizId,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
) -> QuizOut:
    return await quiz_service.publish_quiz(db, quiz_id, current_user)


@router.post(
    "/{quiz_id}/unpublish",
    response_model=QuizOut,
    response_model_by_alias=True,
)
async def unpublish_quiz(
    quiz_id: QuizId,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
) -> QuizOut:
    return await quiz_service.unpublish_quiz(db, quiz_id, current_user)


# =============================================================================
# Favorites
# =============================================================================


@router.get("/favorites/list", response_model=QuizListOut, response_model_by_alias=True)
async def list_favorites(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
) -> QuizListOut:
    """List all quizzes favorited by the current user."""
    quizzes = await quiz_service.list_favorites(db, current_user)
    return QuizListOut(items=quizzes)


@router.post(
    "/{quiz_id}/favorite",
    response_model=FavoriteActionResponse,
    response_model_by_alias=True,
)
async def add_favorite(
    quiz_id: QuizId,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
) -> FavoriteActionResponse:
    """Add a quiz to favorites."""
    result = await quiz_service.add_favorite(db, quiz_id, current_user)
    if result is None:
        raise QuizNotFoundError()
    return result


@router.delete(
    "/{quiz_id}/favorite",
    response_model=FavoriteActionResponse,
    response_model_by_alias=True,
)
async def remove_favorite(
    quiz_id: QuizId,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
) -> FavoriteActionResponse:
    result = await quiz_service.remove_favorite(db, quiz_id, current_user)
    if result is None:
        raise QuizNotFoundError()
    return result


# =============================================================================
# Stats
# =============================================================================


@router.get(
    "/{quiz_id}/stats", response_model=QuizStatsOut, response_model_by_alias=True
)
async def get_quiz_stats(
    quiz_id: QuizId,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
) -> QuizStatsOut:
    return await quiz_service.get_quiz_stats(db, quiz_id, current_user)
