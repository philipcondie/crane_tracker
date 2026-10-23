"""Add crane photo table.

Revision ID: 42da8c9cd521
Revises: ef1668582c31
Create Date: 2026-07-29

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "42da8c9cd521"
down_revision: Union[str, Sequence[str], None] = "ef1668582c31"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "crane_photo",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("crane_id", sa.Uuid(), nullable=False),
        sa.Column("storage_key", sa.String(length=1024), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=100), nullable=False),
        sa.Column(
            "added_at",
            sa.DateTime(),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            'status',
            sa.Enum(
                'active', 'pending_upload', 'pending_delete',
                name='crane_photo_status'),
            nullable=False
        ),
        sa.ForeignKeyConstraint(["crane_id"], ["crane.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("storage_key"),
    )
    op.create_index(
        op.f("ix_crane_photo_crane_id"),
        "crane_photo",
        ["crane_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_crane_photo_crane_id"), table_name="crane_photo")
    op.drop_table("crane_photo")
