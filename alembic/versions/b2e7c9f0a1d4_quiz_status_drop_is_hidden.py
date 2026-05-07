"""quiz status draft published, drop question is_hidden

Revision ID: b2e7c9f0a1d4
Revises: a1b2c3d4e5f6
Create Date: 2026-04-17 10:00:00.000000

"""

from typing import Sequence, Union

from alembic import op  # type: ignore[attr-defined]
import sqlalchemy as sa


revision: str = "b2e7c9f0a1d4"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


quiz_status_enum = sa.Enum("draft", "published", name="quiz_status")


def upgrade() -> None:
    quiz_status_enum.create(op.get_bind(), checkfirst=True)

    # Add status with default 'published' so existing quizzes remain playable,
    # then drop the default — new quizzes default to 'draft' at the model level.
    op.add_column(
        "quizzes",
        sa.Column(
            "status",
            quiz_status_enum,
            nullable=False,
            server_default="published",
        ),
    )
    op.alter_column("quizzes", "status", server_default=None)

    op.drop_column("quiz_questions", "is_hidden")


def downgrade() -> None:
    op.add_column(
        "quiz_questions",
        sa.Column(
            "is_hidden",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.alter_column("quiz_questions", "is_hidden", server_default=None)

    op.drop_column("quizzes", "status")
    quiz_status_enum.drop(op.get_bind(), checkfirst=True)
