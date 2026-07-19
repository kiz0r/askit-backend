"""add unique constraint on (player_id, question_id) in game_player_answers

Revision ID: f5a6b7c8d9e0
Revises: e4f5a6b7c8d9
Create Date: 2026-07-13 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op  # type: ignore[attr-defined]

revision: str = "f5a6b7c8d9e0"
down_revision: Union[str, None] = "e4f5a6b7c8d9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Remove any pre-existing duplicate answers (keeping the earliest one per
    # player/question) so the new unique constraint can be created safely.
    op.execute(
        """
        DELETE FROM game_player_answers a
        USING game_player_answers b
        WHERE a.answer_record_id <> b.answer_record_id
          AND a.player_id = b.player_id
          AND a.question_id = b.question_id
          AND a.answered_at > b.answered_at
        """
    )
    op.create_unique_constraint(
        "uq_player_question_answer",
        "game_player_answers",
        ["player_id", "question_id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_player_question_answer", "game_player_answers", type_="unique"
    )
