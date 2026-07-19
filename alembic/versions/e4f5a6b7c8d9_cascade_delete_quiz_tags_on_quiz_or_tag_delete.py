"""add ON DELETE CASCADE to quiz_tags FKs

Revision ID: e4f5a6b7c8d9
Revises: d1e2f3a4b5c6
Create Date: 2026-07-09 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op  # type: ignore[attr-defined]

revision: str = "e4f5a6b7c8d9"
down_revision: Union[str, None] = "d1e2f3a4b5c6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("quiz_tags_quiz_id_fkey", "quiz_tags", type_="foreignkey")
    op.create_foreign_key(
        "quiz_tags_quiz_id_fkey",
        "quiz_tags",
        "quizzes",
        ["quiz_id"],
        ["quiz_id"],
        ondelete="CASCADE",
    )

    op.drop_constraint("quiz_tags_tag_id_fkey", "quiz_tags", type_="foreignkey")
    op.create_foreign_key(
        "quiz_tags_tag_id_fkey",
        "quiz_tags",
        "tags",
        ["tag_id"],
        ["tag_id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint("quiz_tags_tag_id_fkey", "quiz_tags", type_="foreignkey")
    op.create_foreign_key(
        "quiz_tags_tag_id_fkey",
        "quiz_tags",
        "tags",
        ["tag_id"],
        ["tag_id"],
    )

    op.drop_constraint("quiz_tags_quiz_id_fkey", "quiz_tags", type_="foreignkey")
    op.create_foreign_key(
        "quiz_tags_quiz_id_fkey",
        "quiz_tags",
        "quizzes",
        ["quiz_id"],
        ["quiz_id"],
    )
