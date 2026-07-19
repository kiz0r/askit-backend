from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.auth.dependencies import get_current_user
from app.database import get_async_db
from app.models.user import User
from .exceptions import QuizNotFoundError
from .schemas import (
    BulkStatsRequest,
    BulkStatsOut,
    FavoriteActionResponse,
    QuizCreate,
    QuizExportOut,
    QuizListOut,
    QuizOut,
    QuizStatsOut,
    QuizUpdate,
    SetQuizStatusInput,
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
    return QuizListOut(items=quizzes, total=len(quizzes))


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
    return await quiz_service.update_quiz(db, quiz_id, current_user, body)


@router.delete("/{quiz_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_quiz(
    quiz_id: QuizId,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
) -> Response:
    await quiz_service.delete_quiz(db, quiz_id, current_user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.patch(
    "/{quiz_id}/status",
    response_model=QuizOut,
    response_model_by_alias=True,
)
async def set_quiz_status(
    quiz_id: QuizId,
    body: SetQuizStatusInput,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
) -> QuizOut:
    return await quiz_service.set_quiz_status(db, quiz_id, body.status, current_user)


@router.get("/favorites/list", response_model=QuizListOut, response_model_by_alias=True)
async def list_favorites(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
) -> QuizListOut:
    quizzes = await quiz_service.list_favorites(db, current_user)
    return QuizListOut(items=quizzes, total=len(quizzes))


@router.post(
    "/{quiz_id}/favorite/toggle",
    response_model=FavoriteActionResponse,
    response_model_by_alias=True,
)
async def toggle_favorite(
    quiz_id: QuizId,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
) -> FavoriteActionResponse:
    result = await quiz_service.toggle_favorite(db, quiz_id, current_user)
    if result is None:
        raise QuizNotFoundError()
    return result


@router.get(
    "/{quiz_id}/stats", response_model=QuizStatsOut, response_model_by_alias=True
)
async def get_quiz_stats(
    quiz_id: QuizId,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
) -> QuizStatsOut:
    return await quiz_service.get_quiz_stats(db, quiz_id, current_user)


@router.get(
    "/{quiz_id}/export", response_model=QuizExportOut, response_model_by_alias=True
)
async def export_quiz(
    quiz_id: QuizId,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
) -> QuizExportOut:
    return await quiz_service.export_quiz(db, quiz_id, current_user)


@router.post("/import", response_model=QuizOut, response_model_by_alias=True)
async def import_quiz(
    body: QuizCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
) -> QuizOut:
    quiz = await quiz_service.create_quiz(db, current_user, body)
    return quiz


@router.post("/stats", response_model=BulkStatsOut, response_model_by_alias=True)
async def get_bulk_quiz_stats(
    body: BulkStatsRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
) -> BulkStatsOut:
    items = await quiz_service.get_bulk_quiz_stats(db, body.quiz_ids, current_user)
    return BulkStatsOut(items=items)
