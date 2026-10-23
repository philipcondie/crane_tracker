"""Add anonymous photo reports.

Revision ID: d891a34b70f2
Revises: c781932ae015
"""

import sqlalchemy as sa
from alembic import op

revision = "d891a34b70f2"
down_revision = "c781932ae015"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "photo_report",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("photo_id", sa.Uuid(), sa.ForeignKey("crane_photo.id", ondelete="CASCADE"), nullable=False),
        sa.Column("reporter_ip_hash", sa.String(64), nullable=False),
        sa.Column("added_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("photo_id", "reporter_ip_hash", name="photo_reporter"),
    )
    op.create_index("ix_photo_report_photo_id", "photo_report", ["photo_id"])


def downgrade():
    op.drop_table("photo_report")
