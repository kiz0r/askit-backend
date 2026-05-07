"""move randomize_answers to game session

Revision ID: 9c2a7f1b0d3e
Revises: 8539fea09fae
Create Date: 2026-03-23 14:30:00.000000

"""

from typing import Sequence, Union

from alembic import op  # type: ignore[attr-defined]
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "9c2a7f1b0d3e"
down_revision: Union[str, None] = "8539fea09fae"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add randomize_answers column to game_sessions
    op.add_column(
        "game_sessions",
        sa.Column(
            "randomize_answers", sa.Boolean(), nullable=False, server_default="false"
        ),
    )

    # Remove randomize_answers column from quizzes
    op.drop_column("quizzes", "randomize_answers")


def downgrade() -> None:
    # Add randomize_answers back to quizzes
    op.add_column(
        "quizzes",
        sa.Column(
            "randomize_answers", sa.Boolean(), nullable=False, server_default="false"
        ),
    )

    # Remove randomize_answers from game_sessions
    op.drop_column("game_sessions", "randomize_answers")
