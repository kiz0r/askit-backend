"""add ON DELETE CASCADE to game_player_answers.question_id FK

Revision ID: c3d4e5f6a7b8
Revises: b2e7c9f0a1d4
Create Date: 2026-05-12 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op  # type: ignore[attr-defined]

revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, None] = "b2e7c9f0a1d4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint(
        "game_player_answers_question_id_fkey",
        "game_player_answers",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "game_player_answers_question_id_fkey",
        "game_player_answers",
        "quiz_questions",
        ["question_id"],
        ["question_id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint(
        "game_player_answers_question_id_fkey",
        "game_player_answers",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "game_player_answers_question_id_fkey",
        "game_player_answers",
        "quiz_questions",
        ["question_id"],
        ["question_id"],
    )
