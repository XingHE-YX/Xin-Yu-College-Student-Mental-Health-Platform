"""add questionnaire submission deleted_at

Revision ID: b4f0f6d5d2a4
Revises: 5295854b6475
Create Date: 2026-05-19 10:35:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision: str = "b4f0f6d5d2a4"
down_revision: str | None = "5295854b6475"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply the migration."""
    op.add_column(
        "questionnaire_submissions",
        sa.Column(
            "deleted_at",
            sa.DateTime().with_variant(mysql.DATETIME(fsp=3), "mysql"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    """Revert the migration."""
    op.drop_column("questionnaire_submissions", "deleted_at")
