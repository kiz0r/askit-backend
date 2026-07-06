"""add missing game session and question fields

Revision ID: d1e2f3a4b5c6
Revises: 79b6f7934e08
Create Date: 2026-06-10

"""

from typing import Sequence, Union

from alembic import op

revision: str = "d1e2f3a4b5c6"
down_revision: Union[str, None] = "79b6f7934e08"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE game_sessions ADD COLUMN IF NOT EXISTS "
        "randomize_questions BOOLEAN NOT NULL DEFAULT FALSE"
    )
    op.execute(
        "ALTER TABLE game_sessions ADD COLUMN IF NOT EXISTS "
        "show_immediate_feedback BOOLEAN NOT NULL DEFAULT TRUE"
    )
    op.execute(
        "ALTER TABLE quiz_questions ADD COLUMN IF NOT EXISTS "
        "allow_multiple_answers BOOLEAN NOT NULL DEFAULT FALSE"
    )


def downgrade() -> None:
    op.drop_column("game_sessions", "randomize_questions")
    op.drop_column("game_sessions", "show_immediate_feedback")
    op.drop_column("quiz_questions", "allow_multiple_answers")
