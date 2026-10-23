"""Add provisioned admin accounts and expiring sessions.

Revision ID: c781932ae015
Revises: 89fe23b2ed7d
"""

import sqlalchemy as sa
from alembic import op

revision = "c781932ae015"
down_revision = "89fe23b2ed7d"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "admin_user",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("username", sa.String(255), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
    )
    op.create_table(
        "admin_token",
        sa.Column("token_hash", sa.String(64), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("admin_user.id", ondelete="CASCADE"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_admin_token_user_id", "admin_token", ["user_id"])
    op.create_index("ix_admin_token_expires_at", "admin_token", ["expires_at"])


def downgrade():
    op.drop_table("admin_token")
    op.drop_table("admin_user")
