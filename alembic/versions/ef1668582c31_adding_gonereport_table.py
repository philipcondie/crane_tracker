"""Add gone_report table.

Revision ID: ef1668582c31
Revises: 69af4f84e5fc
Create Date: 2026-07-25 13:40:13.994605

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "ef1668582c31"
down_revision: Union[str, Sequence[str], None] = "69af4f84e5fc"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "gone_report",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("crane_id", sa.Uuid(), nullable=False),
        sa.Column("reporter_ip_hash", sa.String(), nullable=False),
        sa.Column(
            "added_at",
            sa.DateTime(),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["crane_id"],
            ["crane.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "crane_id",
            "reporter_ip_hash",
            name="crane_reporter",
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("gone_report")
