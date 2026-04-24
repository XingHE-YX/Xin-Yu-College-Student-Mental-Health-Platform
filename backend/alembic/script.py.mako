"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}
"""

from __future__ import annotations

from collections.abc import Sequence

<%
needs_op = "op." in upgrades or "op." in downgrades
needs_sa = "sa." in upgrades or "sa." in downgrades
%>
% if needs_op:
from alembic import op
% endif
% if needs_sa:
import sqlalchemy as sa
% endif
${imports if imports else ""}

# revision identifiers, used by Alembic.
revision: str = ${repr(up_revision)}
down_revision: str | None = ${repr(down_revision)}
branch_labels: str | Sequence[str] | None = ${repr(branch_labels)}
depends_on: str | Sequence[str] | None = ${repr(depends_on)}


def upgrade() -> None:
    """Apply the migration."""
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    """Revert the migration."""
    ${downgrades if downgrades else "pass"}
