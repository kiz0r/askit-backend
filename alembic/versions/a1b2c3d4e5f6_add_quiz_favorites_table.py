"""add quiz favorites table

Revision ID: a1b2c3d4e5f6
Revises: 9c2a7f1b0d3e
Create Date: 2026-03-23 15:00:00.000000

"""

from typing import Sequence, Union

from alembic import op  # type: ignore[attr-defined]
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "9c2a7f1b0d3e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "quiz_favorites",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("quiz_id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.func.now(), nullable=True
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["quiz_id"], ["quizzes.quiz_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "quiz_id"),
    )
    # Index for faster lookups by user
    op.create_index("ix_quiz_favorites_user_id", "quiz_favorites", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_quiz_favorites_user_id", table_name="quiz_favorites")
    op.drop_table("quiz_favorites")
