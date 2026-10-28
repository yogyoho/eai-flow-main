"""remove the DingTalk-style MIMIC model

Revision ID: c4d8e2f1a7b3
Revises: edad31c13e6e
Create Date: 2026-10-26 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c4d8e2f1a7b3"
down_revision: str | None = "edad31c13e6e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Only the classic LogicFlow canvas remains. Existing DingTalk-style
    # definitions keep their stored coordinates and open as classic diagrams.
    op.execute(
        "UPDATE flow_definition SET model_value = 'CLASSICS' WHERE model_value IS NULL OR model_value <> 'CLASSICS'"
    )


def downgrade() -> None:
    # The previous model value cannot be reconstructed after normalization.
    pass
